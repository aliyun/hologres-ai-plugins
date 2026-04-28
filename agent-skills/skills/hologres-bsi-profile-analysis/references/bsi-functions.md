# BSI Function Reference

Complete reference for Hologres BSI (Bit-sliced Index) functions. Requires `CREATE EXTENSION bsi` to be installed first.

## BSI Construction Functions

### bsi_build

Create a BSI from two arrays (keys and values).

```
bsi_build(integer[], bigint[]) → bsi
```

```sql
SELECT bsi_iterate(bsi_build('{1,2,3}', '{2,4,6}'));
-- Result:
-- {1,2}
-- {2,4}
-- {3,6}
```

### bsi_add_value

Add a single key-value pair to an existing BSI.

```
bsi_add_value(bsi, integer, bigint) → bsi
```

```sql
SELECT bsi_iterate(bsi_add_value(bsi_build('{1,2,3}', '{2,4,6}'), 4, 8));
-- Result:
-- {1,2} {2,4} {3,6} {4,8}
```

## BSI Expansion Functions

### bsi_iterate

Expand a BSI into individual key-value pairs.

```
bsi_iterate(bsi) → set of integer[]
```

```sql
SELECT bsi_iterate(bsi_build('{1,2,3}', '{2,4,6}'));
-- Result:
-- {1,2}
-- {2,4}
-- {3,6}
```

### bsi_show

Show the first N key-value pairs from a BSI.

```
bsi_show(bsi/bytea, integer) → text
```

```sql
SELECT bsi_show(bsi_build('{1,2,3}', '{2,4,6}'), 2);
-- Result: 1=2,2=4...left 1
```

## BSI Query Functions

### bsi_ebm

Get all keys in a BSI as a Roaring Bitmap.

```
bsi_ebm(bsi/bytea) → roaringbitmap
```

```sql
SELECT rb_to_array(bsi_ebm(bsi_build('{1,2,3}', '{2,4,6}')));
-- Result: {1,2,3}
```

### bsi_eq

Get keys where value equals a specified number.

```
bsi_eq(bsi, bigint [, bytea]) → roaringbitmap
```

Optional `bytea` parameter: Roaring Bitmap to intersect before comparison.

```sql
SELECT rb_to_array(bsi_eq(bsi_build('{1,2,3,4}', '{2,4,4,8}'), 4));
-- Result: {2,3}
```

### bsi_neq

Get keys where value does not equal a specified number.

```
bsi_neq(bsi, bigint [, bytea]) → roaringbitmap
```

```sql
SELECT rb_to_array(bsi_neq(bsi_build('{1,2,3,4}', '{2,4,4,8}'), 4));
-- Result: {1,4}
```

### bsi_gt

Get keys where value is greater than a specified number.

```
bsi_gt(bsi, bigint [, bytea]) → roaringbitmap
```

```sql
SELECT rb_to_array(bsi_gt(bsi_build('{1,2,3,4}', '{2,4,4,8}'), 4));
-- Result: {4}
```

### bsi_ge

Get keys where value is greater than or equal to a specified number.

```
bsi_ge(bsi, bigint [, bytea]) → roaringbitmap
```

```sql
SELECT rb_to_array(bsi_ge(bsi_build('{1,2,3,4}', '{2,4,4,8}'), 4));
-- Result: {2,3,4}
```

### bsi_lt

Get keys where value is less than a specified number.

```
bsi_lt(bsi, bigint [, bytea]) → roaringbitmap
```

```sql
SELECT rb_to_array(bsi_lt(bsi_build('{1,2,3,4}', '{2,4,4,8}'), 4));
-- Result: {1}
```

### bsi_le

Get keys where value is less than or equal to a specified number.

```
bsi_le(bsi, bigint [, bytea]) → roaringbitmap
```

```sql
SELECT rb_to_array(bsi_le(bsi_build('{1,2,3,4}', '{2,4,4,8}'), 4));
-- Result: {1,2,3}
```

### bsi_range

Get keys where value falls within a closed interval [low, high].

```
bsi_range(bsi, bigint, bigint [, bytea]) → roaringbitmap
```

```sql
SELECT rb_to_array(bsi_range(bsi_build('{1,2,3,4}', '{2,4,4,8}'), 3, 5));
-- Result: {2,3}
```

### bsi_compare

Generic comparison filter function.

```
bsi_compare(text, bsi, [bytea,] bigint, bigint) → roaringbitmap
```

Supported comparison types: `LT`, `LE`, `GT`, `GE`, `EQ`, `NEQ`, `RANGE`.

- For `RANGE`, two `bigint` values are required (lower and upper bounds).
- For all other types, only one `bigint` value is required.

```sql
SELECT rb_to_array(bsi_compare('RANGE', bsi_build('{1,2,3,4}', '{2,4,4,8}'), 3, 5));
-- Result: {2,3}
```

### bsi_filter

Filter a BSI by intersecting its keys with a Roaring Bitmap. Returns a new BSI.

```
bsi_filter(bsi/bytea, bytea) → bsi
```

```sql
SELECT bsi_iterate(bsi_filter(bsi_build('{1,2,3}', '{2,4,6}'), rb_build('{1,2}')));
-- Result:
-- {1,2}
-- {2,4}
```

## BSI Aggregate Analysis Functions

### bsi_sum

Compute sum of values and cardinality (count of keys). Returns `[sum, cardinality]`.

