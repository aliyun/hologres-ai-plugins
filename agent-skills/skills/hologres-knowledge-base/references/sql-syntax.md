# SQL Syntax Reference — Full-text & Vector Index

Complete SQL syntax for Hologres full-text inverted index and HGraph vector index.

## Full-text Inverted Index

### Create index

```sql
CREATE INDEX [ IF NOT EXISTS ] <idx_name> ON <table_name>
USING FULLTEXT (<column_name> [, ...])
[ WITH ( <storage_parameter> [ = <value> ] [, ...] ) ];
```

**Parameters:**

| Parameter | Description |
|-----------|-------------|
| `idx_name` | Index name |
| `table_name` | Target table |
| `column_name` | Target column (TEXT / CHAR / VARCHAR). One index per column. |
| `tokenizer` | `jieba` (默认) / `whitespace` / `standard` / `simple` / `keyword` / `icu` / `ik` (V4.0.9+) / `ngram` (V4.0.9+) / `pinyin` (V4.0.9+) |
| `analyzer_params` | JSON string for custom tokenizer config |
| `index_options` | `positions` (默认, 全功能) / `freqs` (省空间, 不支持短语) / `docs` (最省, 仅存在性) — V4.1.9+ |

**Examples:**

```sql
-- Default jieba tokenizer
CREATE INDEX idx1 ON tbl USING FULLTEXT (col1);

-- IK tokenizer
CREATE INDEX idx1 ON tbl USING FULLTEXT (col1) WITH (tokenizer = 'ik');

-- Custom jieba analyzer_params: exact mode + lowercase filter
CREATE INDEX idx1 ON tbl USING FULLTEXT (col1)
WITH (
  tokenizer = 'jieba',
  analyzer_params = '{"tokenizer":{"type":"jieba","mode":"exact"}, "filter":["lowercase"]}'
);

-- Space-saving: only freqs, no positions (phrase search disabled)
CREATE INDEX idx1 ON tbl USING FULLTEXT (col1) WITH (index_options = 'freqs');
```

### Alter index

```sql
-- Change a property
ALTER INDEX [IF EXISTS] <idx_name> SET (<param> = '<value>' [, ...]);

-- Reset to default
ALTER INDEX [IF EXISTS] <idx_name> RESET (<param> [, ...]);
```

Examples:

```sql
ALTER INDEX idx1 SET (tokenizer = 'standard');

ALTER INDEX idx1 SET (
  tokenizer = 'ik',
  analyzer_params = '{"tokenizer":{"type":"ik","mode":"ik_max_word","enable_lowercase": false}}'
);

ALTER INDEX idx1 RESET (tokenizer, analyzer_params);
ALTER INDEX idx1 SET (index_options = 'docs');
```

> ⚠️ Always run `VACUUM <schema>.<table>;` after ALTER to trigger async rebuild.

### Drop index

```sql
DROP INDEX [IF EXISTS] <idx_name> [RESTRICT];
```

### Inspect indexes

```sql
-- All full-text indexes
SELECT * FROM hologres.hg_index_properties;

-- Map index → table + column
SELECT t.relname AS table_name, a.attname AS column_name
FROM pg_class t
  JOIN pg_index i ON t.oid = i.indrelid
  JOIN pg_class idx ON i.indexrelid = idx.oid
  JOIN pg_attribute a ON a.attrelid = t.oid AND a.attnum = ANY(i.indkey)
WHERE t.relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = '<schema>')
  AND idx.relname = '<idx_name>'
LIMIT 1;

-- Build progress
SELECT * FROM hg_show_build_index_progress('<table_name>');
-- Returns: schema_name, table_name, index_name, index_id, am_name,
--          built_index_size, built_num_files, target_num_files,
--          progress, estimated_remaining_time
```

### Full-text search functions

#### `TEXT_SEARCH(...)` — BM25 scored search

**Signature:**

```sql
TEXT_SEARCH(
    search_data        TEXT/VARCHAR/CHAR  -- the indexed column (constant column ref only)
  , search_expression  TEXT               -- the query string (constant only)
  [ , mode             TEXT DEFAULT 'match'
  , operator           TEXT DEFAULT 'OR'
  , tokenizer          TEXT DEFAULT ''    -- defaults to the index's tokenizer
  , analyzer_params    TEXT DEFAULT ''
  , options            TEXT DEFAULT '' ]
) RETURNS FLOAT       -- BM25 relevance score (0 = no match, higher = more relevant)
```

**Mode reference:**

| Mode | Description | Requirement |
|------|-------------|-------------|
| `match` (default) | Tokenize query, match tokens (AND/OR per `operator`) | any `index_options` |
| `phrase` | Exact phrase, slop via `options => 'slop=N;'` | `index_options = 'positions'` |
| `natural_language` | Free-form: `+must -exclude "phrase"`, `AND` / `OR` keywords | depends on operators used |
| `term` | No tokenization, exact-match a single token | any |
| `fuzzy` (V4.2+) | Edit-distance tolerant, via `options => 'fuzziness=1;'` (or `AUTO`) | any |

