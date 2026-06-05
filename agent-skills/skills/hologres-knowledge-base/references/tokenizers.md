# Tokenizer Selection Guide

Hologres full-text inverted index supports multiple tokenizers (`tokenizer = '<name>'` parameter).
Picking the right one is the single biggest precision/recall lever.

## Quick decision table

| Content type | Recommended tokenizer | Why |
|--------------|----------------------|-----|
| Long Chinese articles, keyword extraction | `jieba` | New-word discovery, mode switching |
| Chinese technical / domain descriptions | `ik` | Accurate Chinese terminology |
| English titles, short English text | `simple`, `whitespace`, `standard` | Fast, simple |
| Logs, identifiers, fuzzy LIKE acceleration | `ngram` | Dictionary-free, fuzzy matching |
| Chinese product / person names with pinyin | `pinyin` | Full pinyin, initials, polyphone |
| Multi-lingual text | `icu` | ICU-based Unicode segmentation |
| Tags, status enums, IDs | `keyword` | No tokenization, exact match only |
| Mixed-case English with punctuation | `standard` | Unicode Standard Annex #29 |

## All tokenizers

| Tokenizer | Min version | Default | Description |
|-----------|-------------|---------|-------------|
| `jieba` | V4.0 | ✓ | Chinese tokenizer combining rules + statistical model |
| `whitespace` | V4.0 | | Splits on whitespace |
| `standard` | V4.0 | | Unicode Standard Annex #29 |
| `simple` | V4.0 | | Splits on whitespace + punctuation |
| `keyword` | V4.0 | | No tokenization — emits whole string as one token |
| `icu` | V4.0 | | ICU-based multi-language segmentation |
| `ik` | V4.0.9 | | Chinese IK-style: recognizes English words, emails, URLs (no `://`), IPs |
| `ngram` | V4.0.9 | | Sliding window n-gram; enables LIKE/ILIKE-style fuzzy search |
| `pinyin` | V4.0.9 | | Chinese-to-pinyin (full / initials / polyphone) |

> **Special:** with `keyword` tokenizer, `index_options` is forced to `docs` (no positions/freqs).

---

## Default `analyzer_params`

In most cases, **don't set `analyzer_params`** — the defaults are sensible. Only customize
when you have a specific need.

### jieba

Default = `cut_for_search` mode + lowercase filter.

```sql
CREATE INDEX idx1 ON tbl USING FULLTEXT (col1) WITH (tokenizer = 'jieba');

-- Custom: exact mode, lowercase only
CREATE INDEX idx1 ON tbl USING FULLTEXT (col1)
WITH (
  tokenizer = 'jieba',
  analyzer_params = '{"tokenizer":{"type":"jieba","mode":"exact"}, "filter":["lowercase"]}'
);
```

Modes:
| Mode | Description |
|------|-------------|
| `cut_for_search` (default) | Multi-granularity, search-engine style |
| `exact` | Precise — non-overlapping |
| `full` | Outputs all possible terms — maximum recall |

### ik

```sql
CREATE INDEX idx1 ON tbl USING FULLTEXT (col1) WITH (tokenizer = 'ik');

-- Custom: ik_max_word, no lowercase
CREATE INDEX idx1 ON tbl USING FULLTEXT (col1)
WITH (
  tokenizer = 'ik',
  analyzer_params = '{"tokenizer":{"type":"ik","mode":"ik_max_word","enable_lowercase": false}}'
);
```

Modes:
| Mode | Description |
|------|-------------|
| `ik_smart` (default) | Coarse-grained — fewer tokens, higher precision |
| `ik_max_word` | Fine-grained — more tokens, higher recall |

### ngram

```sql
-- Default: 2-gram, 3-gram
CREATE INDEX idx_ngram ON tbl USING FULLTEXT (col1) WITH (tokenizer = 'ngram');

-- Custom: min=2, max=4 grams
CREATE INDEX idx_ngram ON tbl USING FULLTEXT (col1)
WITH (
  tokenizer = 'ngram',
  analyzer_params = '{"tokenizer":{"type":"ngram","min_gram":2,"max_gram":4}}'
);
```

Use for: LIKE-style fuzzy matching, log search, ID prefix/suffix lookup.

### pinyin

```sql
CREATE INDEX idx_pinyin ON tbl USING FULLTEXT (col1) WITH (tokenizer = 'pinyin');

-- Custom: only initials, keep original Chinese
CREATE INDEX idx_pinyin ON tbl USING FULLTEXT (col1)
WITH (
  tokenizer = 'pinyin',
  analyzer_params = '{
    "tokenizer":{"type":"pinyin","keep_first_letter":true,"keep_full_pinyin":false,"keep_original":true}
  }'
);
```

Use for: name search ("zhang san" / "张三" / "zs" all → same record), product catalog.

### keyword

```sql
-- For tags, IDs, enums
CREATE INDEX idx_tag ON tbl USING FULLTEXT (tag) WITH (tokenizer = 'keyword');
```

Note: `index_options` is forced to `docs`.

---

## Combining tokenizers

Hologres supports **one tokenizer per index**, so for compound needs (e.g. Chinese + pinyin),
create **multiple indexes**:

```sql
CREATE INDEX idx_content_jieba ON kb_documents USING FULLTEXT (content)
WITH (tokenizer = 'jieba');

CREATE INDEX idx_content_pinyin ON kb_documents USING FULLTEXT (content)
WITH (tokenizer = 'pinyin');
```

Then OR the search results in the app layer (or via SQL UNION).

> ⚠️ **One index per column!** You cannot have two indexes on the same column. To have both
> jieba-tokenized + pinyin-tokenized search, create **two separate `TEXT` columns** (e.g.
> `content`, `content_pinyin`) — populate both, index each with its tokenizer.

---

## Filters (post-tokenization processing)

`analyzer_params.filter` is an array of filters applied after tokenization. Common filters:

| Filter | Description |
|--------|-------------|
| `lowercase` | Convert all tokens to lowercase |
| `asciifolding` | Convert non-ASCII Unicode chars to ASCII equivalents |
| `stop` | Remove stop words |
| `length` | Filter out tokens by length |

Example:

```sql
CREATE INDEX idx ON tbl USING FULLTEXT (col)
WITH (
  tokenizer = 'standard',
  analyzer_params = '{"tokenizer":{"type":"standard"}, "filter":["lowercase","asciifolding"]}'
);
```

---

## `index_options` (V4.1.9+)

Controls index size vs. feature support:

| Value | Stored | Phrase search | BM25 quality | Use case |
|-------|--------|---------------|--------------|----------|
| `positions` (default) | DocID + freq + positions | ✓ | Full | General-purpose |
| `freqs` | DocID + freq | ✗ (error) | TF used | No phrase needed, save space |
| `docs` | DocID only | ✗ (error) | All TF = same | Existence check only, minimum size |

> Higher levels are supersets: `positions` ⊃ `freqs` ⊃ `docs`.

```sql
-- Save space, no phrase queries
CREATE INDEX idx ON tbl USING FULLTEXT (col) WITH (index_options = 'freqs');

-- Minimum size, existence check only
CREATE INDEX idx ON tbl USING FULLTEXT (col) WITH (index_options = 'docs');
```
