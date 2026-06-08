---
name: hologres-knowledge-base
description: |
  Hologres Knowledge Base Management: Build search & RAG knowledge bases on Hologres using
  full-text inverted index (Tantivy + BM25), HGraph vector index, and holo-search-sdk.
  Covers create knowledge base → ingest documents (with embeddings) → vector / full-text /
  hybrid search → Q&A with LLM.
  Triggers: "知识库", "knowledge base", "RAG", "向量检索", "vector search", "全文检索", "fulltext search",
  "倒排索引", "BM25", "HGraph", "holo-search-sdk", "embedding", "混合检索", "hybrid search",
  "Hologres 搜索", "Hologres search", "tantivy", "jieba", "ik 分词", "向量索引"
---

# Hologres Knowledge Base Management

Build enterprise search & RAG knowledge bases on Hologres in **three steps**:
**Create Table (with indexes) → Ingest Documents (with embeddings) → Search & Q&A**

Unlike fully managed RAG services (e.g. ADBPG Vector Engine), Hologres exposes the underlying
building blocks (vector + full-text + scalar columns in one table) and gives full control via
SQL or the Python `holo-search-sdk`. This is the right choice when you need:

- A single table that can be searched by vector, keyword, **and** SQL filters in one query
- Tight integration with your existing OLAP / data warehouse on Hologres
- Custom chunking / embedding pipelines

**Architecture**: `Hologres Instance + Schema + Table (vector column + text column + scalar columns) + HGraph Index + Fulltext Index + Embedding Model`

---

## Core Concepts

| Term in this skill | Hologres object |
|--------------------|-----------------|
| Knowledge base | A single column-store table holding chunks |
| Document chunk | One row in the table |
| Vector index | `HGraph` index on a `FLOAT4[]` column |
| Full-text index | `USING FULLTEXT` inverted index on a `TEXT` column |
| Embedding model | External AI model registered via `register_external_model()` and called by `ai_gen()` |
| Q&A / RAG | App layer calls `search_*()` → assembles prompt → calls `ai_gen()` (LLM) |

---

## Version Requirements

| Feature | Minimum Hologres version |
|---------|--------------------------|
| HGraph vector index | V4.0 |
| Full-text inverted index | V4.0 |
| IK / Ngram / Pinyin tokenizers | V4.0.9 |
| `index_options` (positions / freqs / docs) | V4.1.9 |
| `extra_columns` on HGraph | V4.1.1 |
| Real-time fulltext index async refresh | V4.0.8 |

> **[MUST] Verify version first:**
> ```bash
> hologres sql run "SELECT version()"
> ```
> If `< V4.0`, full-text and HGraph indexes are unavailable — abort and notify the user.

---

## Environment Setup

### 1. Install dependencies

```bash
# Hologres CLI (used for DDL, profile management, ai/model commands)
pip install hologres-cli

# holo-search-sdk (used for ingestion and search at runtime, requires Python >= 3.8)
pip install --upgrade holo-search-sdk    # >= 0.3.0
pip install psycopg-binary               # required by holo-search-sdk
```

### 2. Configure profile (one-time)

```bash
hologres config         # interactive wizard
hologres status         # verify connection
```

### 3. Set skill tag for query attribution

```bash
export HOLOGRES_SKILL=hologres-knowledge-base
```

All queries from this session will appear in `hologres.hg_query_log` with
`application_name = "hologres-cli/hologres-knowledge-base"`.

---

## Parameter Confirmation

> **IMPORTANT: Parameter Confirmation** — Before creating tables / indexes / inserting data,
> **ALL** user-customizable parameters MUST be confirmed with the user. Do **not** assume defaults.

| Parameter | Required | Description | Suggested default |
|-----------|----------|-------------|-------------------|
| `schema` | Optional | Target schema | `public` |
| `table` | Required | Knowledge base table name | — |
| `vector_dim` | Required | Vector dimension (must match embedding model) | `1024` for `text-embedding-v4` |
| `distance_method` | Optional | `Cosine` / `InnerProduct` / `Euclidean` | `Cosine` |
| `tokenizer` | Optional | `jieba` / `ik` / `standard` / `ngram` / `pinyin` / … | `jieba` (中文) |
| `chunk_size` | Optional | Tokens per chunk | `500` |
| `chunk_overlap` | Optional | Token overlap between chunks | `50` |
| `embedding_model` | Required | Name registered in Hologres via `register_external_model()`, or a local model | `text-embedding-v4` |
| `llm_model` | Optional (Q&A only) | LLM for answer synthesis | `qwen-max` |