**Examples:**

```sql
-- Keyword AND match
SELECT id, text_search(content, 'machine learning', operator => 'AND') AS score
FROM tbl
WHERE text_search(content, 'machine learning', operator => 'AND') > 0
ORDER BY score DESC;

-- Phrase with slop=2 (chars for jieba/keyword/icu; tokens for standard/simple/whitespace)
SELECT id FROM tbl
WHERE text_search(content, 'machine learning', mode => 'phrase', options => 'slop=2;') > 0;

-- Natural language (+must, -exclude)
SELECT id FROM tbl
WHERE text_search(content, '+python -java system', mode => 'natural_language') > 0;

-- Term (no tokenization — useful for tags, IDs)
SELECT id FROM tbl WHERE text_search(content, 'python', mode => 'term') > 0;

-- Fuzzy (V4.2+) — tolerate typos
SELECT id FROM tbl
WHERE text_search(content, 'shaandong', mode => 'fuzzy', options => 'fuzziness=1;') > 0;

-- AUTO fuzziness — token length <3 → 0 edits, 3~5 → 1, ≥6 → 2
SELECT id FROM tbl
WHERE text_search(content, 'shandong universty', options => 'fuzziness=AUTO;') > 0;
```

> ⚠️ **Do NOT use `content @@ to_tsquery(...)` for the Hologres fulltext index** — that targets
> PostgreSQL's native `tsvector` infrastructure and silently bypasses the `USING FULLTEXT`
> (Tantivy) index. Always use `text_search(...) > 0` as the WHERE predicate.

#### `TOKENIZE(...)` — debug tokenization

```sql
TOKENIZE(
    search_data       TEXT
  [ , tokenizer       TEXT DEFAULT ''   -- defaults to jieba
  , analyzer_params   TEXT DEFAULT '' ]
) RETURNS TEXT[]   -- token array
```

Examples:

```sql
SELECT tokenize('Hologres V4.0 向量索引');
-- {hologres,v4.0,v,4.0,向量,索引}

SELECT tokenize('Hello World 你好', 'standard');
SELECT tokenize('张三', 'pinyin');
```

#### Verify the index is used

`EXPLAIN <query>` — look for `Fulltext Filter` in the plan:

```
Index Scan using Clustering_index on tbl
  Fulltext Filter: (text_search(content, search_expression => '长江'::text,
                                 mode => match, operator => OR, ...) > '0'::double precision)
```

If `Fulltext Filter` is missing, the query fell back to brute force (which is a hard error
for fulltext — Hologres requires the index, unlike vector search).

---

## HGraph Vector Index

### Create index (at table create time, recommended)

The recommended pattern (Hologres V2.1+) is to put **all** table properties — including
`vectors` — into a single `WITH (...)` clause on the initial `CREATE TABLE`. This is preferred
over the legacy two-step pattern (`CREATE TABLE` + `CALL set_table_property(...)`).

Minimal form:

```sql
CREATE TABLE <TABLE_NAME> (
    <VECTOR_COLUMN> float4[] CHECK (
        array_ndims(<VECTOR_COLUMN>) = 1
        AND array_length(<VECTOR_COLUMN>, 1) = <DIM>
    )
)
WITH (
    vectors = '{
        "<VECTOR_COLUMN>": {
            "algorithm": "HGraph",
            "distance_method": "<Cosine|InnerProduct|Euclidean>",
            "builder_params": {
                "base_quantization_type": "rabitq",
                ...
            }
        }
    }'
);
```

Full form (vector + base-table properties all in one WITH):

```sql
CREATE TABLE feature_tb (
    id BIGINT NOT NULL,
    doc_id TEXT NOT NULL,
    embedding FLOAT4[] CHECK (array_ndims(embedding) = 1 AND array_length(embedding, 1) = 768),
    publish_date TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (doc_id, id)
)
WITH (
    orientation = 'column',
    distribution_key = 'doc_id',
    clustering_key = 'publish_date:asc',
    event_time_column = 'publish_date',
    vectors = '{
        "embedding": {
            "algorithm": "HGraph",
            "distance_method": "Cosine",
            "builder_params": {
                "base_quantization_type": "rabitq",
                "graph_storage_type": "compressed",
                "max_degree": 64,
                "ef_construction": 400,
                "use_reorder": true,
                "precise_quantization_type": "fp32",
                "extra_columns": "id"
            }
        }
    }'
);
```

### `builder_params` reference

