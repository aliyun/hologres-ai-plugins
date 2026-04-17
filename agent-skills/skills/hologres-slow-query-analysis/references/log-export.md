# Hologres Slow Query Log Export

Export slow query logs to Hologres internal tables or external tables (MaxCompute, OSS).

## Prerequisites

- Account must have access to `hologres.hg_query_log` table
- Superuser or pg_read_all_stats permission for full instance logs
- Use `query_start` as filter for better performance

## Important Notes

1. Use `query_start` column for time range filtering (indexed)
2. Don't wrap `query_start` in expressions (breaks index usage)
   - Bad: `WHERE to_char(query_start, 'yyyymmdd') = '20220101'`
   - Good: `WHERE query_start >= '2022-01-01' AND query_start < '2022-01-02'`

## Export to Hologres Internal Table

### 1. Create target table

```sql
CREATE TABLE query_log_download (
    usename text,
    status text,
    query_id text,
    datname text,
    command_tag text,
    duration integer,
    message text,
    query_start timestamp with time zone,
    query_date text,
    query text,
    result_rows bigint,
    result_bytes bigint,
    read_rows bigint,
    read_bytes bigint,
    affected_rows bigint,
    affected_bytes bigint,
    memory_bytes bigint,
    shuffle_bytes bigint,
    cpu_time_ms bigint,
    physical_reads bigint,
    pid integer,
    application_name text,
    engine_type text[],
    client_addr text,
    table_write text,
    table_read text[],
    session_id text,
    session_start timestamp with time zone,
    trans_id text,
    command_id text,
    optimization_cost integer,
    start_query_cost integer,
    get_next_cost integer,
    extended_cost text,
    plan text,
    statistics text,
    visualization_info text,
    query_detail text,
    query_extinfo text[]
);
```

### 2. Export data

```sql
INSERT INTO query_log_download
SELECT usename, status, query_id, datname, command_tag, duration,
       message, query_start, query_date, query, result_rows, result_bytes,
       read_rows, read_bytes, affected_rows, affected_bytes, memory_bytes,
       shuffle_bytes, cpu_time_ms, physical_reads, pid, application_name,
       engine_type, client_addr, table_write, table_read, session_id,
       session_start, trans_id, command_id, optimization_cost,
       start_query_cost, get_next_cost, extended_cost, plan, statistics,
       visualization_info, query_detail, query_extinfo
FROM hologres.hg_query_log
WHERE query_start >= '2022-08-03' AND query_start < '2022-08-04';
```

## Export to MaxCompute

### 1. Create MaxCompute table

```sql
-- Run in MaxCompute
CREATE TABLE IF NOT EXISTS mc_holo_query_log (
    username STRING COMMENT 'Query user',
    status STRING COMMENT 'Query status',
    query_id STRING COMMENT 'Query ID',
    datname STRING COMMENT 'Database name',
    command_tag STRING COMMENT 'Query type',
    duration BIGINT COMMENT 'Duration (ms)',
    message STRING COMMENT 'Error message',
    query STRING COMMENT 'Query text',
    read_rows BIGINT COMMENT 'Rows read',
    read_bytes BIGINT COMMENT 'Bytes read',
    memory_bytes BIGINT COMMENT 'Memory used',
    shuffle_bytes BIGINT COMMENT 'Shuffle bytes',
    cpu_time_ms BIGINT COMMENT 'CPU time (ms)',
    physical_reads BIGINT COMMENT 'Physical reads',
    application_name STRING COMMENT 'Application',
    engine_type ARRAY<STRING> COMMENT 'Query engine',
    table_write STRING COMMENT 'Write table',
    table_read ARRAY<STRING> COMMENT 'Read tables',
    plan STRING COMMENT 'Query plan',
    optimization_cost BIGINT COMMENT 'Plan time',
    start_query_cost BIGINT COMMENT 'Startup time',
    get_next_cost BIGINT COMMENT 'Execution time',
    extended_cost STRING COMMENT 'Other costs',
    query_detail STRING COMMENT 'Extra info (JSON)',
    query_extinfo ARRAY<STRING> COMMENT 'Extra info (Array)',
    query_start STRING COMMENT 'Start time',
    query_date STRING COMMENT 'Start date'
) COMMENT 'hologres instance query log daily'
PARTITIONED BY (ds STRING COMMENT 'stat date')
LIFECYCLE 365;

ALTER TABLE mc_holo_query_log ADD PARTITION (ds=20220803);
```

### 2. Import foreign schema and export

```sql
-- Run in Hologres
IMPORT FOREIGN SCHEMA project_name LIMIT TO (mc_holo_query_log)
FROM SERVER odps_server INTO public;

INSERT INTO mc_holo_query_log
SELECT usename AS username, status, query_id, datname, command_tag,
       duration, message, query, read_rows, read_bytes, memory_bytes,
       shuffle_bytes, cpu_time_ms, physical_reads, application_name,
       engine_type, table_write, table_read, plan, optimization_cost,
       start_query_cost, get_next_cost, extended_cost, query_detail,
       query_extinfo, query_start, query_date, '20220803'
FROM hologres.hg_query_log
WHERE query_start >= '2022-08-03' AND query_start < '2022-08-04';
```