> **Security:** Never echo / print AccessKey, password, or API keys.
> Use `hologres config` to manage connection profiles.
> The CLI redacts sensitive literals in `~/.hologres/sql-history.jsonl`.

---

## Core Workflow

### 1. Create the Knowledge Base Table

A knowledge base in Hologres is a single column-store table holding:
- A primary key (`id`)
- The raw text chunk (`content TEXT`) — full-text indexed
- The embedding (`embedding FLOAT4[]`) — HGraph vector indexed
- Optional metadata columns (`doc_id`, `chunk_idx`, `source`, `publish_date`, …)

#### Option A — Recommended: one CREATE TABLE with all properties in WITH (V2.1+)

This is the official Hologres-recommended pattern: table columns, primary key, all table
properties (`orientation`, `distribution_key`, `clustering_key`, `event_time_column`, …) **and**
the `vectors` HGraph config all in a single `WITH (...)` clause. Then add the fulltext index
separately (it is its own DDL).

> ⚠️ Avoid the legacy `CALL set_table_property(...)` form — it still works but the WITH syntax
> is more concise, atomic, and recommended from Hologres V2.1 onward. The bundled
> `hologres table create` CLI command currently emits the legacy syntax and does **not** support
> `vectors=`; use raw SQL via `hologres sql run --write` for this skill.

```bash
hologres sql run --write "
CREATE TABLE public.kb_documents (
    id BIGINT NOT NULL,
    doc_id TEXT NOT NULL,
    chunk_idx INT,
    content TEXT,
    embedding FLOAT4[] CHECK (array_ndims(embedding) = 1 AND array_length(embedding, 1) = 1024),
    source TEXT,
    publish_date TIMESTAMPTZ,
    PRIMARY KEY (doc_id, id)               -- composite PK so distribution_key ⊆ PK
)
WITH (
    orientation = 'column',
    distribution_key = 'doc_id',           -- co-locate chunks of the same doc on one shard
    clustering_key = 'publish_date:asc',
    event_time_column = 'publish_date',    -- file-level pruning on time range queries
    vectors = '{
        \"embedding\": {
            \"algorithm\": \"HGraph\",
            \"distance_method\": \"Cosine\",
            \"builder_params\": {
                \"base_quantization_type\": \"rabitq\",
                \"graph_storage_type\": \"compressed\",
                \"max_degree\": 64,
                \"ef_construction\": 400,
                \"use_reorder\": true,
                \"precise_quantization_type\": \"fp32\",
                \"extra_columns\": \"id\"
            }
        }
    }'
);

CREATE INDEX idx_kb_content_ft
    ON public.kb_documents
    USING FULLTEXT (content)
    WITH (tokenizer = 'jieba');
"
```

> ⚠️ **`precise_quantization_type` is mandatory at CREATE TABLE time** when `use_reorder = true`,
> even though the docs say it has a default of `fp32`. `ALTER TABLE SET (vectors = ...)` is more
> lenient and will apply the default — but `CREATE TABLE WITH (vectors = ...)` will reject the
> statement with `ERROR: precise_quantization_type must be set here.`

#### Option B — All-in-one via holo-search-sdk (Python)

The SDK exposes convenience methods (`set_vector_index`, `create_text_index`) that internally
issue `ALTER TABLE`. You can still fold all base-table properties into the initial CREATE TABLE
WITH clause — just skip the `vectors` config there and let `set_vector_index()` add it later
(easier to call from Python than building a JSON literal in a multi-line string).

