# Advanced UV Scenarios

Advanced use cases beyond basic UV/PV: retention analysis, new/lost user tracking, multi-platform dedup, and funnel analysis using RoaringBitmap.

## Retention Analysis

Calculate day-N retention using bitmap intersection.

### Day-1 Retention

```sql
WITH day0 AS (
  SELECT RB_OR_AGG(rb_uid) AS rb
  FROM dt_dws_app_rb WHERE ymd = '20251223'
),
day1 AS (
  SELECT RB_OR_AGG(rb_uid) AS rb
  FROM dt_dws_app_rb WHERE ymd = '20251224'
)
SELECT
  RB_CARDINALITY(d0.rb) AS day0_uv,
  RB_CARDINALITY(RB_AND(d0.rb, d1.rb)) AS retained,
  ROUND(RB_CARDINALITY(RB_AND(d0.rb, d1.rb))::numeric
        / NULLIF(RB_CARDINALITY(d0.rb), 0) * 100, 2) AS retention_pct
FROM day0 d0, day1 d1;
```

### Multi-Day Retention (Day 1, 3, 7, 30)

```sql
WITH base AS (
  SELECT RB_OR_AGG(rb_uid) AS rb
  FROM dt_dws_app_rb WHERE ymd = '20251201'
)
SELECT
  RB_CARDINALITY(b.rb) AS base_uv,
  RB_CARDINALITY(RB_AND(b.rb, (SELECT RB_OR_AGG(rb_uid) FROM dt_dws_app_rb WHERE ymd = '20251202'))) AS d1,
  RB_CARDINALITY(RB_AND(b.rb, (SELECT RB_OR_AGG(rb_uid) FROM dt_dws_app_rb WHERE ymd = '20251204'))) AS d3,
  RB_CARDINALITY(RB_AND(b.rb, (SELECT RB_OR_AGG(rb_uid) FROM dt_dws_app_rb WHERE ymd = '20251208'))) AS d7,
  RB_CARDINALITY(RB_AND(b.rb, (SELECT RB_OR_AGG(rb_uid) FROM dt_dws_app_rb WHERE ymd = '20251231'))) AS d30
FROM base b;
```

## New User & Lost User Analysis

### New Users (First Appearance)

Users who appeared in current period but not in previous period.

```sql
WITH current_period AS (
  SELECT RB_OR_AGG(rb_uid) AS rb
  FROM dt_dws_app_rb
  WHERE ymd >= '20251224' AND ymd <= '20251230'
),
previous_period AS (
  SELECT RB_OR_AGG(rb_uid) AS rb
  FROM dt_dws_app_rb
  WHERE ymd >= '20251217' AND ymd <= '20251223'
)
SELECT RB_CARDINALITY(RB_ANDNOT(c.rb, p.rb)) AS new_users
FROM current_period c, previous_period p;
```

### Lost Users (Churned)

Users who appeared in previous period but not in current period.

```sql
WITH current_period AS (
  SELECT RB_OR_AGG(rb_uid) AS rb
  FROM dt_dws_app_rb
  WHERE ymd >= '20251224' AND ymd <= '20251230'
),
previous_period AS (
  SELECT RB_OR_AGG(rb_uid) AS rb
  FROM dt_dws_app_rb
  WHERE ymd >= '20251217' AND ymd <= '20251223'
)
SELECT RB_CARDINALITY(RB_ANDNOT(p.rb, c.rb)) AS lost_users
FROM current_period c, previous_period p;
```

## Segment Overlap Analysis

Compare user overlap between dimensions (e.g., countries, channels).

```sql
WITH segment_cn AS (
  SELECT RB_OR_AGG(rb_uid) AS rb
  FROM dt_dws_app_rb
  WHERE country = 'CN' AND ymd = '20251223'
),
segment_us AS (
  SELECT RB_OR_AGG(rb_uid) AS rb
  FROM dt_dws_app_rb
  WHERE country = 'US' AND ymd = '20251223'
)
SELECT
  RB_CARDINALITY(a.rb) AS cn_uv,
  RB_CARDINALITY(b.rb) AS us_uv,
  RB_CARDINALITY(RB_AND(a.rb, b.rb)) AS overlap,
  RB_CARDINALITY(RB_OR(a.rb, b.rb)) AS union_uv,
  ROUND(RB_CARDINALITY(RB_AND(a.rb, b.rb))::numeric
        / NULLIF(RB_CARDINALITY(RB_OR(a.rb, b.rb)), 0) * 100, 2)
    AS overlap_pct
FROM segment_cn a, segment_us b;
```

## Multi-Dimension UV in One Query

Calculate UV per dimension while also computing total UV across all dimensions.

```sql
-- Per-country UV + total UV
SELECT
  COALESCE(country, 'TOTAL') AS country,
  RB_CARDINALITY(RB_OR_AGG(rb_uid)) AS uv,
  SUM(pv) AS pv
FROM dt_dws_app_rb
WHERE ymd >= '20251201' AND ymd <= '20251231'
GROUP BY ROLLUP(country)
ORDER BY uv DESC;
```

## Multiple Bitmap Columns

For more complex scenarios, store multiple bitmaps in one Dynamic Table.

```sql
-- Track both active users and paying users
CREATE DYNAMIC TABLE dt_dws_user_segments (
  ymd, country,
  rb_all_users, rb_paying_users,
  pv, pay_count
)
LOGICAL PARTITION BY LIST (ymd)
WITH (
  freshness = '5 minutes',
  auto_refresh_mode = 'incremental',
  auto_refresh_partition_active_time = '2 days',
  partition_key_time_format = 'YYYYMMDD'
)
AS
SELECT ymd, country,
       RB_BUILD_AGG(uid) AS rb_all_users,
       RB_BUILD_AGG(CASE WHEN is_paying THEN uid ELSE NULL END) AS rb_paying_users,
       COUNT(1) AS pv,
       SUM(CASE WHEN is_paying THEN 1 ELSE 0 END) AS pay_count
FROM ods_user_events
GROUP BY ymd, country;

-- Query: paying user conversion rate
SELECT country,
       RB_CARDINALITY(RB_OR_AGG(rb_all_users)) AS total_uv,
       RB_CARDINALITY(RB_OR_AGG(rb_paying_users)) AS paying_uv,
       ROUND(RB_CARDINALITY(RB_OR_AGG(rb_paying_users))::numeric
             / NULLIF(RB_CARDINALITY(RB_OR_AGG(rb_all_users)), 0) * 100, 2)
         AS conversion_pct
FROM dt_dws_user_segments
WHERE ymd >= '20251201' AND ymd <= '20251231'
GROUP BY country;
```

## Performance Tips

| Tip | Description |
|-----|-------------|
| Minimize GROUP BY dimensions | Fewer dimensions = fewer bitmap rows = faster merge |
| Filter before merge | Use WHERE to reduce partitions scanned before `RB_OR_AGG` |
| Use `LOGICAL PARTITION` | Enables partition pruning for time-range queries |
| Avoid `RB_TO_ARRAY` on large bitmaps | Converting millions of IDs to arrays is expensive |
| Pre-aggregate at coarser granularity | If only country-level UV is needed, don't include city in DWS |
