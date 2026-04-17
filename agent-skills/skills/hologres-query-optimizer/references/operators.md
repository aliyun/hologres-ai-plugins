# Hologres Query Operators Reference

Detailed descriptions of all Hologres query operators with optimization tips.

## SCAN Operators

### Seq Scan

**Description**: Sequential full table scan.

```
Seq Scan on <table_name>
```

**Variations**:
- `Seq Scan on Partitioned Table`: Shows `Partitions selected: x out of y`
- `Foreign Table Type: MaxCompute/OSS/Hologres`: External table scan

**Optimization**: Add filters or indexes to avoid full scans.

---

### Index Scan using Clustering_index

**Description**: Column-store index scan. Triggered when query hits segment, clustering, or bitmap indexes.

```
Index Scan using Clustering_index on <table_name>
  Segment Filter: (condition)
  Cluster Filter: (condition)
  Bitmap Filter: (condition)
```

**Optimization**: Design proper `clustering_key`, `event_time_column`, and `bitmap_columns`.

---

### Index Seek (pk_index)

**Description**: Row-store primary key scan. Used for point queries on row-store tables.

**Optimization**: Use row-store tables with primary keys for high-frequency point queries.

---

## Filter Operators

### Filter (No Index)

**Warning**: Plain `Filter` means no index hit. Review table indexes.

```
Seq Scan on <table_name>
  Filter: (condition)
```

**Special Case**: `One-Time Filter: false` = empty result set.

---

### Segment Filter

**Description**: Segment key (event_time_column) hit.

```sql
-- Set segment key
CALL set_table_property('table', 'event_time_column', 'time_col');
```

---

### Cluster Filter

**Description**: Clustering key hit.

```sql
-- Set clustering key
CALL set_table_property('table', 'clustering_key', 'col1,col2');
```

---

### Bitmap Filter

**Description**: Bitmap index hit.

```sql
-- Set bitmap columns
CALL set_table_property('table', 'bitmap_columns', 'col1,col2');
```

---

## Data Movement Operators

### Local Gather

**Description**: Merge data from multiple files within a shard.

The `dop` under Local Gather represents file count being scanned.

---

### Gather

**Description**: Merge data from multiple shards to final result.

```
Gather
  [20:1 ...]  -- 20 shards merge to 1
```

---

### Redistribution

**Description**: Data shuffle across shards.

```
Redistribution
  Hash Key: col1, col2
```

**Common Causes**:
1. Distribution key not set or misaligned with JOIN/GROUP BY keys
2. Expression on JOIN key changes data type

**Optimization**:
```sql
-- Set distribution key to match JOIN keys
CALL set_table_property('table', 'distribution_key', 'join_col');
```

**Example Problem**:
```sql
-- tbl1.distribution_key='a', tbl2.distribution_key='d'
-- JOIN on tbl1.a=tbl2.c causes redistribution!
SELECT * FROM tbl1 JOIN tbl2 ON tbl1.a = tbl2.c;
```

---

### Broadcast

**Description**: Broadcast small table to all shards for join.

```
Broadcast
  [1:20 ...]  -- 1 input broadcasts to 20 shards
```

**Warning**: If non-small table shows Broadcast, statistics are likely outdated. Run `ANALYZE <table>`.

---

## Join Operators

### Hash Join

**Description**: Hash-based join. One table (typically smaller) builds hash table in memory.

| Type | Description |
|------|-------------|
| Hash Left Join | All left rows + matching right (NULL if no match) |
| Hash Right Join | All right rows + matching left (NULL if no match) |
| Hash Inner Join | Only matching rows |
| Hash Full Join | All rows from both (NULL for non-matches) |
| Hash Anti Join | Unmatched rows only (NOT EXISTS) |
| Hash Semi Join | First match only (EXISTS) |

**Key Sub-nodes**:
- `Hash Cond`: Join condition
- `Hash Key`: GROUP BY key distribution

**Identify Hash Table**:
- Table with "Hash" prefix
- Bottom table in plan (read bottom-up)

**Optimization**:
1. **Ensure small table is hash table** — update statistics with `ANALYZE`
2. **Control join order** for complex queries:
   ```sql
   SET optimizer_join_order = 'query';     -- Follow SQL order
   SET optimizer_join_order = 'greedy';    -- Greedy algorithm
   SET optimizer_join_order = 'exhaustive'; -- Default, optimal
   ```

---

### Nested Loop Join & Materialize

**Description**: Nested loop where outer table drives inner table scan. `Materialize` caches inner table.

**Warning**: Very expensive for large tables.

**Optimization**:
- Keep result sets small
- Avoid non-equi joins
- Rewrite to equi-joins if possible

---

### Cross Join (V3.0+)

**Description**: Optimized nested loop for small table non-equi joins. Loads small table into memory.

**Trade-off**: Better performance but higher memory.

**Disable if needed**:
```sql
SET hg_experimental_enable_cross_join_rewrite = off;
```

---

## Aggregation Operators

### HashAggregate

**Description**: Hash-based aggregation for GROUP BY.

### Multi-stage Aggregation

- `Partial HashAggregate`: File/shard-level aggregation
- `Final HashAggregate`: Cross-shard aggregation

**Force Multi-stage**:
```sql
SET optimizer_force_multistage_agg = on;
```

---

## Other Operators

### Sort

**Description**: ORDER BY sorting.

**Optimization**: Avoid sorting large datasets. Consider clustering_key alignment.

---

### Limit

**Description**: Limit output rows.

**Important**: Check if Limit is pushed to Scan node. Only pushed Limit reduces actual scan.

**Optimization**:
- Add filters to reduce scan scope
- Avoid very large LIMIT values

---

### ExecuteExternalSQL

**Description**: PQE (PostgreSQL engine) execution. Slower than HQE.

**Optimization**: Rewrite to HQE-supported functions.

```sql
-- PQE (slow)
SELECT a::timestamp FROM table;

-- HQE (fast)
SELECT to_timestamp(a, 'YYYY-MM-DD HH24:MI:SS') FROM table;
```

---

### Decode

**Description**: Text data encoding/decoding for accelerated computation.

---

### Project

**Description**: Query result projection. Safe to ignore.

---

### Append

**Description**: Combine subquery results (UNION ALL).

---

### Exchange

**Description**: Intra-shard data exchange. Safe to ignore.

---

### Forward

**Description**: Data transfer between HQE and PQE/SQE engines.

---

### Shard Prune & Shards Selected

- `Shard prune: lazily/eagerly`: Shard selection strategy
- `Shards selected: X out of Y`: Number of shards accessed
