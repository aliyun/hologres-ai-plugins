# Hologres Diagnostic SQL Queries

Complete collection of diagnostic SQL queries for `hologres.hg_query_log`.

## User Statistics

### Query count per user
```sql
SELECT usename AS "User",
       count(1) as "Query Count"
FROM hologres.hg_query_log
GROUP BY usename
ORDER BY count(1) DESC;
```

## Query Details

### Get specific query by ID
```sql
SELECT * FROM hologres.hg_query_log WHERE query_id = '13001450118416xxxx';
```

## New Query Analysis

### Count new queries yesterday
```sql
SELECT COUNT(1)
FROM (
    SELECT DISTINCT t1.digest
    FROM hologres.hg_query_log t1
    WHERE t1.query_start >= CURRENT_DATE - INTERVAL '1 day'
      AND t1.query_start < CURRENT_DATE
      AND NOT EXISTS (
          SELECT 1 FROM hologres.hg_query_log t2
          WHERE t2.digest = t1.digest
            AND t2.query_start < CURRENT_DATE - INTERVAL '1 day'
      )
      AND digest IS NOT NULL
) AS a;
```

### New queries by type
```sql
SELECT a.command_tag, COUNT(1)
FROM (
    SELECT DISTINCT t1.digest, t1.command_tag
    FROM hologres.hg_query_log t1
    WHERE t1.query_start >= CURRENT_DATE - INTERVAL '1 day'
      AND t1.query_start < CURRENT_DATE
      AND NOT EXISTS (
          SELECT 1 FROM hologres.hg_query_log t2
          WHERE t2.digest = t1.digest
            AND t2.query_start < CURRENT_DATE - INTERVAL '1 day'
      )
      AND t1.digest IS NOT NULL
) AS a
GROUP BY 1 ORDER BY 2 DESC;
```

### New query details
```sql
SELECT a.usename, a.status, a.query_id, a.digest, a.datname,
       a.command_tag, a.query, a.cpu_time_ms, a.memory_bytes
FROM (
    SELECT DISTINCT t1.usename, t1.status, t1.query_id, t1.digest,
           t1.datname, t1.command_tag, t1.query, t1.cpu_time_ms, t1.memory_bytes
    FROM hologres.hg_query_log t1
    WHERE t1.query_start >= CURRENT_DATE - INTERVAL '1 day'
      AND t1.query_start < CURRENT_DATE
      AND NOT EXISTS (
          SELECT 1 FROM hologres.hg_query_log t2
          WHERE t2.digest = t1.digest
            AND t2.query_start < CURRENT_DATE - INTERVAL '1 day'
      )
      AND t1.digest IS NOT NULL
) AS a;
```

### New query trend (hourly)
```sql
SELECT to_char(a.query_start, 'HH24') AS query_start_hour,
       a.command_tag, COUNT(1)
FROM (
    SELECT DISTINCT t1.query_start, t1.digest, t1.command_tag
    FROM hologres.hg_query_log t1
    WHERE t1.query_start >= CURRENT_DATE - INTERVAL '1 day'
      AND t1.query_start < CURRENT_DATE
      AND NOT EXISTS (
          SELECT 1 FROM hologres.hg_query_log t2
          WHERE t2.digest = t1.digest
            AND t2.query_start < CURRENT_DATE - INTERVAL '1 day'
      )
      AND t1.digest IS NOT NULL
) AS a
GROUP BY 1, 2 ORDER BY 3 DESC;
```

## Query Aggregation

### Slow query frequency by digest
```sql
SELECT digest, command_tag, count(1)
FROM hologres.hg_query_log
WHERE query_start >= CURRENT_DATE - INTERVAL '1 day'
  AND query_start < CURRENT_DATE
GROUP BY 1, 2
ORDER BY 3 DESC;
```

### Top 10 memory consumers (past week)
```sql
SELECT digest, avg(memory_bytes)
FROM hologres.hg_query_log
WHERE query_start >= CURRENT_DATE - INTERVAL '7 day'
  AND query_start < CURRENT_DATE
  AND digest IS NOT NULL
  AND memory_bytes IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC
LIMIT 10;
```

## Traffic Analysis

### Hourly access volume (last 3 hours)
```sql
SELECT date_trunc('hour', query_start) AS query_start,
       count(1) AS query_count,
       sum(read_bytes) AS read_bytes,
       sum(cpu_time_ms) AS cpu_time_ms
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '3 h'
GROUP BY 1;
```

## High Resource Period Analysis

### SQL template CPU consumption in specific time range
```sql
SELECT digest, count(1), avg(cpu_time_ms), sum(cpu_time_ms)
FROM hologres.hg_query_log
WHERE query_start > '2025-02-26 10:00:00+08'
  AND query_start < '2025-02-26 10:05:00+08'
GROUP BY digest
ORDER BY sum(cpu_time_ms) DESC
LIMIT 100;
```

### Comprehensive slow SQL analysis by time range
```sql
SELECT command_tag, digest, max(engine_type::text), count(1) total_count,
       sum(case when status != 'SUCCESS' then 1 else 0 end) fail_count,
       max(cpu_time_ms) max_cpu, avg(cpu_time_ms)::int avg_cpu,
       sum(cpu_time_ms) total_cpu, avg(duration)::int avg_duration,
       sum(duration) total_duration,
       max(case when status = 'SUCCESS' then query_id else null end) query_id,
       min(query_start)
FROM hologres.hg_query_log
WHERE query_start > '2025-12-09 14:10:00+08'
  AND query_start <= '2025-12-09 14:20:00+08'
  AND engine_type::text != '{FixedQE}'
GROUP BY 1, 2
ORDER BY sum(cpu_time_ms) DESC NULLS LAST
LIMIT 10;
```

## SQL Fingerprint (digest)

SQL fingerprint calculation rules:
- Only for SELECT, INSERT, DELETE, UPDATE queries
- Case handling follows Hologres SQL rules
- Ignores whitespace (spaces, newlines, tabs)
- Ignores specific constant values
- Array element count doesn't affect fingerprint
- Schema is auto-completed for table names
