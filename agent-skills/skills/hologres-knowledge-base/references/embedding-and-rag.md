# Embeddings & RAG Patterns on Hologres

This guide covers what ADBPG does automatically (chunking, embedding, parsing, Q&A) but
**how to do it explicitly on Hologres**. You have two control planes:

1. **Server-side via `ai_gen()`** — Hologres calls an external embedding/LLM model from SQL
2. **Client-side** — Your Python code computes embeddings and writes via SDK

---

## 1. Register an embedding model in Hologres

Hologres can call external AI models (DashScope, OpenAI, etc.) via the
`register_external_model()` mechanism. The `hologres-cli` wraps this:

### List supported model types

```bash
# All catalog entries
hologres model catalog

# Embedding only
hologres model catalog --task embedding

# Search
hologres model catalog --search embed
```

Typical supported types (subject to change — always check `hologres model catalog` for the current list):

| Type | Provider | Dimension |
|------|----------|-----------|
| `text-embedding-v4` | DashScope (Tongyi) | 1024 (default) |
| `text-embedding-v3` | DashScope | 1024 |
| `qwen3-vl-embedding` | DashScope | varies |
| `text-embedding-3-small` | OpenAI | 1536 |
| `text-embedding-3-large` | OpenAI | 3072 |

### Register a model

```bash
hologres model create \
  --name my_embed \
  --type text-embedding-v4 \
  --api-key '<DASHSCOPE_API_KEY>'
```

> **Region** is auto-filled from the current profile's `region_id`. The API key is **never**
> echoed to `~/.hologres/sql-history.jsonl` or stdout.

### List registered models

```bash
hologres model list                          # all
hologres model list --task embedding         # filter by task
hologres model list --search embed           # substring search
```

### Delete a model

```bash
hologres model delete my_embed --confirm     # without --confirm: dry-run only
```

---

## 2. Chunking strategies

Hologres doesn't auto-chunk — choose the right strategy for your content:

| Strategy | Use case | Typical `chunk_size` | Notes |
|----------|----------|----------------------|-------|
| Fixed-size sliding window | General text | 300–800 tokens | Always pair with `chunk_overlap` (10~20%) |
| Sentence / paragraph split | Articles, structured docs | Variable | Preserves semantic boundaries |
| Markdown-aware | Technical docs, READMEs | Section-based | Split on headers (`#`, `##`) |
| Code-aware | Source code | Function-based | Use AST-based splitter |
| Semantic chunking | High-quality RAG | Variable | Embed each sentence, group by similarity |

Quick Python utility (LangChain `RecursiveCharacterTextSplitter`-style):

```python
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50,
               separators=("\n\n", "\n", "。", ". ", " ")) -> list[str]:
    """Naive recursive chunker — split on coarser separators first, fall back to finer."""
    if len(text) <= chunk_size:
        return [text]
    for sep in separators:
        if sep in text:
            parts = text.split(sep)
            chunks, buf = [], ""
            for p in parts:
                if len(buf) + len(p) + len(sep) > chunk_size:
                    if buf:
                        chunks.append(buf)
                    buf = (buf[-overlap:] if overlap else "") + p
                else:
                    buf = buf + (sep if buf else "") + p
            if buf:
                chunks.append(buf)
            return chunks
    return [text[i:i+chunk_size] for i in range(0, len(text), chunk_size - overlap)]
```

---

## 3. Two ingestion patterns

### Pattern A — Server-side embedding via `ai_gen()`

**Pros:** No client-side embedding pipeline. Embedding + write happen in a single SQL.
**Cons:** Each `INSERT` row triggers a remote API call → batch sizes are small.

```sql
-- One-row insert
INSERT INTO public.kb_documents (id, doc_id, chunk_idx, content, embedding, source)
VALUES (
    nextval('kb_documents_id_seq'),
    'doc_001',
    0,
    'Hologres 是一款实时数仓，支持向量检索…',
    ai_gen('my_embed', 'Hologres 是一款实时数仓，支持向量检索…')::FLOAT4[],
    'manual.pdf'
);

-- Bulk insert (chunks pre-split client-side, embeddings computed by Hologres)
INSERT INTO public.kb_documents (id, doc_id, chunk_idx, content, embedding, source)
SELECT
    nextval('kb_documents_id_seq'),
    'doc_001',
    chunk_idx,
    chunk_text,
    ai_gen('my_embed', chunk_text)::FLOAT4[],
    'manual.pdf'
FROM (VALUES
    (0, '第一段文本…'),
    (1, '第二段文本…'),
    (2, '第三段文本…')
) AS t(chunk_idx, chunk_text);
```

CLI invocation (use `--write`):

```bash
hologres sql run --write "<the INSERT above>"
```

### Pattern B — Client-side embedding via SDK

**Pros:** Use any embedding model (local sentence-transformers, OpenAI, etc.).
Batch many rows in one network round-trip. Better for high-throughput ingestion.

