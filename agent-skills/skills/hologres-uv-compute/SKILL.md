---
name: hologres-uv-compute
description: |
  Hologres UV/PV computation using Dynamic Tables and RoaringBitmap for real-time deduplication
  at scale. Use for building incremental UV/PV pipelines, RoaringBitmap-based user deduplication,
  flexible time-range UV aggregation, and text-to-int UID encoding for bitmap compatibility.
  Triggers: "hologres uv", "hologres pv", "roaringbitmap", "rb_build_agg", "rb_or_agg",
  "去重", "UV计算", "用户去重", "bitmap去重", "实时UV", "hg_id_encoding"
---

## Prerequisites

This skill requires **hologres-cli** to be installed first:

```bash
pip install hologres-cli
```

All SQL execution and Dynamic Table operations depend on `hologres-cli` commands (`hologres sql run --write`, `hologres dt create`).

# Hologres UV/PV Computation with Dynamic Table & RoaringBitmap

Build real-time, incremental UV/PV computation pipelines using Dynamic Tables and RoaringBitmap in Hologres. This approach supports flexible time-range aggregation over billions of records with low latency.

## Why This Approach

| Traditional COUNT DISTINCT | RoaringBitmap + Dynamic Table |
|---------------------------|-------------------------------|
| Full scan on every query | Pre-aggregated bitmaps, incremental refresh |
| Slow with high-cardinality UIDs | Compressed bitmap, sub-second UV queries |
| Cannot merge across time ranges | `RB_OR_AGG` merges bitmaps for any date range |
| Heavy resource usage | Incremental computation, minimal resources |

## Quick Start

```sql
-- 1. Enable RoaringBitmap extension
CREATE EXTENSION IF NOT EXISTS roaringbitmap;

-- 2. Create ODS detail table (source data)
BEGIN;
CREATE TABLE ods_app_detail (
  uid int,
  country text,
  prov text,
  city text,
  ymd text NOT NULL
) LOGICAL PARTITION BY LIST (ymd);
CALL set_table_property('ods_app_detail', 'orientation', 'column');
CALL set_table_property('ods_app_detail', 'distribution_key', 'uid');
CALL set_table_property('ods_app_detail', 'clustering_key', 'ymd');
CALL set_table_property('ods_app_detail', 'event_time_column', 'ymd');
CALL set_table_property('ods_app_detail', 'bitmap_columns', 'country,prov,city,ymd');
COMMIT;

-- 3. Create DWS Dynamic Table (bitmap aggregation layer)
CREATE DYNAMIC TABLE dt_dws_app_rb (
  country, prov, city, rb_uid, pv, ymd
)
LOGICAL PARTITION BY LIST (ymd)
WITH (
  freshness = '5 minutes',
  auto_refresh_mode = 'incremental',
  auto_refresh_partition_active_time = '2 days',
  partition_key_time_format = 'YYYYMMDD'
)
AS
SELECT country, prov, city,
       RB_BUILD_AGG(uid) AS rb_uid,
       COUNT(1) AS pv,
       ymd
FROM ods_app_detail
GROUP BY country, prov, city, ymd;

-- 4. Query UV/PV for a single day
SELECT country, prov, city,
       RB_CARDINALITY(RB_OR_AGG(rb_uid)) AS uv,
       SUM(pv) AS pv
FROM dt_dws_app_rb
WHERE ymd = '20251223'
GROUP BY country, prov, city;
```

## Architecture Overview

```
ODS (Detail)                DWS (Bitmap Aggregation)         Query
┌─────────────┐  Dynamic   ┌──────────────────────┐    ┌─────────────┐
│ods_app_detail│──Table────>│ dt_dws_app_rb        │───>│ RB_OR_AGG   │
│  uid, dims,  │ incremental│  rb_uid (bitmap),    │    │ + CARDINALITY│
│  ymd         │  refresh   │  pv, dims, ymd       │    │ = UV for any │
└─────────────┘            └──────────────────────┘    │ time range  │
                                                       └─────────────┘
```

**Data flow:**
1. Raw events flow into `ods_app_detail` (partitioned by day)
2. Dynamic Table `dt_dws_app_rb` incrementally aggregates UIDs into bitmaps per dimension per day
3. Queries merge bitmaps across any date range using `RB_OR_AGG` for exact UV

## ODS Detail Table Design

The source table stores raw event data, partitioned by date.