```python
import holo_search_sdk as holo

client = holo.connect(
    host="<HOLO_HOST>", port=<HOLO_PORT>, database="<HOLO_DBNAME>",
    access_key_id="<ACCESS_KEY_ID>", access_key_secret="<ACCESS_KEY_SECRET>",
    schema="public",
)
client.connect()

client.execute("""
CREATE TABLE IF NOT EXISTS kb_documents (
    id BIGINT NOT NULL,
    doc_id TEXT NOT NULL,
    chunk_idx INT,
    content TEXT,
    embedding FLOAT4[] CHECK (array_ndims(embedding) = 1 AND array_length(embedding, 1) = 1024),
    source TEXT,
    publish_date TIMESTAMPTZ,
    PRIMARY KEY (doc_id, id)
)
WITH (
    orientation = 'column',
    distribution_key = 'doc_id',
    clustering_key = 'publish_date:asc',
    event_time_column = 'publish_date'
);
""", fetch_result=False)

table = client.open_table("kb_documents")

# Vector index (SDK issues ALTER TABLE under the hood — accepts default precise_quantization_type)
table.set_vector_index(
    column="embedding",
    distance_method="Cosine",
    base_quantization_type="rabitq",
    use_reorder=True,
    max_degree=64,
    ef_construction=400,
)

# Full-text index
table.create_text_index(
    index_name="idx_kb_content_ft",
    column="content",
    tokenizer="jieba",
)
```

#### Index design checklist

| Decision | Guidance |
|----------|----------|
| Vector dim | **Must equal** the output dim of the embedding model. Mismatched dim → INSERT fails. |
| `distance_method` | `Cosine` for semantic similarity (most common); `InnerProduct` for inner-product; `Euclidean` for L2. |
| `base_quantization_type` | `rabitq` (best balance), `sq8_uniform` (low-latency pure-memory), `fp32` (highest precision, largest). |
| `precise_io_type` | `block_memory_io` (latency-sensitive) / `reader_io` (large data, mix memory + disk). |
| `tokenizer` | `jieba` (默认中文), `ik` (中文术语), `standard` (英文), `ngram` (模糊匹配/like 加速), `pinyin` (拼音). |
| Single-shard data scale | Latency-sensitive: ≤500万行/shard; throughput: ≤3000~5000万行/shard (768-dim). |

---

### 2. Ingest Documents

The ingestion pipeline is **app-side**: chunk → embed → INSERT. Hologres does **not** auto-chunk
or auto-embed (unlike ADBPG). You have two embedding strategies:

#### Strategy A — Embed in Hologres via `ai_gen()` (recommended for SQL-only pipelines)

Register an external embedding model once via SQL:

```bash
hologres sql run --write "CALL register_external_model('my_embed', 'text-embedding-v4', 'bailian', '{\"api_key\": \"<DASHSCOPE_API_KEY>\"}', 'embedding')"
```

Then insert chunks and let Hologres compute embeddings server-side:

```bash
hologres sql run --write "
INSERT INTO public.kb_documents (id, doc_id, chunk_idx, content, embedding, source, publish_date)
SELECT
    nextval('kb_documents_id_seq'),
    'doc_001',
    chunk_idx,
    chunk_text,
    ai_gen('my_embed', chunk_text)::FLOAT4[],
    'manual.pdf',
    NOW()
FROM (VALUES
    (1, 'Hologres 是一款实时数仓，支持向量检索…'),
    (2, '通过 HGraph 算法可实现高性能近似最近邻搜索…')
) AS t(chunk_idx, chunk_text);
"
```

#### Strategy B — Embed in Python, upsert via holo-search-sdk

For external embedding APIs or local models, generate embeddings client-side then bulk-upsert:

```python
# Pseudo-code — replace embed() with your model call
chunks = chunk_document(text, chunk_size=500, chunk_overlap=50)

rows = []
for i, chunk in enumerate(chunks):
    embedding = embed(chunk)              # → list[float] of length vector_dim
    rows.append([next_id(), "doc_001", i, chunk, embedding, "manual.pdf", "2026-01-01"])

table.upsert_multi(
    index_column="id",
    values=rows,
    column_names=["id", "doc_id", "chunk_idx", "content", "embedding", "source", "publish_date"],
    update=True,
)
```

#### After bulk load — trigger index build

