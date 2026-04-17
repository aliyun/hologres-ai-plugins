# Hologres GUC Parameters for Query Tuning

Useful GUC (Grand Unified Configuration) parameters for query optimization.

## Join Optimization

### optimizer_join_order

```sql
SET optimizer_join_order = '<value>';
```

| Value | Description |
|-------|-------------|
| `exhaustive` (default) | Optimal plan, higher QO overhead |
| `query` | Follow SQL order, lower QO overhead |
| `greedy` | Greedy algorithm, balanced |

**Use Case**: Complex multi-table joins (5+ tables) where QO is slow.

---

## Aggregation

### optimizer_force_multistage_agg

```sql
SET optimizer_force_multistage_agg = on;
```

Forces multi-stage (partial + final) aggregation.

**Use Case**: Large aggregations where single-stage is slow.

---

## Join Type Control

### hg_experimental_enable_cross_join_rewrite

```sql
SET hg_experimental_enable_cross_join_rewrite = off;
```

Controls Cross Join optimization (V3.0+).

**Trade-off**: Cross Join is faster but uses more memory.

---

## Broadcast Control

### hg_experimental_enable_force_broadcast

```sql
SET hg_experimental_enable_force_broadcast = on;
```

Forces broadcast for small tables.

---

## Query Limits

### statement_timeout

```sql
SET statement_timeout = '5min';
```

---

## Memory Control

### hg_experimental_query_mem_limit

```sql
SET hg_experimental_query_mem_limit = 10737418240;  -- 10GB
```

---

## Scope

| Scope | Syntax |
|-------|--------|
| Session | `SET param = value;` |
| Transaction | `SET LOCAL param = value;` |
| Database | `ALTER DATABASE db SET param = value;` |

```sql
-- Reset to default
RESET optimizer_join_order;
```

---

## Common Scenarios

### Slow Multi-Table Joins
```sql
SET optimizer_join_order = 'query';
SET optimizer_force_multistage_agg = on;
```

### Memory Issues
```sql
SET hg_experimental_query_mem_limit = 5368709120;
SET hg_experimental_enable_cross_join_rewrite = off;
```
