# Hologres Slow Query Log Configuration

Configuration parameters for controlling slow query log behavior.

## log_min_duration_statement

Controls the minimum query duration to be logged.

| Property | Value |
|----------|-------|
| Default | 100ms (V2.2.7+), 1s (earlier versions) |
| Minimum | 100ms |
| Scope | DB level (superuser), Session level (all users) |

### Usage

```sql
-- DB level (requires superuser)
ALTER DATABASE dbname SET log_min_duration_statement = '250ms';

-- Session level (all users)
SET log_min_duration_statement = '250ms';

-- Disable logging
SET log_min_duration_statement = '-1';
```

### Notes
- Only affects new queries, existing logs remain unchanged
- Logs all DDL statements regardless of this setting
- Logs all failed queries regardless of this setting

## log_min_duration_query_stats

Controls recording of query execution statistics.

| Property | Value |
|----------|-------|
| Default | 10s |
| Scope | DB level, Session level |

### Usage

```sql
-- DB level
ALTER DATABASE dbname SET log_min_duration_query_stats = '20s';

-- Session level
SET log_min_duration_query_stats = '20s';

-- Disable
SET log_min_duration_query_stats = '-1';
```

### Notes
- High storage consumption
- Lower values may slow down log queries
- Adjust to lower values only when troubleshooting

## log_min_duration_query_plan

Controls recording of query execution plans.

| Property | Value |
|----------|-------|
| Default | 10s |
| Scope | DB level, Session level |

### Usage

```sql
-- DB level
ALTER DATABASE dbname SET log_min_duration_query_plan = '10s';

-- Session level
SET log_min_duration_query_plan = '10s';

-- Disable
SET log_min_duration_query_plan = '-1';
```

### Notes
- Execution plans can be obtained via EXPLAIN anytime
- Usually not necessary to record

## hg_query_log_retention_time_sec (V3.0.27+)

Controls log retention period.

| Property | Value |
|----------|-------|
| Default | 30 days (2592000 seconds) |
| Range | 3-30 days (259200-2592000 seconds) |
| Scope | DB level |

### Usage

```sql
-- Set to 7 days
ALTER DATABASE dbname SET hg_query_log_retention_time_sec = 604800;

-- Set to 30 days (default)
ALTER DATABASE dbname SET hg_query_log_retention_time_sec = 2592000;
```

### Notes
- Only affects new logs
- Expired logs are cleaned immediately (not async)
- Only applies to new connections

## V1.1 Compatibility Fix

For V1.1.36-V1.1.49, enable complete statistics display:

```sql
-- DB level (recommended, one-time setting)
ALTER DATABASE db_name SET hg_experimental_force_sync_collect_execution_statistics = ON;

-- Session level
SET hg_experimental_force_sync_collect_execution_statistics = ON;
```
