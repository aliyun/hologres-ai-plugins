# Hologres Query Optimization Patterns

Common optimization patterns and SQL rewrites for Hologres queries.

## Pattern 1: Update Statistics

**Problem**: Inaccurate row estimates (`rows=1000` default)

**Solution**:
```sql
ANALYZE <tablename>;
```

**Best Practice**: Run ANALYZE after >10% data change.

---

## Pattern 2: Fix Distribution Key

**Problem**: Redistribution operators causing shuffle

**Solution**: Align distribution key with JOIN/GROUP BY keys.

```sql
BEGIN;
CREATE TABLE orders (
    order_id bigint NOT NULL,
    customer_id bigint NOT NULL
);
CALL set_table_property('orders', 'distribution_key', 'customer_id');
COMMIT;
```

**For existing tables**: Recreate with new distribution key.

---

## Pattern 3: Add Indexes

### Clustering Key (range queries)
```sql
CALL set_table_property('table', 'clustering_key', 'time_col');
```

### Segment Key (time-series)
```sql
CALL set_table_property('table', 'event_time_column', 'time_col');
```

### Bitmap Index (equality filters)
```sql
CALL set_table_property('table', 'bitmap_columns', 'status,type');
```

---

## Pattern 4: Optimize Hash Joins

**Problem**: Large table used as hash table

**Solution**:
```sql
-- Update statistics
ANALYZE large_table;
ANALYZE small_table;

-- Or force join order
SET optimizer_join_order = 'query';
```

---

## Pattern 5: Avoid Nested Loop Joins

**Problem**: Non-equi joins causing nested loop

**Solution**:
```sql
-- Instead of non-equi join
SELECT * FROM t1, t2 WHERE t1.a > t2.b;

-- Rewrite with range conditions
SELECT * FROM t1 JOIN t2 ON t1.a > t2.b AND t1.a < t2.b + 100;
```

---

## Pattern 6: PQE to HQE Rewrites

**Problem**: ExecuteExternalSQL showing PQE execution

| PQE (Slow) | HQE (Fast) |
|------------|------------|
| `col::timestamp` | `to_timestamp(col, 'YYYY-MM-DD HH24:MI:SS')` |
| `col::date` | `to_date(col, 'YYYY-MM-DD')` |

---

## Pattern 7: Multi-stage Aggregation

**Problem**: Slow single-stage aggregation on large data

**Solution**:
```sql
SET optimizer_force_multistage_agg = on;
```

---

## Pattern 8: Push Down Limit

**Problem**: Limit not pushed to scan

**Solution**: Add filters to help push-down.

```sql
SELECT * FROM table WHERE partition_col = 'value' LIMIT 100;
```

---

## Pattern 9: Reduce Data Skew

**Problem**: Large variance in rows/time across workers

**Solution**:
1. Review distribution key
2. Handle hot keys separately
3. Use composite distribution keys

```sql
-- Check distribution
SELECT hg_shard_id, COUNT(*) FROM table GROUP BY hg_shard_id ORDER BY 2 DESC;
```

---

## Pattern 10: Partition Pruning

**Problem**: Full partition scan

**Solution**:
```sql
-- Always filter on partition column directly
SELECT * FROM table WHERE partition_date = '2024-01-01';

-- Avoid expressions on partition column
-- BAD: WHERE date_trunc('day', partition_date) = ...
```

---

## Quick Reference

| Issue | EXPLAIN Symptom | Solution |
|-------|-----------------|----------|
| Bad estimates | `rows=1000` | `ANALYZE <table>` |
| Data shuffle | `Redistribution` | Fix distribution_key |
| No index | `Filter` only | Add clustering/bitmap |
| Wrong hash table | Large hash table | Update statistics |
| Nested loop | `Nested Loop` | Rewrite to equi-join |
| PQE | `ExecuteExternalSQL` | Rewrite functions |
| Slow agg | Long agg time | Multi-stage aggregation |
| Data skew | Large max/min variance | Review distribution |
