# Performance Tuning — HGraph + Full-text

This guide covers the choices that most affect search latency, throughput, and recall.

## When to skip the index entirely

For **small datasets (< 100k rows)** or when you have abundant compute, brute-force exact
search is often **faster** than HGraph and gives 100% recall:

```sql
-- Exact (no HGraph index needed)
SELECT id, cosine_distance(embedding, '<query_vec>') AS d
FROM kb_documents
ORDER BY d DESC
LIMIT 10;
```

HGraph trade-offs to be aware of:
- **Lossy index** — recall < 100%
- **May return fewer rows** — `LIMIT 1000` could return 500 if the graph doesn't traverse enough nodes
- **Build cost** — async during Compaction; new data is brute-forced until built

---

## HGraph quantization decision

Quantization compresses vectors to reduce memory; higher precision = more memory + better recall.

| `base_quantization_type` | Memory | Speed | Recall | Use case |
|--------------------------|--------|-------|--------|----------|
| `fp32` | 100% (4 B/dim) | Slowest | Highest | Small data, max precision |
| `fp16` | 50% | Mid | High | Balanced |
| `sq8` | 25% | Fast | Medium | Memory-tight |
| `sq8_uniform` | 25% | Fast | Medium-High | **Recommended for latency-sensitive pure-memory** |
| `rabitq` | ~3% (1 bit/dim + scalar) | Fastest | High (with reorder) | **Recommended default** |

### `use_reorder` (high-precision reorder layer)

Adds a second-stage rerank using high-precision vectors. Almost always worth enabling:

```json
"builder_params": {
  "base_quantization_type": "rabitq",
  "use_reorder": true,
  "precise_quantization_type": "fp32"
}
```

- `precise_quantization_type` should be **higher precision than base**
- `precise_io_type`:
  - `block_memory_io` (default) — all in memory, lowest latency
  - `reader_io` — high-precision layer on disk → trades latency for capacity

---

## Shard sizing (single-shard data scale)

Based on a 768-dim vector with single-column index:

| Profile | Single-shard rows |
|---------|-------------------|
| Latency-sensitive, pure-memory index | ≤ 5 million |
| Latency-relaxed, memory+disk hybrid | ≤ 30~50 million |

> Multi-column indexes / higher dimensions → scale down proportionally.

To set shard count, use a Table Group:

```sql
CALL HG_CREATE_TABLE_GROUP('kb_tg_8', 8);

CREATE TABLE kb_documents (
    id BIGINT NOT NULL,
    doc_id TEXT NOT NULL,
    content TEXT,
    embedding FLOAT4[] CHECK (array_ndims(embedding) = 1 AND array_length(embedding, 1) = 1024),
    PRIMARY KEY (doc_id, id)
)
WITH (
    table_group = 'kb_tg_8',
    orientation = 'column',
    distribution_key = 'doc_id',
    vectors = '{
      "embedding": {
        "algorithm": "HGraph",
        "distance_method": "Cosine",
        "builder_params": {
          "base_quantization_type": "rabitq",
          "use_reorder": true,
          "precise_quantization_type": "fp32",
          "graph_storage_type": "compressed"
        }
      }
    }'
);
```

---

## Build-time params

| Param | Tuning |
|-------|--------|
| `max_degree` | Default 64. Up to 96 trades memory + build time for recall. Beyond 96 → diminishing returns. |
| `ef_construction` | Default 400. Up to 600 trades build time for recall. Beyond 600 → diminishing returns. |
| `builder_thread_count` | Default 4. **Don't touch** unless you've measured a real bottleneck — higher values can spike CPU. |
| `graph_storage_type` | `flat` (default) / `compressed` (V4.0.10+, ~50% memory savings, ~5% QPS loss). |

---

## `extra_columns` trick (V4.1.1+)

Attach scalar columns to the HGraph index, so the search **doesn't need to read the base table**:

