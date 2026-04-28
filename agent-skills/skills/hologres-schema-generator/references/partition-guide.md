# Hologres Partition Table Guide

## Overview

Hologres supports **LIST partitioning** only. Partition tables divide data into child tables by discrete values (typically dates), enabling partition pruning in queries.

## Syntax

### Create Parent Table

```sql
-- V2.1+ WITH syntax
CREATE TABLE parent_table (
  id BIGINT NOT NULL,
  ds TEXT NOT NULL,
  ...,
  PRIMARY KEY (ds, id)
)
PARTITION BY LIST (ds)
WITH (
  orientation = 'column',
  distribution_key = 'id',
  clustering_key = 'id:asc',
  event_time_column = 'ds'
);

-- Legacy syntax
BEGIN;
CREATE TABLE parent_table (
  id BIGINT NOT NULL,
  ds TEXT NOT NULL,
  PRIMARY KEY (ds, id)
) PARTITION BY LIST (ds);
CALL set_table_property('parent_table', 'orientation', 'column');
CALL set_table_property('parent_table', 'distribution_key', 'id');
COMMIT;
```

### Create Child Partitions

```sql
-- Single value per partition (most common: daily partitions)
CREATE TABLE parent_20251201 PARTITION OF parent_table FOR VALUES IN ('20251201');
CREATE TABLE parent_20251202 PARTITION OF parent_table FOR VALUES IN ('20251202');

-- Multiple values per partition (e.g., weekly)
CREATE TABLE parent_w01 PARTITION OF parent_table FOR VALUES IN ('20251201','20251202','20251203','20251204','20251205','20251206','20251207');
```

### Dynamic Partition Creation (Writing)

If writing to a partition value that has no child table, the write will fail. You must create the partition before writing.

```sql
-- Auto-create partition on write (V2.0+)
-- Set at session level
SET hg_experimental_enable_create_partition_on_insert = ON;

-- Or at table level (V2.2+)
ALTER TABLE parent_table SET (auto_partitioning = 'true');
```

## Partition Column Rules

| Rule | Description |
|------|-------------|
| Only **LIST** type | RANGE and HASH partitioning not supported |
| **Must be in PK** | If the table has a primary key, partition column must be part of it |
| Only **1 column** | Cannot partition by multiple columns |
| Supported types | `TEXT`, `VARCHAR(n)`, `INT`, `BIGINT`, `DATE` (V1.3.22+) |
| Cannot be altered | Partition column is set at creation, cannot change |

## When to Use Partitions

### Decision Flowchart

```
Daily data volume?
  |
  +-- < 100M rows/day --> No partition. Use event_time_column only
  |
  +-- >= 100M rows/day
       |
       +-- Queries always filter by date? --> Partition by date (TEXT ds)
       |
       +-- Queries filter by category? --> Partition by category (if few values)
       |
       +-- No clear filter pattern --> No partition. Use clustering_key
```

### Good Partition Candidates

| Scenario | Partition Column | Type | Partition Granularity |
|----------|-----------------|------|----------------------|
| Daily log analytics | `ds` | TEXT | Daily: '20251201' |
| Monthly billing | `month` | TEXT | Monthly: '202512' |
| Regional data | `region` | TEXT | Per region: 'cn','us','eu' |
| Date-typed events | `event_date` | DATE | Daily |

### Bad Partition Candidates

| Scenario | Why Not |
|----------|---------|
| Small daily data (< 100M rows) | Too many small files, hurts scan performance |
| High-cardinality column (user_id) | Creates millions of tiny partitions |
| Frequently changing filter patterns | Queries may miss partition pruning |
| No common filter column | No pruning benefit |

## Partition with Table Properties

All table properties (distribution_key, clustering_key, etc.) are set on the **parent table** and inherited by all child partitions.

```sql
CREATE TABLE events (
  event_id BIGINT NOT NULL,
  user_id BIGINT,
  event_type TEXT,
  event_time TIMESTAMPTZ,
  ds TEXT NOT NULL,
  PRIMARY KEY (ds, event_id)
)
PARTITION BY LIST (ds)
WITH (
  orientation = 'column',
  distribution_key = 'event_id',
  clustering_key = 'event_time:asc',
  event_time_column = 'event_time',
  bitmap_columns = 'event_type,user_id'
);
```

## Partition Management

### List Partitions

```sql
-- Show all child partitions
SELECT
  nmsp_parent.nspname AS parent_schema,
  parent.relname AS parent_table,
  nmsp_child.nspname AS child_schema,
  child.relname AS child_table
FROM pg_inherits
  JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
  JOIN pg_class child ON pg_inherits.inhrelid = child.oid
  JOIN pg_namespace nmsp_parent ON parent.relnamespace = nmsp_parent.oid
  JOIN pg_namespace nmsp_child ON child.relnamespace = nmsp_child.oid
WHERE parent.relname = 'parent_table';
```

### Drop Partition

```sql
-- Drop a specific child partition (data is deleted)
DROP TABLE parent_20251201;

-- Detach partition (preserves data as standalone table)
ALTER TABLE parent_table DETACH PARTITION parent_20251201;
```

### Rename Partition

