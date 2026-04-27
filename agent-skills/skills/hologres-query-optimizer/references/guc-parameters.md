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

| Scope | SQL Syntax | CLI Equivalent |
|-------|-----------|----------------|
| Database | `ALTER DATABASE db SET param = value;` | `hologres guc set param value` |
| Database Reset | `ALTER DATABASE db RESET param;` | `hologres guc reset param` |

```bash
# List all Hologres GUC parameters with current values
hologres guc list
hologres guc list --filter optimizer

# Show a single parameter value
hologres guc show optimizer_join_order

# Set at database level (persistent)
hologres guc set optimizer_join_order query

# Reset to default
hologres guc reset optimizer_join_order
```

---

## Common Scenarios

### Slow Multi-Table Joins
```sql
SET optimizer_join_order = 'query';
SET optimizer_force_multistage_agg = on;
```

Persisted via CLI (database level):
```bash
hologres guc set optimizer_join_order query
hologres guc set optimizer_force_multistage_agg on
```

### Memory Issues
```sql
SET hg_experimental_query_mem_limit = 5368709120;
SET hg_experimental_enable_cross_join_rewrite = off;
```

Persisted via CLI:
```bash
hologres guc set hg_experimental_query_mem_limit 5368709120
hologres guc set hg_experimental_enable_cross_join_rewrite off
```

### Inspect & Reset
```bash
# Check all GUC parameters
hologres guc list

# Reset parameters to default
hologres guc reset optimizer_join_order
hologres guc reset hg_experimental_query_mem_limit
```