```json
"builder_params": {
  "base_quantization_type": "rabitq",
  "extra_columns": "id"
}
```

After this, queries like `SELECT id, approx_cosine_distance(...) FROM tbl ORDER BY ... LIMIT 10`
are served entirely by the index. Verify via `EXPLAIN ANALYZE` — look for
`vector_index_extra_columns_used` counter.

**Limitations:**
- Only `INT`, `BIGINT`, `SMALLINT` columns can be attached
- Adds to index size

---

## Bulk-load with Serverless Computing (synchronous index build)

By default, indexes build async via Compaction. For batch loads, use Serverless Computing to
build during load — eliminates the "BM25 = 0, vector = brute force" gap:

```sql
SET hg_computing_resource = 'serverless';
SET hg_serverless_computing_run_compaction_before_commit_bulk_load = on;

INSERT INTO kb_documents SELECT ... FROM staging_table;

RESET hg_computing_resource;
```

Or trigger Compaction manually after load:

```sql
VACUUM public.kb_documents;
-- More aggressive:
SELECT hologres.hg_full_compact_table('public.kb_documents', 'max_file_size_mb=4096');
```

> For small (small batch / streaming) loads, BM25 scores are file-level → small files →
> imprecise relative scores. **Manual `VACUUM`** consolidates files and improves precision.

---

## Verify index is used

```sql
EXPLAIN
SELECT id, approx_cosine_distance(embedding, '<vec>') AS d
FROM kb_documents
ORDER BY d DESC LIMIT 40;
```

Look for `Vector Filter` in the plan:

```
Index Scan using Clustering_index on kb_documents
  Vector Filter: VectorCond => KNN: '40'::bigint distance_method: approx_cosine_distance ...
```

If `Vector Filter` is **missing**, the index isn't used. Common causes:

| Cause | Fix |
|-------|-----|
| Distance function ≠ index `distance_method` | Use the matching `approx_*` function |
| Wrong ORDER BY direction | `Euclidean → ASC`, `Cosine/InnerProduct → DESC` |
| Query against newly inserted (mem-table) data | Trigger Compaction with `VACUUM` |
| Using exact function (`cosine_distance`) instead of `approx_cosine_distance` | Use the approx variant |
| Filter on indexed column with non-supported predicate | Move filter to a separate column |

---

## Query-time GUC tuning

| GUC | Default | Effect |
|-----|---------|--------|
| `hg_experimental_enable_adaptive_execution` | `on` | Adaptive plan rewrites — leave on |
| `hg_computing_resource` | varies | Set to `'serverless'` for heavy queries |
| `statement_timeout` | `8h` | Lower for production queries |

Set per-session via `hologres sql run`:

```bash
hologres sql run "SET hg_computing_resource = 'serverless'; SELECT ..."
```

---

## Monitoring index status

```bash
# Per-table fulltext build progress
hologres sql run "SELECT * FROM hg_show_build_index_progress('public.kb_documents');"

# All fulltext indexes
hologres sql run "SELECT * FROM hologres.hg_index_properties;"

# Vector index properties
hologres sql run "SELECT * FROM hologres.hg_table_properties WHERE property_key = 'vectors';"

# Table size (to gauge shard sizing)
hologres table size public.kb_documents
hologres table properties public.kb_documents
```

---

## A/B testing recall

After a config change, compare recall against exact search on a sample of queries:

```sql
-- Ground truth
WITH gt AS (
  SELECT id FROM kb_documents
  ORDER BY cosine_distance(embedding, '<q>') DESC
  LIMIT 100
),
-- HGraph approx
approx AS (
  SELECT id FROM kb_documents
  ORDER BY approx_cosine_distance(embedding, '<q>') DESC
  LIMIT 100
)
SELECT COUNT(*) FILTER (WHERE id IN (SELECT id FROM gt))::FLOAT / COUNT(*) AS recall_at_100
FROM approx;
```

Run for a batch of queries → average. Aim for ≥ 0.95 recall@K for production.