Both vector and fulltext indexes build **asynchronously during Compaction**. Until built, BM25
scores are `0` and HGraph search falls back to brute force. For batch imports:

```bash
# Preferred: use Serverless Computing (does Compaction + index build during load)
hologres sql run --write "SET hg_computing_resource = 'serverless';
SET hg_serverless_computing_run_compaction_before_commit_bulk_load = on;"

# Or manually trigger Compaction after load
hologres sql run --write "VACUUM public.kb_documents;"
# or, more aggressive:
hologres sql run --write "SELECT hologres.hg_full_compact_table('public.kb_documents', 'max_file_size_mb=4096');"
```

#### Verify index build progress

```bash
# Full-text index progress
hologres sql run "SELECT * FROM hg_show_build_index_progress('public.kb_documents');"

# Inspect existing indexes
hologres sql run "SELECT * FROM hologres.hg_index_properties WHERE table_name = 'kb_documents';"
hologres sql run "SELECT * FROM hologres.hg_table_properties WHERE table_name = 'kb_documents' AND property_key = 'vectors';"
```

---

### 3. Search & Q&A

#### Vector search (semantic similarity)

```python
# holo-search-sdk
query_vec = embed("如何配置 Hologres 向量索引？")

results = (
    table.search_vector(
        vector=query_vec,
        column="embedding",
        distance_method="Cosine",
        output_name="similarity_score",
    )
    .where("publish_date > '2024-01-01'")     # scalar filter
    .order_by("similarity_score", "desc")      # Cosine in Hologres returns similarity (higher = closer)
    .limit(10)
    .fetchall()
)
```

Equivalent raw SQL (verify via `EXPLAIN` — look for **`Vector Filter`** in the plan):

```sql
SELECT id, content,
       approx_cosine_distance(embedding, '<query_vector_literal>') AS distance
FROM public.kb_documents
WHERE publish_date > '2024-01-01'
ORDER BY distance DESC     -- Cosine in Hologres returns similarity-like score → DESC
LIMIT 10;
```

> ⚠️ **Hologres "distance" functions for Cosine / InnerProduct return SIMILARITY scores**
> (higher = more similar), not true distance. This is a naming quirk — always check the
> ORDER BY direction below.
>
> | distance_method | Use approx function | ORDER BY | Semantics |
> |-----------------|---------------------|----------|-----------|
> | `Euclidean` | `approx_euclidean_distance` | `ASC` | True L2 distance (lower = closer) |
> | `InnerProduct` | `approx_inner_product_distance` | `DESC` | Inner product (higher = closer) |
> | `Cosine` | `approx_cosine_distance` | `DESC` | Similarity (higher = closer) — **not** `1 - cos` |
>
> ⚠️ **The exact functions (`cosine_distance`, `inner_product_distance`) follow the SAME convention**
> as their approx counterparts — they return similarity for Cosine/InnerProduct, not true distance.
> Only `euclidean_distance` returns a true distance.
>
> ⚠️ **Distance function must match index `distance_method`**, otherwise the HGraph index is bypassed
> and the query falls back to brute force (still correct, but slower).

#### Full-text search (keyword / BM25)

```python
results = (
    table.search_text(
        column="content",
        expression="向量索引 配置",
        mode="match", operator="AND",        # require all terms
        return_score=True, return_score_name="bm25",
    )
    .order_by("bm25", "desc")
    .limit(10)
    .fetchall()
)
```

Equivalent raw SQL — Hologres provides a dedicated `TEXT_SEARCH()` function that returns BM25
score. **Do not** use PostgreSQL's `@@ to_tsquery()` — that targets the built-in `tsvector`,
not the Tantivy-backed `USING FULLTEXT` index, and silently bypasses it.

```sql
-- Basic keyword match (default operator=OR)
SELECT id, content,
       text_search(content, '向量索引 配置') AS bm25
FROM public.kb_documents
WHERE text_search(content, '向量索引 配置') > 0     -- > 0 = matched
ORDER BY bm25 DESC
LIMIT 10;

-- AND mode: require all tokens
SELECT id, content,
       text_search(content, '向量索引 配置', operator => 'AND') AS bm25
FROM public.kb_documents
WHERE text_search(content, '向量索引 配置', operator => 'AND') > 0
ORDER BY bm25 DESC;
```

