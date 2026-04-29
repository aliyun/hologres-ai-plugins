---
name: hologres-slow-query-analysis
description: |
  Hologres slow query log analysis and diagnosis skill. Use for analyzing slow queries, 
  failed queries, query performance diagnosis, and log management in Alibaba Cloud Hologres.
  Triggers: "hologres slow query", "hg_query_log", "query diagnosis", "慢Query分析", "Hologres性能诊断"
---

## Prerequisites

This skill requires **hologres-cli** to be installed first:

```bash
pip install hologres-cli
```

All SQL execution and GUC parameter operations depend on `hologres-cli` commands (`hologres sql run`, `hologres guc set`).

# Hologres Slow Query Analysis

Diagnose and analyze slow/failed queries in Alibaba Cloud Hologres using the `hologres.hg_query_log` system table.

## Version Requirements

| Hologres Version | Feature |
|-----------------|---------|
| V0.10+ | Basic slow query log |
| V2.2+ | SQL fingerprint (digest) |
| V2.2.7+ | Default threshold 100ms |
| V3.0.2+ | Aggregated records for <100ms queries |

## Quick Start

### 1. Check Permissions

```sql
-- Superuser: view all DB logs
ALTER USER "cloud_account_id" SUPERUSER;

-- Or join pg_read_all_stats group
GRANT pg_read_all_stats TO "cloud_account_id";

-- For current DB only (SPM model)
CALL spm_grant('<db_name>_admin', 'cloud_account_id');
```

### 2. Basic Query Count

```sql
SELECT count(*) FROM hologres.hg_query_log;
```

### 3. Recent Slow Queries (10 min)

```sql
SELECT status AS "Status",
       duration AS "Duration(ms)",
       query_start AS "Start Time",
       (read_bytes/1048576)::text || ' MB' AS "Read",
       (memory_bytes/1048576)::text || ' MB' AS "Memory",
       (cpu_time_ms/1000)::text || ' s' AS "CPU",
       query_id AS "QueryID",
       query::char(50) AS "Query"
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '10 min'
ORDER BY duration DESC
LIMIT 100;
```

## Core Diagnostic Workflows

### Workflow 1: Find Resource-Heavy Queries

Use when CPU/memory usage is high.

```sql
-- Top 10 CPU-consuming queries (past day)
SELECT digest, avg(cpu_time_ms), sum(cpu_time_ms)
FROM hologres.hg_query_log
WHERE query_start >= CURRENT_DATE - INTERVAL '1 day'
  AND digest IS NOT NULL AND usename != 'system'
GROUP BY 1 ORDER BY 3 DESC LIMIT 10;
```

### Workflow 2: Find Failed Queries

```sql
SELECT status, message::char(100), duration, query_start, query_id, query::char(80)
FROM hologres.hg_query_log
WHERE query_start BETWEEN '2024-01-01 00:00:00'::timestamptz 
      AND '2024-01-01 01:00:00'::timestamptz
  AND status = 'FAILED'
ORDER BY query_start ASC LIMIT 100;
```

### Workflow 3: Query Phase Analysis

Identify bottleneck phase (optimization/startup/execution).

```sql
SELECT status, duration AS "Total(ms)",
       optimization_cost AS "Optimize(ms)",
       start_query_cost AS "Startup(ms)",
       get_next_cost AS "Execute(ms)",
       duration - optimization_cost - start_query_cost - get_next_cost AS "Other(ms)",
       query_id, query::char(50)
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '10 min'
ORDER BY duration DESC LIMIT 100;
```

### Workflow 4: Compare with Yesterday

```sql
SELECT query_date, count(1), sum(read_bytes), sum(cpu_time_ms)
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '3 h'
GROUP BY query_date
UNION ALL
SELECT query_date, count(1), sum(read_bytes), sum(cpu_time_ms)
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '1d 3h' AND query_start <= now() - interval '1d'
GROUP BY query_date;
```

## Key Fields Reference

| Field | Description |
|-------|-------------|
| `query_id` | Unique query identifier |
| `digest` | SQL fingerprint (MD5 hash) |
| `duration` | Total query time (ms) |
| `cpu_time_ms` | CPU time consumed |
| `memory_bytes` | Peak memory usage |
| `read_bytes` | Data read volume |
| `engine_type` | Query engine (HQE/PQE/SDK/PG) |
| `optimization_cost` | Plan generation time |
| `start_query_cost` | Query startup time |
| `get_next_cost` | Execution time |

## Configuration

```sql
-- Set slow query threshold (DB level, superuser only)
ALTER DATABASE dbname SET log_min_duration_statement = '250ms';

-- Session level
SET log_min_duration_statement = '250ms';

-- Set log retention (V3.0.27+, 3-30 days)
ALTER DATABASE dbname SET hg_query_log_retention_time_sec = 2592000;
```

Or use the CLI for database-level settings:
```bash
hologres guc set log_min_duration_statement '250ms'
hologres guc set hg_query_log_retention_time_sec 2592000
```

## References

| Document | Content |
|----------|---------|
| [diagnostic-queries.md](references/diagnostic-queries.md) | Complete diagnostic SQL collection |
| [log-export.md](references/log-export.md) | Export logs to internal/external tables |
| [configuration.md](references/configuration.md) | Configuration parameters |

## Best Practices

1. Always filter by `query_start` for better performance
2. Use `digest` to group similar queries for pattern analysis
3. Check `engine_type` - PQE queries may need optimization
4. For `start_query_cost` high: check locks or resource contention
5. For `get_next_cost` high: optimize SQL or add indexes
6. Regular cleanup: set appropriate retention period
