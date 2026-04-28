# Dynamic Table Configuration Patterns for UV

Configuration patterns and best practices for Dynamic Tables in UV/PV computation pipelines.

## Basic Configuration

### Minimal DWS Table

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

### Key Parameter Reference

| Parameter | Description | Recommended |
|-----------|-------------|-------------|
| `freshness` | How fresh data should be | `5 minutes` for near-real-time, `1 hours` for batch |
| `auto_refresh_mode` | Refresh strategy | `incremental` — only new data |
| `auto_refresh_partition_active_time` | Auto-refresh window | `2 days` — only refresh recent partitions |
| `partition_key_time_format` | Parse format for partition key | `YYYYMMDD`, `YYYY-MM-DD`, `YYYYMMDDHH24` |

## Freshness Tuning

Choose freshness based on business requirements:

| Scenario | Freshness | Trade-off |
|----------|-----------|-----------|
| Real-time dashboard | `1 minutes` | Higher compute cost |
| Near-real-time reporting | `5 minutes` | Balanced |
| Hourly batch | `1 hours` | Lower cost |
| Daily batch | `24 hours` | Minimal cost |

## Partition Active Time

Controls which partitions are auto-refreshed. Older partitions are NOT refreshed automatically.

```sql
-- Only auto-refresh last 2 days
auto_refresh_partition_active_time = '2 days'

-- Auto-refresh last 7 days
auto_refresh_partition_active_time = '7 days'
```

**Rule of thumb:** Set to cover the typical data correction window plus one day buffer.

## Historical Partition Refresh

Partitions outside `auto_refresh_partition_active_time` need manual refresh:

```sql
-- Refresh a single partition (full mode required for historical)
REFRESH DYNAMIC TABLE dt_dws_app_rb
  PARTITION(20251201)
  WITH (refresh_mode = 'full');

-- Refresh with OVERWRITE (replace existing data)
REFRESH OVERWRITE DYNAMIC TABLE dt_dws_app_rb
  PARTITION(20251201)
  WITH (refresh_mode = 'full');
```

## Storage Optimization

### Column Properties

```sql
CREATE DYNAMIC TABLE dt_dws_app_rb (...)
WITH (
  freshness = '5 minutes',
  auto_refresh_mode = 'incremental',
  auto_refresh_partition_active_time = '2 days',
  partition_key_time_format = 'YYYYMMDD',
  -- Storage optimization
  orientation = 'column',
  distribution_key = 'country',
  clustering_key = 'ymd',
  bitmap_columns = 'country,prov,city'
)
AS ...;
```

| Property | Recommendation | Reason |
|----------|---------------|--------|
| `orientation` | `column` | UV queries scan dimension columns |
| `distribution_key` | Primary GROUP BY dimension | Reduce shuffle |
| `clustering_key` | `ymd` | Optimize date-range filter |
| `bitmap_columns` | Dimension columns | Accelerate WHERE filters |

## Computing Resource Options

```sql
-- Use local compute (default)
computing_resource = 'local'

-- Use serverless compute (no impact on online queries)
computing_resource = 'serverless'

-- Use a specific warehouse
computing_resource = 'my_warehouse'
```

**Recommendation:** Use `serverless` for large DWS tables to isolate refresh load from query workload.

## Multi-Layer Pipeline

For complex scenarios, chain multiple Dynamic Tables:

```
ODS (detail) → DWD (cleaned) → DWS (bitmap agg) → Query
```

### DWD Layer (Optional Cleaning)

```sql
CREATE DYNAMIC TABLE dt_dwd_app_clean (...)
WITH (freshness = '3 minutes', auto_refresh_mode = 'incremental', ...)
AS
SELECT uid, country, prov, city, ymd
FROM ods_app_detail
WHERE uid IS NOT NULL AND country IS NOT NULL;
```

### DWS Layer (Bitmap Aggregation)

```sql
CREATE DYNAMIC TABLE dt_dws_app_rb (...)
WITH (freshness = '5 minutes', auto_refresh_mode = 'incremental', ...)
AS
SELECT country, prov, city,
       RB_BUILD_AGG(uid) AS rb_uid,
       COUNT(1) AS pv, ymd
FROM dt_dwd_app_clean
GROUP BY country, prov, city, ymd;
```

## Monitoring Refresh Status

```sql
-- Check Dynamic Table properties and refresh info
SELECT * FROM hologres.hg_dynamic_table_properties
WHERE table_name = 'dt_dws_app_rb';

-- Using CLI
-- hologres dt show dt_dws_app_rb
-- hologres dt list
```

## Troubleshooting

| Issue | Cause | Solution |
|-------|-------|----------|
| Historical partition has no data | Not auto-refreshed | `REFRESH DYNAMIC TABLE ... PARTITION(...) WITH (refresh_mode = 'full')` |
| Refresh taking too long | Too many active partitions | Reduce `auto_refresh_partition_active_time` |
| Incremental refresh fails | Unsupported function used | Check [supported functions list](https://help.aliyun.com/zh/hologres/user-guide/supported-functions-for-incremental-refresh) |
| Data freshness not met | Compute resource insufficient | Switch to `serverless` or increase warehouse capacity |