```python
import holo_search_sdk as holo
from openai import OpenAI   # or any embedding provider

oai = OpenAI(api_key="<OPENAI_API_KEY>")

def embed(texts: list[str]) -> list[list[float]]:
    r = oai.embeddings.create(model="text-embedding-3-small", input=texts)
    return [d.embedding for d in r.data]

client = holo.connect(host="...", port=..., database="...",
                     access_key_id="...", access_key_secret="...",
                     schema="public")
client.connect()
table = client.open_table("kb_documents")

chunks = chunk_text(open("manual.txt").read(), chunk_size=500, overlap=50)
embeddings = embed(chunks)

rows = [
    [i, "doc_001", i, chunk, emb, "manual.pdf", "2026-01-01"]
    for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
]

table.upsert_multi(
    index_column="id", values=rows,
    column_names=["id", "doc_id", "chunk_idx", "content", "embedding", "source", "publish_date"],
    update=True,
)

client.disconnect()
```

---

## 4. RAG (Q&A) pattern

Hologres has **no built-in chat-with-knowledge-base** API like ADBPG. The pattern:

```
[user question]
    ↓ embed
[query vector] → vector search (TopK chunks)
[user question] → fulltext search (TopK chunks)        [optional, for hybrid]
    ↓ RRF or weighted merge
[top-N retrieved chunks]
    ↓ assemble prompt
[LLM call]
    ↓
[answer + citations]
```

### Reference implementation

```python
import holo_search_sdk as holo

def rag_answer(question: str, top_k: int = 5) -> str:
    client = holo.connect(host="...", port=..., database="...",
                         access_key_id="...", access_key_secret="...",
                         schema="public")
    client.connect()
    try:
        table = client.open_table("kb_documents")

        # 1. Embed the question (client-side)
        q_vec = embed([question])[0]

        # 2. Retrieve via hybrid: vector + fulltext (RRF)
        v_results = (
            table.search_vector(vector=q_vec, column="embedding",
                                distance_method="Cosine", output_name="score")
            .select(["id", "content"]).limit(top_k * 2).fetchall()
        )
        f_results = (
            table.search_text(column="content", expression=question,
                              return_score=True, return_score_name="score")
            .select(["id", "content"]).limit(top_k * 2).fetchall()
        )

        # 3. RRF fusion (simple in-Python merge)
        scores = {}
        for rank, r in enumerate(v_results):
            scores[r["id"]] = scores.get(r["id"], 0) + 1.0 / (60 + rank)
        for rank, r in enumerate(f_results):
            scores[r["id"]] = scores.get(r["id"], 0) + 1.0 / (60 + rank)

        merged = {r["id"]: r for r in (v_results + f_results)}
        top = sorted(merged.values(), key=lambda r: -scores[r["id"]])[:top_k]

        context = "\n\n---\n\n".join(f"[chunk {r['id']}]\n{r['content']}" for r in top)

        # 4. Call LLM
        prompt = f"""根据下面的知识库片段回答问题。如答案不在片段中，请如实说不知道。

【知识库片段】
{context}

【问题】
{question}

【答案】"""

        # Either via hologres-cli...
        import subprocess
        out = subprocess.run(
            ["hologres", "ai", "gen", prompt, "--model", "qwen-max"],
            capture_output=True, text=True, check=True,
        )
        return out.stdout

        # ...or via your own LLM SDK (DashScope/OpenAI/etc.)

    finally:
        client.disconnect()
```

### Pure-SQL alternative (via `ai_gen()`)

If your LLM is registered in Hologres, you can do retrieval + answer in **one SQL**:

```sql
WITH retrieved AS (
  SELECT content
  FROM public.kb_documents
  ORDER BY approx_cosine_distance(embedding, ai_gen('my_embed', '如何配置 HGraph？')::FLOAT4[]) DESC
  LIMIT 5
),
context AS (
  SELECT string_agg(content, E'\n---\n') AS ctx FROM retrieved
)
SELECT ai_gen('qwen-max',
    '根据下面知识库回答：' || E'\n' || ctx || E'\n\n问题：如何配置 HGraph？')
FROM context;
```

Run via:

```bash
hologres sql run "<the SQL above>"
```

---

## 5. Embedding cache

For large corpora, avoid re-embedding identical chunks. Patterns:

- **Hash-based dedup**: add `chunk_hash TEXT` column, upsert by hash
- **Two-table design**: separate `embeddings_cache(text_hash, embedding)` table, INSERT chunks only if hash unseen

---

## 6. Reranking (optional second stage)

Vector + BM25 retrieve broad candidates; a cross-encoder reranker boosts precision:

```python
# After hybrid retrieval, rerank top 50 → top 5
from sentence_transformers import CrossEncoder
reranker = CrossEncoder("BAAI/bge-reranker-large")

scores = reranker.predict([(question, r["content"]) for r in top50])
top5 = [r for _, r in sorted(zip(scores, top50), reverse=True)[:5]]
```

> Hologres does **not** ship a built-in reranker. If your LLM provider exposes a rerank endpoint
> (e.g. DashScope `gte-rerank`), you can also wrap that as a Hologres external model and call
> via `ai_gen()` — but as of now, the catalog focuses on chat/embedding/image/video tasks.