Verify the index is used via `EXPLAIN` — look for `Fulltext Filter` in the plan.

Search modes (`mode => ...`):

| Mode | Use case | Example |
|------|----------|---------|
| `match` (default) | Keyword match — configurable AND/OR via `operator` | `text_search(c, 'a b', operator => 'AND')` |
| `phrase` | Exact phrase — distance via `options => 'slop=N;'` | `text_search(c, 'a b', mode => 'phrase', options => 'slop=2;')` |
| `natural_language` | Free-form: `+must -exclude "phrase"`, AND / OR keywords | `text_search(c, '+python -java', mode => 'natural_language')` |
| `term` | No tokenization, exact token match | `text_search(c, 'python', mode => 'term')` |
| `fuzzy` (V4.2+) | Edit-distance tolerant match | `text_search(c, 'pythn', mode => 'fuzzy', options => 'fuzziness=1;')` |

> `phrase` mode `slop` unit: **characters** for jieba/keyword/icu; **tokens** for standard/simple/whitespace.

> Debug tokenization: `SELECT tokenize('Hologres V4.0 向量索引');`
> → `{hologres,v4.0,v,4.0,向量,索引}`

#### Hybrid search (vector + full-text + scalar)

Hologres lets you combine all three in a single SQL — this is its strongest differentiator vs.
dedicated vector DBs. Below is RRF (Reciprocal Rank Fusion) — a simple, parameter-light fusion:

```sql
WITH vec AS (
  SELECT id, content,
         approx_cosine_distance(embedding, '<query_vector_literal>') AS vec_sim,
         ROW_NUMBER() OVER (
           ORDER BY approx_cosine_distance(embedding, '<query_vector_literal>') DESC
         ) AS vec_rank
  FROM public.kb_documents
  WHERE publish_date > '2024-01-01'
  ORDER BY vec_sim DESC LIMIT 50
),
ft AS (
  SELECT id, content,
         text_search(content, 'Hologres 向量索引') AS bm25,
         ROW_NUMBER() OVER (
           ORDER BY text_search(content, 'Hologres 向量索引') DESC
         ) AS ft_rank
  FROM public.kb_documents
  WHERE text_search(content, 'Hologres 向量索引') > 0
    AND publish_date > '2024-01-01'
  LIMIT 50
)
-- RRF merge (k=60 is the conventional smoothing constant)
SELECT
  COALESCE(vec.id, ft.id) AS id,
  COALESCE(vec.content, ft.content) AS content,
  COALESCE(1.0 / (60 + vec.vec_rank), 0)
  + COALESCE(1.0 / (60 + ft.ft_rank), 0) AS rrf_score
FROM vec FULL OUTER JOIN ft USING (id)
ORDER BY rrf_score DESC
LIMIT 10;
```

#### Q&A (RAG)

Hologres has **no built-in chat-with-knowledge-base** API. The pattern is **assemble prompt
externally**, then call any LLM — either via `hologres ai gen` (uses a model registered in
Hologres) or via an external SDK:

```bash
# 1. Retrieve top-K chunks (use the hybrid query above)
# 2. Concatenate chunks into context, then ask the LLM:
hologres ai gen \
  "根据下面知识库片段回答问题。

【知识库】
$(cat retrieved_chunks.txt)

【问题】
如何为 Hologres 表添加 HGraph 向量索引？" \
  --model qwen-max
```

---

## Index Maintenance

### Modify an index

```bash
# Switch full-text tokenizer
hologres sql run --write "ALTER INDEX idx_kb_content_ft SET (tokenizer = 'ik');"

# Tune HGraph parameters (rebuilds on next Compaction)
hologres sql run --write "
ALTER TABLE public.kb_documents
SET (vectors = '{\"embedding\": {\"algorithm\": \"HGraph\", \"distance_method\": \"Cosine\",
                  \"builder_params\": {\"max_degree\": 96, \"ef_construction\": 600,
                  \"base_quantization_type\": \"rabitq\", \"use_reorder\": true}}}');
"
hologres sql run --write "VACUUM public.kb_documents;"   # trigger rebuild
```