```sql
BEGIN;
CREATE TABLE ods_app_detail (
  uid int,
  country text,
  prov text,
  city text,
  ymd text NOT NULL
) LOGICAL PARTITION BY LIST (ymd);

CALL set_table_property('ods_app_detail', 'orientation', 'column');
CALL set_table_property('ods_app_detail', 'distribution_key', 'uid');
CALL set_table_property('ods_app_detail', 'clustering_key', 'ymd');
CALL set_table_property('ods_app_detail', 'event_time_column', 'ymd');
CALL set_table_property('ods_app_detail', 'bitmap_columns', 'country,prov,city,ymd');
COMMIT;
```

**Key design choices:**

| Property | Value | Reason |
|----------|-------|--------|
| `orientation` | `column` | Columnar storage for analytical queries |
| `distribution_key` | `uid` | Distribute by user for aggregation locality |
| `clustering_key` | `ymd` | Optimize time-range scans |
| `event_time_column` | `ymd` | Segment key for partition pruning |
| `bitmap_columns` | dimension columns | Accelerate dimension filtering |

## DWS Dynamic Table (Bitmap Aggregation)

The Dynamic Table pre-aggregates UIDs into RoaringBitmaps per dimension per day using incremental refresh.

```sql
CREATE DYNAMIC TABLE dt_dws_app_rb (
  country, prov, city, rb_uid, pv, ymd
)
LOGICAL PARTITION BY LIST (ymd)
WITH (
  freshness = '5 minutes',
  auto_refresh_mode = 'incremental',
  auto_refresh_partition_active_time = '2 days',
  partition_key_time_format = 'YYYYMMDD'
)
AS
SELECT country, prov, city,
       RB_BUILD_AGG(uid) AS rb_uid,
       COUNT(1) AS pv,
       ymd
FROM ods_app_detail
GROUP BY country, prov, city, ymd;
```

**Key Dynamic Table parameters:**

| Parameter | Value | Description |
|-----------|-------|-------------|
| `freshness` | `5 minutes` | Target data freshness |
| `auto_refresh_mode` | `incremental` | Only compute new/changed data |
| `auto_refresh_partition_active_time` | `2 days` | Only auto-refresh recent 2 days |
| `partition_key_time_format` | `YYYYMMDD` | Parse partition key as date |

### Refresh Historical Partitions

Auto-refresh only covers active partitions. For historical data, trigger manually:

```sql
-- Full refresh a specific partition
REFRESH DYNAMIC TABLE dt_dws_app_rb
  PARTITION(20251201)
  WITH (refresh_mode = 'full');

-- Full refresh a date range (one by one)
REFRESH DYNAMIC TABLE dt_dws_app_rb
  PARTITION(20251201)
  WITH (refresh_mode = 'full');
```

## UV/PV Queries

### Single Day

```sql
SELECT country, prov, city,
       RB_CARDINALITY(RB_OR_AGG(rb_uid)) AS uv,
       SUM(pv) AS pv
FROM dt_dws_app_rb
WHERE ymd = '20251223'
GROUP BY country, prov, city;
```

### Date Range (e.g., Monthly)

```sql
SELECT country, prov, city,
       RB_CARDINALITY(RB_OR_AGG(rb_uid)) AS uv,
       SUM(pv) AS pv
FROM dt_dws_app_rb
WHERE ymd >= '20251201' AND ymd <= '20251231'
GROUP BY country, prov, city;
```

### Global UV (All Dimensions)

```sql
SELECT RB_CARDINALITY(RB_OR_AGG(rb_uid)) AS total_uv,
       SUM(pv) AS total_pv
FROM dt_dws_app_rb
WHERE ymd >= '20251201' AND ymd <= '20251231';
```

**How it works:** `RB_OR_AGG` merges daily bitmaps with bitwise OR — a user appearing on multiple days is counted only once. `RB_CARDINALITY` returns the count of distinct bits (= distinct users).

## Text UID Encoding

When UIDs are `text` type (e.g., device IDs, UUIDs), they must be mapped to integers for RoaringBitmap. Two approaches:

### Approach 1: Mapping Table (Manual)

```sql
-- Create mapping table
BEGIN;
CREATE TABLE uid_mapping (
  uid text NOT NULL,
  uid_int32 serial,
  PRIMARY KEY (uid)
);
CALL set_table_property('uid_mapping', 'orientation', 'row');
CALL set_table_property('uid_mapping', 'distribution_key', 'uid');
CALL set_table_property('uid_mapping', 'clustering_key', 'uid');
COMMIT;

-- Use in Dynamic Table
CREATE DYNAMIC TABLE dt_dws_app_rb (...)
AS
SELECT country, prov, city,
       RB_BUILD_AGG(m.uid_int32) AS uid_rb,
       COUNT(1) AS pv, ymd
FROM ods_app_detail o
JOIN uid_mapping m ON o.uid_text = m.uid
GROUP BY country, prov, city, ymd;
```

