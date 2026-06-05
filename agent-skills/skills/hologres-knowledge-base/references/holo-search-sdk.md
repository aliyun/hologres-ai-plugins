# holo-search-sdk Python API Reference

`holo-search-sdk` is the official Python SDK for unified full-text + vector search on Hologres.
It wraps psycopg + Hologres-specific search syntax into a fluent API.

> **Version requirement:** `holo-search-sdk >= 0.3.0`, `Python >= 3.8`

## Installation

```bash
pip install --upgrade holo-search-sdk
pip install psycopg-binary    # required runtime dep — must be installed separately
```

Common install error:

```
ImportError: no pq wrapper available.
  - couldn't import psycopg 'c' implementation
  - couldn't import psycopg 'binary' implementation
  - couldn't import psycopg 'python' implementation
```

→ Fix: `pip install psycopg-binary`

---

## Connect to Hologres

```python
import holo_search_sdk as holo

client = holo.connect(
    host="<HOLO_HOST>",                # 实例详情 → 网络信息
    port=<HOLO_PORT>,                  # usually 80 or 443
    database="<HOLO_DBNAME>",
    access_key_id="<ACCESS_KEY_ID>",
    access_key_secret="<ACCESS_KEY_SECRET>",
    schema="public",                   # default schema
)
client.connect()

# ... do work ...

client.disconnect()
```

> **Security:** Don't paste AccessKey/Secret in code committed to git. Read from env vars or
> from `~/.hologres/config.json` (managed by `hologres-cli`).

---

## Table operations

### Execute arbitrary SQL

```python
client.execute(
    "CREATE TABLE IF NOT EXISTS kb (id BIGINT PRIMARY KEY, content TEXT, embedding FLOAT4[])",
    fetch_result=False,
)
```

### Open an existing table

```python
table = client.open_table("kb_documents")
```

### Insert rows

```python
# Bulk insert
data = [
    [1, "Hello world", [0.1, 0.2, 0.3], "2023-01-01"],
    [2, "Python SDK",  [0.4, 0.5, 0.6], "2024-01-01"],
]
table.insert_multi(data, ["id", "content", "vector_column", "publish_date"])
```

### Upsert

```python
# Single-row upsert
table.upsert_one(
    index_column="id",
    values=[1, "updated content", [0.3, 0.2, 0.1], "2026-01-01"],
    column_names=["id", "content", "vector_column", "publish_date"],
    update=True,                          # conflict → update
)

# Batch upsert
table.upsert_multi(
    index_column="id",
    values=[
        [1, "new content 1", [0.2, 0.3, 0.4], "2026-02-01"],
        [2, "new content 2", [0.6, 0.5, 0.7], "2024-02-01"],
    ],
    column_names=["id", "content", "vector_column", "publish_date"],
    update=True,
    update_columns=["content", "vector_column"],   # only update these on conflict
)
```

---

## Index management

### Vector index

```python
table.set_vector_index(
    column="vector_column",
    distance_method="Cosine",                 # or "Euclidean" / "InnerProduct"
    base_quantization_type="rabitq",          # or "sq8" / "sq8_uniform" / "fp16" / "fp32"
    use_reorder=True,                         # add high-precision reorder layer
    max_degree=64,
    ef_construction=400,
)
```

### Full-text index

```python
# Create
table.create_text_index(
    index_name="ft_idx_content",
    column="content",
    tokenizer="jieba",                        # jieba / ik / standard / whitespace / ngram / pinyin / ...
)

# Modify (e.g. switch tokenizer)
table.set_text_index(
    index_name="ft_idx_content",
    tokenizer="ik",
)

# Drop
table.drop_text_index(index_name="ft_idx_content")
```

---

## Search

### Vector search

```python
query_vec = [0.2, 0.3, 0.4]

# Basic Top-K
results = (
    table.search_vector(
        vector=query_vec,
        column="vector_column",
        distance_method="Cosine",
    )
    .limit(10)
    .fetchall()
)

# With distance threshold
results = (
    table.search_vector(vector=query_vec, column="vector_column", distance_method="Cosine")
    .min_distance(0.5)
    .fetchall()
)

# Rename the distance column in output
results = (
    table.search_vector(
        vector=query_vec,
        column="vector_column",
        output_name="similarity_score",
        distance_method="Cosine",
    )
    .fetchall()
)
```

