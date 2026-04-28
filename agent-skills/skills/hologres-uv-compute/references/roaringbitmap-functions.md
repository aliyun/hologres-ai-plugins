# RoaringBitmap Function Reference

Complete function reference for RoaringBitmap operations in Hologres.

## Prerequisites

```sql
CREATE EXTENSION IF NOT EXISTS roaringbitmap;
```

## Aggregate Functions

These functions aggregate multiple rows into a single bitmap.

### RB_BUILD_AGG

Build a bitmap from an integer column across rows.

```sql
-- Syntax
RB_BUILD_AGG(integer_column) → roaringbitmap

-- Example: aggregate all UIDs into one bitmap
SELECT RB_BUILD_AGG(uid) AS user_bitmap
FROM ods_app_detail
WHERE ymd = '20251223';
```

**Notes:**
- Input must be `int4` (integer). For `bigint`, use `RB_BUILD_AGG_INT8`.
- NULL values are ignored.
- Supported in Dynamic Table incremental refresh.

### RB_OR_AGG

Merge (union) multiple bitmaps. Result contains all distinct elements from all input bitmaps.

```sql
-- Syntax
RB_OR_AGG(roaringbitmap_column) → roaringbitmap

-- Example: merge daily bitmaps for monthly UV
SELECT RB_CARDINALITY(RB_OR_AGG(rb_uid)) AS monthly_uv
FROM dt_dws_app_rb
WHERE ymd >= '20251201' AND ymd <= '20251231';
```

**Use case:** Cross-day/week/month UV deduplication.

### RB_AND_AGG

Intersect multiple bitmaps. Result contains only elements present in ALL input bitmaps.

```sql
-- Syntax
RB_AND_AGG(roaringbitmap_column) → roaringbitmap

-- Example: users who visited EVERY day in a week
SELECT RB_CARDINALITY(RB_AND_AGG(rb_uid)) AS daily_active_users
FROM dt_dws_app_rb
WHERE ymd >= '20251223' AND ymd <= '20251229';
```

**Use case:** Retention analysis — find users present across all periods.

## Scalar Functions (Two-Bitmap Operations)

### RB_OR

Union two bitmaps.

```sql
-- Syntax
RB_OR(roaringbitmap, roaringbitmap) → roaringbitmap

-- Example
SELECT RB_CARDINALITY(RB_OR(bitmap_day1, bitmap_day2)) AS two_day_uv;
```

### RB_AND

Intersect two bitmaps.

```sql
-- Syntax
RB_AND(roaringbitmap, roaringbitmap) → roaringbitmap

-- Example: users in both groups
SELECT RB_CARDINALITY(RB_AND(group_a_bitmap, group_b_bitmap)) AS overlap;
```

### RB_ANDNOT

Difference — elements in the first bitmap but NOT in the second.

```sql
-- Syntax
RB_ANDNOT(roaringbitmap, roaringbitmap) → roaringbitmap

-- Example: new users today (in today but not in yesterday)
SELECT RB_CARDINALITY(RB_ANDNOT(today_bitmap, yesterday_bitmap)) AS new_users;
```

### RB_XOR

Symmetric difference — elements in either bitmap but not both.

```sql
-- Syntax
RB_XOR(roaringbitmap, roaringbitmap) → roaringbitmap
```

## Cardinality & Inspection

### RB_CARDINALITY

Count distinct elements in a bitmap.

```sql
-- Syntax
RB_CARDINALITY(roaringbitmap) → bigint

-- Example
SELECT RB_CARDINALITY(RB_OR_AGG(rb_uid)) AS uv
FROM dt_dws_app_rb
WHERE ymd = '20251223';
```

### RB_IS_EMPTY

Check if a bitmap has no elements.

```sql
-- Syntax
RB_IS_EMPTY(roaringbitmap) → boolean
```

### RB_CONTAINS

Check if a bitmap contains a specific integer value.

