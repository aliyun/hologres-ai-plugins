---
name: hologres-query-optimizer
description: |
  Hologres Query Execution Plan Analyzer and Optimizer. Use for analyzing SQL performance issues, 
  understanding EXPLAIN/EXPLAIN ANALYZE output, interpreting query operators, and providing 
  optimization recommendations for Hologres queries.
  Triggers: "hologres explain", "query plan", "execution plan", "sql optimization", "query performance", 
  "hologres performance", "slow query", "query optimizer", "explain analyze"
---

## Prerequisites

This skill requires **hologres-cli** to be installed first:

```bash
pip install hologres-cli
```

All SQL execution and GUC parameter operations depend on `hologres-cli` commands (`hologres sql run`, `hologres guc show/set`).

# Hologres Query Execution Plan Analyzer

This skill helps analyze and optimize Hologres SQL query execution plans using `EXPLAIN` and `EXPLAIN ANALYZE` commands.

> **Version Note**: This documentation is based on Hologres V1.3.4x+. Upgrade your instance for better execution plan readability.

## Overview

| Command | Description |
|---------|-------------|
| `EXPLAIN <sql>` | Shows **estimated** execution plan from Query Optimizer (QO). Reference only. |
| `EXPLAIN ANALYZE <sql>` | Shows **actual** execution plan with real runtime metrics. Use for optimization. |

## Quick Start

```sql
-- Estimated plan (no execution)
EXPLAIN SELECT * FROM my_table WHERE id > 100;

-- Actual plan with runtime metrics (executes query)
EXPLAIN ANALYZE SELECT * FROM my_table WHERE id > 100;
```

## Reading EXPLAIN Output

Read execution plans **bottom-up**. Each arrow (`->`) represents a node/operator.

| Parameter | Description |
|-----------|-------------|
| `cost` | Estimated cost: `startup_cost..total_cost`. Parent includes child costs. |
| `rows` | Estimated output rows. **`rows=1000` indicates missing statistics** — run `ANALYZE <table>`. |
| `width` | Estimated average output width (bytes). |

## Reading EXPLAIN ANALYZE Output

EXPLAIN ANALYZE includes four sections: **Query Plan**, **ADVICE**, **Cost**, and **Resource**.

### Query Plan Metrics

Format: `[dop_in:dop_out id=X dop=N time=max/avg/min rows=total(max/avg/min) mem=max/avg/min open=X get_next=Y]`

| Metric | Description |
|--------|-------------|
| `dop_in:dop_out` | Parallelism ratio (e.g., `21:1` for gather, `21:21` for shuffle) |
| `dop` | Actual parallelism degree (matches shard count) |
| `time` | Total time = open + get_next (ms). **Cumulative** from children. |
| `rows` | Output rows: `total(max/avg/min)`. Large variance = data skew. |
| `mem` | Memory: `max/avg/min` |
| `open` | Initialization time. Hash operators build tables here. |
| `get_next` | Data fetch time. Called repeatedly until complete. |

> **Important**: `time` is cumulative. Current operator time = current time - child time.

### ADVICE Section

System-generated suggestions:
- Missing indexes: `Table xxx misses bitmap index`
- Missing statistics: `Table xxx Miss Stats! please run 'analyze xxx';`
- Data skew: `shuffle data skew! max rows is X, min rows is Y`

### Cost Breakdown

| Metric | Description |
|--------|-------------|
| Total cost | Query total time (ms) |
| Optimizer cost | QO plan generation time |
| Start query cost | Pre-execution init (schema sync, locking) |
| Get the first block cost | Time to first record batch |
| Get result cost | Time to all results |

### Resource Consumption

Format: `total(max_worker/avg_worker/min_worker)`

| Metric | Description |
|--------|-------------|
| Memory | Total and per-worker memory |
| CPU time | Cumulative CPU time across cores |
| Physical read bytes | Disk reads (cache miss) |
| Read bytes | Total reads (disk + cache) |

## Common Operators

For detailed operator reference, see [references/operators.md](references/operators.md).

### Scan Operators
| Operator | Description |
|----------|-------------|
| Seq Scan | Full table scan |
| Index Scan using Clustering_index | Column-store index scan |
| Index Seek (pk_index) | Row-store primary key scan |

### Filter Operators
| Operator | Description |
|----------|-------------|
| Filter | No index hit — **add indexes** |
| Segment Filter | Segment key hit |
| Cluster Filter | Clustering key hit |
| Bitmap Filter | Bitmap index hit |

### Data Movement
| Operator | Description |
|----------|-------------|
| Local Gather | Merge files within shard |
| Gather | Merge shards to final result |
| Redistribution | Data shuffle — **check distribution_key** |
| Broadcast | Small table broadcast to all shards |

### Join Operators
| Operator | Description |
|----------|-------------|
| Hash Join | Hash-based join (ensure small table is hash table) |
| Nested Loop | Nested loop join (**avoid for large data**) |
| Cross Join | Optimized non-equi join (V3.0+) |

### Aggregation
| Operator | Description |
|----------|-------------|
| HashAggregate | Hash-based aggregation |
| Partial/Final HashAggregate | Multi-stage aggregation |

### Other
| Operator | Description |
|----------|-------------|
| Sort | ORDER BY |
| Limit | Row limit (check if pushed to scan) |
| ExecuteExternalSQL | PQE execution — **rewrite for HQE** |

## Optimization Workflow

1. Run `EXPLAIN ANALYZE` on slow query
2. Check **ADVICE** section for immediate fixes
3. Identify bottleneck operators (highest time)
4. Apply targeted optimizations:

| Issue | Symptom | Solution |
|-------|---------|----------|
| Missing stats | `rows=1000` | `ANALYZE <table>` |
| Data shuffle | Redistribution | Fix `distribution_key` |
| Wrong hash table | Large table as hash | Update statistics |
| No index | Filter only | Add clustering/bitmap index |
| PQE execution | ExecuteExternalSQL | Rewrite to HQE functions |
| Data skew | Large max/min variance | Review distribution |

## Key GUC Parameters

```sql
-- Multi-stage aggregation
SET optimizer_force_multistage_agg = on;

-- Join order control (for complex multi-table joins)
SET optimizer_join_order = 'query';  -- Follow SQL order
SET optimizer_join_order = 'greedy'; -- Greedy algorithm

-- Disable Cross Join
SET hg_experimental_enable_cross_join_rewrite = off;
```

To persist these settings at database level, use the CLI:
```bash
hologres guc set optimizer_force_multistage_agg on
hologres guc set optimizer_join_order query
```

## Best Practices

1. Always use `EXPLAIN ANALYZE` for production analysis
2. Run `ANALYZE` after significant data changes
3. Design `distribution_key` based on JOIN/GROUP BY patterns
4. Set `clustering_key` for range query columns
5. Use bitmap indexes for low-cardinality filters
6. Ensure small table is hash table in joins
7. Avoid non-equi joins when possible
8. Rewrite PQE functions to HQE alternatives

## Reference Links

| Reference | Description |
|-----------|-------------|
| [references/operators.md](references/operators.md) | Detailed operator descriptions |
| [references/optimization-patterns.md](references/optimization-patterns.md) | Common optimization patterns |
| [references/guc-parameters.md](references/guc-parameters.md) | Query tuning parameters |