### Approach 2: hg_id_encoding (V4.1+, Recommended)

Built-in function that auto-manages the mapping table.

```sql
-- Create mapping table (single text PK + one serial column)
BEGIN;
CREATE TABLE uid_mapping (
  uid text NOT NULL,
  uid_int32 serial,
  PRIMARY KEY (uid)
);
CALL set_table_property('uid_mapping', 'orientation', 'row');
CALL set_table_property('uid_mapping', 'distribution_key', 'uid');
COMMIT;

-- Use hg_id_encoding_int4 in Dynamic Table query
CREATE DYNAMIC TABLE dt_dws_app_rb (...)
AS
SELECT country, prov, city,
       RB_BUILD_AGG(hg_id_encoding_int4(uid_text, 'uid_mapping')) AS uid_rb,
       COUNT(1) AS pv, ymd
FROM ods_app_detail
GROUP BY country, prov, city, ymd;
```

**Constraints for `hg_id_encoding_int4`:**
- Mapping table must have exactly: one `text` PK column + one `serial` column
- Input UID must not be NULL
- Requires Hologres V4.1+
- Supports incremental refresh in Dynamic Tables

## Core RoaringBitmap Functions

| Function | Description | Example |
|----------|-------------|---------|
| `RB_BUILD_AGG(int)` | Aggregate integers into a bitmap | `RB_BUILD_AGG(uid)` |
| `RB_OR_AGG(roaringbitmap)` | Merge bitmaps (union / deduplicate) | `RB_OR_AGG(rb_uid)` |
| `RB_AND_AGG(roaringbitmap)` | Intersect bitmaps (common users) | `RB_AND_AGG(rb_uid)` |
| `RB_CARDINALITY(roaringbitmap)` | Count distinct elements in bitmap | `RB_CARDINALITY(rb)` |
| `RB_OR(rb, rb)` | Union two bitmaps | `RB_OR(a, b)` |
| `RB_AND(rb, rb)` | Intersect two bitmaps | `RB_AND(a, b)` |
| `RB_ANDNOT(rb, rb)` | Difference (in A but not in B) | `RB_ANDNOT(a, b)` |
| `RB_TO_ARRAY(roaringbitmap)` | Convert bitmap to integer array | `RB_TO_ARRAY(rb)` |
| `RB_BUILD(int[])` | Build bitmap from integer array | `RB_BUILD(ARRAY[1,2,3])` |
| `RB_CONTAINS(rb, int)` | Check if bitmap contains a value | `RB_CONTAINS(rb, 42)` |
| `RB_IS_EMPTY(roaringbitmap)` | Check if bitmap is empty | `RB_IS_EMPTY(rb)` |

For complete function reference, see [references/roaringbitmap-functions.md](references/roaringbitmap-functions.md).

## References

| Document | Content |
|----------|---------|
| [roaringbitmap-functions.md](references/roaringbitmap-functions.md) | Complete RoaringBitmap function reference |
| [dynamic-table-patterns.md](references/dynamic-table-patterns.md) | Dynamic Table configuration patterns for UV |
| [advanced-scenarios.md](references/advanced-scenarios.md) | Advanced UV scenarios: retention, funnel, cross-platform |

## Best Practices

1. **Always use `LOGICAL PARTITION BY LIST (ymd)`** on both ODS and DWS tables for time-range partition pruning
2. **Set `auto_refresh_mode = 'incremental'`** to avoid recomputing all data on each refresh
3. **Configure `auto_refresh_partition_active_time`** to limit auto-refresh to recent partitions only
4. **Manually refresh historical partitions** with `REFRESH DYNAMIC TABLE ... PARTITION(...) WITH (refresh_mode = 'full')`
5. **Use `RB_OR_AGG` for cross-day UV** — it merges daily bitmaps for exact deduplication over any date range
6. **For text UIDs, use `hg_id_encoding_int4`** (V4.1+) instead of manual mapping tables
7. **Set `distribution_key = 'uid'`** on ODS table for aggregation locality
8. **Install extension first** — `CREATE EXTENSION IF NOT EXISTS roaringbitmap` before any bitmap operations