```sql
-- Syntax
RB_CONTAINS(roaringbitmap, integer) → boolean

-- Example: check if user 12345 is in the bitmap
SELECT RB_CONTAINS(rb_uid, 12345) FROM dt_dws_app_rb WHERE ymd = '20251223';
```

### RB_EQUALS

Check if two bitmaps are identical.

```sql
-- Syntax
RB_EQUALS(roaringbitmap, roaringbitmap) → boolean
```

### RB_INTERSECT

Check if two bitmaps share any element.

```sql
-- Syntax
RB_INTERSECT(roaringbitmap, roaringbitmap) → boolean
```

## Construction & Conversion

### RB_BUILD

Build a bitmap from an integer array.

```sql
-- Syntax
RB_BUILD(integer[]) → roaringbitmap

-- Example
SELECT RB_BUILD(ARRAY[1, 2, 3, 100, 200]);
```

### RB_TO_ARRAY

Convert a bitmap back to an integer array.

```sql
-- Syntax
RB_TO_ARRAY(roaringbitmap) → integer[]

-- Example: get all user IDs from a bitmap
SELECT RB_TO_ARRAY(rb_uid) FROM dt_dws_app_rb LIMIT 1;
```

### RB_BUILD_AGG_INT8

Build a bitmap from a `bigint` column (64-bit input). Internally splits into high/low 32-bit parts.

```sql
-- Syntax
RB_BUILD_AGG_INT8(bigint_column) → roaringbitmap
```

## UID Encoding Functions

For text-type UIDs that need integer mapping before bitmap operations.

### hg_id_encoding_int4 (V4.1+)

Auto-map text UIDs to 32-bit integers using a mapping table.

```sql
-- Syntax
hg_id_encoding_int4(text_uid, 'mapping_table_name') → integer

-- Prerequisites: mapping table with text PK + serial column
CREATE TABLE uid_mapping (
  uid text NOT NULL PRIMARY KEY,
  uid_int32 serial
);

-- Usage in Dynamic Table
SELECT RB_BUILD_AGG(hg_id_encoding_int4(device_id, 'uid_mapping')) AS uid_rb
FROM ods_events
GROUP BY dimension;
```

**Constraints:**
- Mapping table: exactly one `text` PK + one `serial` column
- Input must not be NULL
- Requires Hologres V4.1+
- Supported in incremental Dynamic Table refresh

### hg_id_encoding_int8

Same as `hg_id_encoding_int4` but maps to `bigint` (64-bit).

## Common Patterns

### UV for Flexible Date Range

```sql
-- Works for any date range: day, week, month, quarter, year
SELECT RB_CARDINALITY(RB_OR_AGG(rb_uid)) AS uv
FROM dt_dws_app_rb
WHERE ymd >= '20251201' AND ymd <= '20251231';
```

### New Users (Appeared Today, Not Yesterday)

```sql
WITH today AS (
  SELECT RB_OR_AGG(rb_uid) AS rb FROM dt_dws_app_rb WHERE ymd = '20251224'
),
yesterday AS (
  SELECT RB_OR_AGG(rb_uid) AS rb FROM dt_dws_app_rb WHERE ymd = '20251223'
)
SELECT RB_CARDINALITY(RB_ANDNOT(t.rb, y.rb)) AS new_users
FROM today t, yesterday y;
```

### User Overlap Between Two Segments

```sql
WITH segment_a AS (
  SELECT RB_OR_AGG(rb_uid) AS rb FROM dt_dws_app_rb
  WHERE country = 'CN' AND ymd = '20251223'
),
segment_b AS (
  SELECT RB_OR_AGG(rb_uid) AS rb FROM dt_dws_app_rb
  WHERE country = 'US' AND ymd = '20251223'
)
SELECT RB_CARDINALITY(RB_AND(a.rb, b.rb)) AS overlap_uv,
       RB_CARDINALITY(RB_OR(a.rb, b.rb)) AS total_uv
FROM segment_a a, segment_b b;
```