### Drop an index

```bash
hologres sql run --write "DROP INDEX idx_kb_content_ft;"

# Drop vector index (replace vectors map with empty JSON)
hologres sql run --write "ALTER TABLE public.kb_documents SET (vectors = '{}');"
```

---

## Limitations & Gotchas

| Item | Caveat |
|------|--------|
| Vector / fulltext index | **Column-store / row-column tables only.** Row-store tables unsupported. |
| Fulltext column types | Only `TEXT` / `CHAR` / `VARCHAR`. One index per column. |
| Index build | Asynchronous via Compaction. Until built: BM25 = 0, vector → brute force. |
| Mem-table data | Newly inserted (in mem-table) data isn't yet indexed — brute-force scanned. |
| Vector approx recall | HGraph is **lossy**; `LIMIT 1000` may return fewer rows. |
| Recall trade-off | For small data (<100k rows), prefer **exact** functions (`cosine_distance`, etc.) — no index needed. |
| Brute force | Fulltext search **requires** an index — there is no brute-force fallback. |
| Phrase search | Requires `index_options = 'positions'` (default). `freqs` / `docs` modes → error. |
| Recycle bin | When dropping/recreating tables with vector indexes, **disable recycle bin** to avoid mem leaks. |

---

## Reference Links

| Document | Content |
|----------|---------|
| [references/sql-syntax.md](references/sql-syntax.md) | Full SQL syntax for `USING FULLTEXT`, HGraph, search functions |
| [references/holo-search-sdk.md](references/holo-search-sdk.md) | Complete Python SDK API reference |
| [references/embedding-and-rag.md](references/embedding-and-rag.md) | Embedding model registration, chunking strategies, RAG patterns |
| [references/tokenizers.md](references/tokenizers.md) | Tokenizer selection guide (jieba / ik / ngram / pinyin / …) |
| [references/performance-tuning.md](references/performance-tuning.md) | HGraph quantization choices, shard sizing, index build tuning |

External:
- [Hologres 全文倒排索引官方文档](https://help.aliyun.com/zh/hologres/user-guide/full-text-inverted-index)
- [Hologres HGraph 向量索引官方文档](https://help.aliyun.com/zh/hologres/user-guide/hgraph-index-usage-guide)
- [Hologres holo-search-sdk 官方文档](https://help.aliyun.com/zh/hologres/user-guide/hologres-search-sdk)

---

## Best Practices

1. **Always trigger Compaction after bulk load** — otherwise BM25 = 0 and vector search degrades.
   Prefer `SET hg_computing_resource = 'serverless'` for synchronous build during load.
2. **Confirm vector dimension matches embedding model** — `dim` mismatch is the #1 INSERT failure.
3. **Use `extra_columns` on HGraph** to fetch ID/scalar columns from the index — avoids reading the base table.
4. **Pick `rabitq` + `use_reorder=true`** as the default quantization — best precision/cost ratio.
5. **For Chinese**: `jieba` (general) or `ik` (terminology); for English: `standard`; for fuzzy: `ngram`.
6. **Verify the index is used** — `EXPLAIN <query>` and look for `Vector Filter` (vector) or fulltext-index scan.
7. **Don't index everything** — small (<100k rows) tables search faster by brute force.
8. **Tag queries with `HOLOGRES_SKILL`** — for per-skill stats in `hg_query_log`.

## Error Codes (from hologres-cli)

| Code | Meaning | Fix |
|------|---------|-----|
| `QUERY_ERROR: dim mismatch` | Embedding dim ≠ column constraint | Re-check embedding model dim |
| `QUERY_ERROR: index_options 'freqs' does not support phrase` | Phrase search on non-positions index | Recreate index with `index_options = 'positions'` |
| `QUERY_ERROR: only column/row-column tables support fulltext index` | Index on row-store table | Recreate as `orientation = 'column'` |
| `WRITE_GUARD_ERROR` | DDL/DML without `--write` flag | Add `--write` to `hologres sql run` |
| `NOT_SUPPORTED` | Command not supported | Check CLI version or documentation |