### Full-text search

```python
# Basic
results = table.search_text(
    column="content",
    expression="机器学习",
    return_all_columns=True,
).fetchall()

# With BM25 score
results = (
    table.search_text(
        column="content",
        expression="深度学习",
        return_score=True,
        return_score_name="relevance_score",
    )
    .select(["id", "vector_column", "content"])
    .fetchall()
)
```

#### Search modes

```python
# match (default) — keyword match, AND/OR between terms
table.search_text(column="content", expression="python programming", mode="match", operator="AND")

# phrase — exact phrase
table.search_text(column="content", expression="machine learning", mode="phrase")

# natural_language — +must -exclude "phrase"
table.search_text(column="content", expression='+python -java', mode="natural_language")

# term — no tokenization, exact token
table.search_text(column="content", expression="python", mode="term")
```

| Mode | What it does | Index requirement |
|------|--------------|-------------------|
| `match` | Tokenizes the query, matches tokens against indexed tokens (AND/OR) | any |
| `phrase` | Matches exact phrase | `index_options = 'positions'` (default) |
| `natural_language` | Boolean operators: `+must -exclude "phrase"` | depends on operators |
| `term` | No tokenization; exact-match a single token | any |

---

## Hybrid search (vector + full-text + scalar filters)

`search_vector` and `search_text` return a query builder that supports `.where()`, `.order_by()`,
`.limit()`, `.select()`, `.fetchall()` / `.fetchone()` — chain freely:

```python
# Vector + scalar filter
results = (
    table.search_vector(
        vector=query_vec, column="vector_column",
        output_name="similarity_score",
        distance_method="Cosine",
    )
    .where("publish_date > '2023-01-01'")
    .order_by("similarity_score", "desc")
    .limit(10)
    .fetchall()
)

# Full-text + scalar filter
results = (
    table.search_text(
        column="content", expression="人工智能",
        return_score=True, return_score_name="score",
    )
    .where("publish_date > '2023-01-01'")
    .order_by("score", "desc")
    .limit(10)
    .fetchall()
)
```

> For **true hybrid scoring** (vector + BM25 fused score, e.g. RRF), the SDK doesn't expose a
> high-level helper as of v0.3.0 — use `client.execute(...)` with raw SQL (see
> [sql-syntax.md](sql-syntax.md) for an RRF example).

---

## Point lookup by primary key

```python
# Single row
result = (
    table.get_by_key(
        key_column="id", key_value=1,
        return_columns=["id", "content", "vector_column"],   # optional
    )
    .fetchone()
)

# Batch
results = (
    table.get_multi_by_keys(
        key_column="id", key_values=[1, 2, 3],
        return_columns=["id", "content"],
    )
    .fetchall()
)
```

---

## Query builder methods

All `search_*()` and `get_*()` calls return a query builder. Chainable methods:

| Method | Purpose |
|--------|---------|
| `.where(sql_predicate)` | Add a scalar WHERE filter |
| `.select(columns)` | Restrict returned columns |
| `.order_by(column, "asc"\|"desc")` | Sort results |
| `.limit(n)` | Top-K |
| `.min_distance(threshold)` | (vector search) filter by max distance |
| `.fetchall()` | Execute, return all rows |
| `.fetchone()` | Execute, return first row |

---

## Wrapping it all up

```python
import holo_search_sdk as holo

client = holo.connect(
    host="<HOLO_HOST>", port=<HOLO_PORT>, database="<HOLO_DBNAME>",
    access_key_id="<ACCESS_KEY_ID>", access_key_secret="<ACCESS_KEY_SECRET>",
    schema="public",
)
client.connect()

try:
    table = client.open_table("kb_documents")

    results = (
        table.search_vector(
            vector=[0.1, 0.2, 0.3, 0.4],
            column="embedding",
            distance_method="Cosine",
            output_name="score",
        )
        .where("publish_date > '2024-01-01'")
        .order_by("score", "desc")
        .limit(10)
        .fetchall()
    )

    for row in results:
        print(row)

finally:
    client.disconnect()
```