```sql
ALTER TABLE parent_20251201 RENAME TO parent_20251201_backup;
```

### Attach Existing Table as Partition

```sql
-- Existing table must have compatible schema
ALTER TABLE parent_table ATTACH PARTITION existing_table FOR VALUES IN ('20251210');
```

## Partition-Based Data Lifecycle (Recommended)

> **Do NOT use `time_to_live_in_seconds` for data lifecycle.** TTL deletion is non-deterministic — data is deleted at an arbitrary time after the specified duration, making it unreliable.
>
> **Use partition-based lifecycle instead** — drop old partitions on a schedule for precise, predictable data management.

### Lifecycle via Scheduled Partition Dropping

```sql
-- Create table with daily partitions (no TTL)
CREATE TABLE logs (
  log_id BIGINT NOT NULL,
  message TEXT,
  ds TEXT NOT NULL,
  log_time TIMESTAMPTZ,
  PRIMARY KEY (ds, log_id)
)
PARTITION BY LIST (ds)
WITH (
  orientation = 'column',
  distribution_key = 'log_id',
  event_time_column = 'log_time'
);

-- Drop partitions older than 30 days (run via cron / scheduling system)
-- Example: on 2025-12-31, drop partition for 2025-12-01
DROP TABLE IF EXISTS logs_20251201;
```

### Automation Script: Drop Old Partitions

```sql
-- Drop partitions older than N days
DO $$
DECLARE
  cutoff_date DATE := CURRENT_DATE - INTERVAL '30 days';
  partition_value TEXT;
  partition_name TEXT;
  rec RECORD;
BEGIN
  FOR rec IN
    SELECT child.relname AS child_table
    FROM pg_inherits
      JOIN pg_class parent ON pg_inherits.inhparent = parent.oid
      JOIN pg_class child ON pg_inherits.inhrelid = child.oid
    WHERE parent.relname = 'logs'
  LOOP
    -- Extract date from partition name (assumes suffix is YYYYMMDD)
    partition_value := RIGHT(rec.child_table, 8);
    BEGIN
      IF TO_DATE(partition_value, 'YYYYMMDD') < cutoff_date THEN
        EXECUTE format('DROP TABLE IF EXISTS %I', rec.child_table);
        RAISE NOTICE 'Dropped partition: %', rec.child_table;
      END IF;
    EXCEPTION WHEN OTHERS THEN
      -- Skip partitions with non-date suffixes
      NULL;
    END;
  END LOOP;
END $$;
```

## Querying Partition Tables

### Partition Pruning

Always include partition column in WHERE clause for efficient queries:

```sql
-- Good: partition pruning occurs
SELECT * FROM events WHERE ds = '20251201' AND event_type = 'click';

-- Good: range pruning (scans only matching partitions)
SELECT * FROM events WHERE ds >= '20251201' AND ds <= '20251207';

-- Bad: full scan across ALL partitions
SELECT * FROM events WHERE event_type = 'click';
-- (no ds filter -> scans every partition)
```

### Query Child Partition Directly

```sql
-- Query specific partition (avoids pruning overhead for known partition)
SELECT * FROM events_20251201 WHERE event_type = 'click';
```

### INSERT / UPSERT

```sql
-- Insert into parent table (routes to correct partition)
INSERT INTO events (event_id, user_id, event_type, event_time, ds)
VALUES (1, 100, 'click', NOW(), '20251201');

-- Insert into child partition directly
INSERT INTO events_20251201 (event_id, user_id, event_type, event_time, ds)
VALUES (1, 100, 'click', NOW(), '20251201');

-- UPSERT (INSERT ON CONFLICT) works on both parent and child
INSERT INTO events VALUES (1, 100, 'click', NOW(), '20251201')
ON CONFLICT (ds, event_id) DO UPDATE SET event_type = EXCLUDED.event_type;
```

## Best Practices

1. **Use TEXT for partition column** -- Simplest and most compatible (ds = '20251201')
2. **One day per partition for daily data** -- Standard pattern for large datasets
3. **Pre-create partitions** -- Create future partitions in advance to avoid write failures
4. **Always filter on partition column** -- Prevents expensive full scans
5. **Combine with event_time_column** -- Partition for coarse pruning, segment for fine pruning
6. **Monitor partition count** -- Too many partitions (>1000) can degrade metadata operations
7. **Use scheduled partition dropping for lifecycle** -- Drop old partitions via cron; do NOT use `time_to_live_in_seconds`
8. **Partition column in PK** -- Required rule; put partition column first in PK for clarity
9. **Avoid partitioning small tables** -- Overhead exceeds benefit when daily data is small
10. **Same distribution_key across related tables** -- Enables local joins across partitioned tables

## Partition Automation Script

```sql
-- Create daily partitions for next 7 days
DO $$
DECLARE
  d DATE;
  partition_name TEXT;
  partition_value TEXT;
BEGIN
  FOR i IN 0..6 LOOP
    d := CURRENT_DATE + i;
    partition_value := TO_CHAR(d, 'YYYYMMDD');
    partition_name := 'events_' || partition_value;
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS %I PARTITION OF events FOR VALUES IN (%L)',
      partition_name, partition_value
    );
  END LOOP;
END $$;
```
