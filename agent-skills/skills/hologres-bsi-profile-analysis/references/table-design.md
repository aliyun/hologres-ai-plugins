# BSI Table Design Patterns

Table design patterns for BSI-based user profile analysis in Hologres.

## Basic Pattern (No Bucketing)

Suitable for small datasets where data concentration is acceptable.

### Entity-Relationship

```
dws_userbase ──┐
               ├─→ dws_uid_dict ──→ rb_tag (attribute tags)
usershop_behavior ─┘              └─→ bsi_gmv (behavioral tags)
```

### DDL

```sql
-- User attribute source table
CREATE TABLE dws_userbase (
    uid int NOT NULL PRIMARY KEY,
    province text,
    gender text
    -- Other attribute columns
) WITH (
    distribution_key = 'uid'
);

-- UID dictionary encoding table (required for Roaring Bitmap / BSI)
CREATE TABLE dws_uid_dict (
    encode_uid serial,
    uid int PRIMARY KEY
);

-- User behavioral tag source table
CREATE TABLE usershop_behavior (
    uid int NOT NULL,
    gmv int
) WITH (
    distribution_key = 'uid'
);

-- Roaring Bitmap attribute tag table
CREATE TABLE rb_tag (
    tag_name text,
    tag_val text,
    bitmap roaringbitmap
);

-- BSI behavioral tag table (GMV)
CREATE TABLE bsi_gmv (
    gmv_bsi bsi
);
```

### Data Flow

1. Populate `dws_uid_dict` with contiguous integer encoding of UIDs.
2. Build `rb_tag` from `dws_userbase` + `dws_uid_dict` using `rb_build_agg()`.
3. Build `bsi_gmv` from `usershop_behavior` + `dws_uid_dict` using `bsi_build()`.

### Import SQL

```sql
-- Attribute tags → Roaring Bitmap
INSERT INTO rb_tag
SELECT 'province', province, rb_build_agg(b.encode_uid) AS bitmap
FROM dws_userbase a JOIN dws_uid_dict b ON a.uid = b.uid
GROUP BY province;

INSERT INTO rb_tag
SELECT 'gender', gender, rb_build_agg(b.encode_uid) AS bitmap
FROM dws_userbase a JOIN dws_uid_dict b ON a.uid = b.uid
GROUP BY gender;

-- Behavioral tags → BSI
INSERT INTO bsi_gmv
SELECT bsi_build(array_agg(b.encode_uid), array_agg(a.gmv)) AS bitmap
FROM usershop_behavior a JOIN dws_uid_dict b ON a.uid = b.uid;
```

### Limitations

- All BSI/Roaring Bitmap data stored in a single row → concentrates on few compute nodes
- No time dimension → cannot query by date range
- No category dimension → cannot filter by business category

---

## Advanced Pattern (With Bucketing)

Solves data concentration by distributing data across multiple buckets for parallel computation.

### When to Use

- User base > 10 million
- Need to query by time range or category
- Cluster has multiple compute nodes that should be utilized

### DDL

```sql
-- User attribute source table (same as basic)
CREATE TABLE dws_userbase (
    uid int NOT NULL PRIMARY KEY,
    province text,
    gender text
) WITH (
    distribution_key = 'uid'
);

-- UID dictionary encoding table (same as basic)
CREATE TABLE dws_uid_dict (
    encode_uid serial,
    uid int PRIMARY KEY
);

-- User behavioral tag source table (with category and date)
CREATE TABLE usershop_behavior (
    uid int NOT NULL,
    category text,
    gmv int,
    ds date
) WITH (
    distribution_key = 'uid'
);

-- Roaring Bitmap attribute tag table (with bucket)
CREATE TABLE rb_tag (
    tag_name text,
    tag_val text,
    bucket int,
    bitmap roaringbitmap
) WITH (
    distribution_key = 'bucket'
);

-- BSI behavioral tag table (with bucket, category, date)
CREATE TABLE bsi_gmv (
    category text,
    bucket int,
    gmv_bsi bsi,
    ds date
) WITH (
    distribution_key = 'bucket'
);
```