```
bsi_sum(bsi/bytea [, bytea]) → bigint[]
```

Optional `bytea` parameter: Roaring Bitmap to intersect before computing.

```sql
SELECT bsi_sum(bsi_build('{1,2,3,4}', '{2,4,6,8}'));
-- Result: {20,4}  → sum=20, count=4
```

Usage in profile analysis:
```sql
-- Total GMV and per-capita GMV for a segmented audience
SELECT sum(kv[1]) AS total_gmv, sum(kv[1]) / sum(kv[2]) AS avg_gmv
FROM (
    SELECT bsi_sum(gmv_bsi, crowd) AS kv
    FROM bsi_gmv, (SELECT rb_and(a.bitmap, b.bitmap) AS crowd FROM ...) t
) t;
```

### bsi_stat

Compute distribution statistics by boundary values. Returns interval counts.

```
bsi_stat(bigint[], bsi/bytea [, bytea]) → text
```

- First parameter: boundary values array defining the intervals.
- Optional third parameter: Roaring Bitmap to intersect before computing.

```sql
SELECT bsi_stat('{1,3,5}', bsi_build('{1,2,3,4}', '{2,4,6,8}'));
-- Result: (0,1]=0;(1,3]=1;(3,5]=1;(5,8]=2
```

### bsi_topk

Get top K keys with the largest values.

```
bsi_topk(bsi/bytea, [bytea,] integer) → roaringbitmap
```

Optional `bytea` parameter (second positional): Roaring Bitmap to intersect before computing.

```sql
SELECT rb_to_array(bsi_topk(bsi_build('{1,2,3,4,5}', '{2,4,6,8,10}'), 3));
-- Result: {3,4,5}
```

### bsi_transpose

Get distinct values as a Roaring Bitmap.

```
bsi_transpose(bsi/bytea [, bytea]) → roaringbitmap
```

```sql
SELECT rb_to_array(bsi_transpose(bsi_build('{1,2,3,4,5}', '{2,4,4,8,8}')));
-- Result: {2,4,8}
```

### bsi_transpose_with_count

Get distinct values with their occurrence counts as a new BSI.

```
bsi_transpose_with_count(bsi/bytea [, bytea]) → bsi
```

```sql
SELECT bsi_iterate(bsi_transpose_with_count(bsi_build('{1,2,3,4,5}', '{2,4,4,8,8}')));
-- Result:
-- {2,1}
-- {4,2}
-- {8,2}
```

## BSI Arithmetic and Merge Functions

### bsi_add

Add values of two BSI objects that share the same keys.

```
bsi_add(bsi, bsi) → bsi
```

```sql
SELECT bsi_iterate(bsi_add(bsi_build('{1,2,3}', '{2,4,6}'), bsi_build('{1,2}', '{2,4}')));
-- Result: {1,4} {2,8} {3,6}
```

### bsi_add_agg

Sum aggregate function across rows. Used for bucketed BSI aggregation.

```
bsi_add_agg(bsi) → bsi
```

```sql
SELECT bsi_iterate(bsi_add_agg(bsi_build('{1,2,3}', '{2,4,6}')));
-- Result: {1,2} {2,4} {3,6}
```

### bsi_merge

Merge two BSI objects. Their keys must not overlap.

```
bsi_merge(bsi, bsi) → bsi
```

```sql
SELECT bsi_iterate(bsi_merge(bsi_build('{1,2}', '{2,4}'), bsi_build('{3,4}', '{6,8}')));
-- Result: {1,2} {2,4} {3,6} {4,8}
```

### bsi_merge_agg

Merge aggregate function across rows. Keys must not overlap across rows.

```
bsi_merge_agg(bsi) → bsi
```

```sql
SELECT bsi_iterate(bsi_merge_agg(bsi_build('{1,2,3}', '{2,4,6}')));
-- Result: {1,2} {2,4} {3,6}
```

## Companion Roaring Bitmap Functions

Commonly used alongside BSI in profile analysis scenarios.

| Function | Description |
|----------|-------------|
| `rb_build(integer[])` | Create Roaring Bitmap from integer array |
| `rb_build_agg(integer)` | Aggregate function to build Roaring Bitmap |
| `rb_and(roaringbitmap, roaringbitmap)` | Intersection of two Roaring Bitmaps |
| `rb_or(roaringbitmap, roaringbitmap)` | Union of two Roaring Bitmaps |
| `rb_to_array(roaringbitmap)` | Convert Roaring Bitmap to integer array |
| `rb_cardinality(roaringbitmap)` | Count of elements in Roaring Bitmap |

## Function Category Summary

| Category | Functions |
|----------|-----------|
| **Construction** | `bsi_build`, `bsi_add_value` |
| **Expansion** | `bsi_iterate`, `bsi_show` |
| **Comparison Query** | `bsi_eq`, `bsi_neq`, `bsi_gt`, `bsi_ge`, `bsi_lt`, `bsi_le`, `bsi_range`, `bsi_compare` |
| **Filtering** | `bsi_filter`, `bsi_ebm` |
| **Aggregation** | `bsi_sum`, `bsi_stat`, `bsi_topk`, `bsi_transpose`, `bsi_transpose_with_count` |
| **Arithmetic** | `bsi_add`, `bsi_add_agg`, `bsi_merge`, `bsi_merge_agg` |