| Param | Required | Default | Description |
|-------|----------|---------|-------------|
| `max_degree` | No | `64` | Max neighbors per node (16~96 recommended) |
| `ef_construction` | No | `400` | Build-time search depth (≤600 recommended) |
| `base_quantization_type` | **Yes** | — | `sq8` / `sq8_uniform` / `fp16` / `fp32` / `rabitq` |
| `use_reorder` | No | `false` | Enable high-precision reorder layer |
| `precise_quantization_type` | **Yes** (when `use_reorder=true` at CREATE TABLE time) | `fp32` (via ALTER TABLE only) | Reorder layer quantization (must be higher precision than base). ⚠️ CREATE TABLE rejects missing value with `ERROR: precise_quantization_type must be set here`; ALTER TABLE accepts default `fp32`. |
| `precise_io_type` | No | `block_memory_io` | `block_memory_io` (all in memory) / `reader_io` (precise on disk) |
| `builder_thread_count` | No | `4` | Index build threads (don't touch unless CPU is fine) |
| `graph_storage_type` | No | `flat` | `flat` / `compressed` (save 50% memory, ~5% QPS loss) — V4.0.10+ |
| `extra_columns` | No | — | Attach columns (INT/BIGINT/SMALLINT only) to index — avoid base-table lookup — V4.1.1+ |

### Quantization decision

| Goal | base_quantization | use_reorder | precise_io_type |
|------|-------------------|-------------|-----------------|
| Lowest latency, high precision | `sq8_uniform` or `rabitq` | `true` | `block_memory_io` |
| Large data, decent latency | `rabitq` | `true` | `reader_io` |
| Highest precision (small data) | `fp32` | `false` | n/a |
| Most memory-efficient | `rabitq` + `graph_storage_type='compressed'` | depends | `reader_io` |

### Alter HGraph index

```sql
ALTER TABLE <TABLE_NAME>
SET (
    vectors = '{
        "<VECTOR_COLUMN>": {
            "algorithm": "HGraph",
            "distance_method": "Cosine",
            "builder_params": {
                "max_degree": 96,
                "ef_construction": 600,
                "base_quantization_type": "rabitq",
                "use_reorder": true
            }
        }
    }'
);
```

### Drop HGraph index

```sql
-- Drop ALL vector indexes on the table
ALTER TABLE <TABLE_NAME> SET (vectors = '{}');

-- Drop one column's index while keeping others (re-state remaining columns)
ALTER TABLE <TABLE_NAME>
SET (vectors = '{ "col1": { ...keep col1 config... } }');
```

### Inspect vector indexes

```sql
SELECT *
FROM hologres.hg_table_properties
WHERE table_name = '<TABLE_NAME>' AND property_key = 'vectors';
```

### Distance functions

Approximate (use HGraph index) — must match index `distance_method`:

| Function | distance_method | ORDER BY |
|----------|-----------------|----------|
| `approx_euclidean_distance(v, q)` | `Euclidean` | `ASC` |
| `approx_inner_product_distance(v, q)` | `InnerProduct` | `DESC` |
| `approx_cosine_distance(v, q)` | `Cosine` | `DESC` |

Exact (brute force, no index) — for small data or correctness verification:

| Function | Returns | ORDER BY |
|----------|---------|----------|
| `euclidean_distance(v, q)` | True L2 distance (lower = closer) | `ASC` |
| `inner_product_distance(v, q)` | Inner product `⟨v, q⟩` (higher = closer) — **not** `-⟨v, q⟩` despite the "distance" suffix | `DESC` |
| `cosine_distance(v, q)` | Cosine similarity in `[-1, 1]` (higher = closer) — **not** `1 - cos` | `DESC` |

> ⚠️ Hologres "distance" naming is misleading for Cosine and InnerProduct — both the approx
> and exact variants return similarity-style scores (higher = better) and require `ORDER BY DESC`.
> Only Euclidean follows the intuitive "lower = closer" convention.

### Example: Top-K vector search

```sql
SELECT id,
       approx_cosine_distance(embedding, '{0.1,0.2,0.3,0.4}') AS distance
FROM feature_tb
ORDER BY distance DESC
LIMIT 40;
```

Verify index is used via `EXPLAIN` — look for `Vector Filter`:

```
... -> Index Scan using Clustering_index on feature_tb
       Vector Filter: VectorCond => KNN: '40'::bigint distance_method: approx_cosine_distance ...
```

---

## Compaction (required after bulk load)

```sql
-- Standard
VACUUM <schema>.<table>;

-- Aggressive (force merge into larger files)
SELECT hologres.hg_full_compact_table('<schema>.<table>', 'max_file_size_mb=4096');
```

Or use Serverless Computing to build indexes during INSERT:

```sql
SET hg_computing_resource = 'serverless';
SET hg_serverless_computing_run_compaction_before_commit_bulk_load = on;

INSERT INTO feature_tb SELECT ...;

RESET hg_computing_resource;
```