### Key Design Decisions

| Decision | Recommendation | Rationale |
|----------|---------------|-----------|
| Bucket count | 65536 (use `encode_uid / 65536`) | Balances parallelism and overhead |
| `distribution_key` | `bucket` | Ensures same bucket data on same node for local joins |
| Time partitioning | `ds` column in BSI table | Enables date range queries |
| Category dimension | `category` column | Supports per-category analysis |

### Import SQL

```sql
-- Attribute tags → Roaring Bitmap with bucketing
INSERT INTO rb_tag
SELECT 'province', province, encode_uid / 65536 AS bucket,
    rb_build_agg(b.encode_uid) AS bitmap
FROM dws_userbase a JOIN dws_uid_dict b ON a.uid = b.uid
GROUP BY province, bucket;

INSERT INTO rb_tag
SELECT 'gender', gender, encode_uid / 65536 AS bucket,
    rb_build_agg(b.encode_uid) AS bitmap
FROM dws_userbase a JOIN dws_uid_dict b ON a.uid = b.uid
GROUP BY gender, bucket;

-- Behavioral tags → BSI with bucketing
INSERT INTO bsi_gmv
SELECT a.category, b.encode_uid / 65536 AS bucket,
    bsi_build(array_agg(b.encode_uid), array_agg(a.gmv)) AS bitmap, a.ds
FROM usershop_behavior a JOIN dws_uid_dict b ON a.uid = b.uid
WHERE ds = CURRENT_DATE - interval '1 day'
GROUP BY category, bucket, ds;
```

### Query Pattern Differences

With bucketing, queries must:
1. Join `rb_tag` and `bsi_gmv` on `bucket` column
2. Use `bsi_add_agg()` to aggregate BSI across buckets before analysis

```sql
-- Basic: direct bsi_sum on single-row BSI
SELECT bsi_sum(gmv_bsi, crowd) FROM bsi_gmv, (...crowd...) t;

-- Bucketed: aggregate across buckets first, then sum
SELECT sum(kv[1]) AS total_gmv, sum(kv[1]) / sum(kv[2]) AS avg_gmv
FROM (
    SELECT bsi_sum(t1.gmv_bsi, t2.crowd) AS kv, t1.bucket
    FROM (SELECT gmv_bsi, bucket FROM bsi_gmv WHERE ...) t1
    JOIN (SELECT crowd, bucket FROM ...) t2 ON t1.bucket = t2.bucket
) t;
```

---

## Extending for Multiple Behavioral Tags

To track multiple behavioral tags (e.g., GMV, PV, order count), create a separate BSI table per tag:

```sql
-- GMV BSI table
CREATE TABLE bsi_gmv (
    category text,
    bucket int,
    gmv_bsi bsi,
    ds date
) WITH (distribution_key = 'bucket');

-- PV BSI table
CREATE TABLE bsi_pv (
    category text,
    bucket int,
    pv_bsi bsi,
    ds date
) WITH (distribution_key = 'bucket');

-- Order count BSI table
CREATE TABLE bsi_order_cnt (
    category text,
    bucket int,
    order_cnt_bsi bsi,
    ds date
) WITH (distribution_key = 'bucket');
```

Each BSI table follows the same import and query patterns, just with different source columns and BSI column names.

---

## UID Dictionary Encoding

The `dws_uid_dict` table maps original UIDs to contiguous integers (`encode_uid`), which is required because:
- Roaring Bitmap operates on integer keys
- BSI operates on integer keys
- Contiguous encoding minimizes memory/storage

### Building the Dictionary

```sql
-- Initial population
INSERT INTO dws_uid_dict (uid)
SELECT DISTINCT uid FROM dws_userbase;

-- Incremental: add new UIDs not yet in dictionary
INSERT INTO dws_uid_dict (uid)
SELECT DISTINCT uid FROM new_user_table
WHERE uid NOT IN (SELECT uid FROM dws_uid_dict);
```

> **Note**: Dictionary maintenance requires custom ETL logic and cannot be fully automated via CLI. Consider using a scheduling tool (e.g., DataWorks) for incremental updates.