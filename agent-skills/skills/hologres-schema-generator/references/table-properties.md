# Hologres Table Properties Reference

## Properties Overview

| Property | Column Store | Row Store | Row-Column Store | Alterable |
|----------|:----------:|:---------:|:----------------:|:---------:|
| `orientation` | Y | Y | Y | No |
| `distribution_key` | Y | Y | Y | No |
| `clustering_key` | Y | Ignored (uses PK) | Column part only | No |
| `event_time_column` | Y | Ignored | Column part only | No |
| `bitmap_columns` | Y | Ignored | Column part only | Yes |
| `dictionary_encoding_columns` | Y | Ignored | Column part only | Yes |
| `time_to_live_in_seconds` | Y | Y | Y | Yes |
| `storage_mode` | Y | Y | Y | Yes |
| `table_group` | Y | Y | Y | No |

## orientation (Storage Format)

Controls the physical storage layout of the table.

```sql
-- V2.1+ WITH syntax
WITH (orientation = 'column')
WITH (orientation = 'row')
WITH (orientation = 'row,column')

-- Legacy syntax
CALL set_table_property('table_name', 'orientation', 'column');
```

### Selection Flowchart

```
Query pattern?
  |
  +-- Mainly point lookups (WHERE pk = ?) --> 'row'
  |
  +-- Mainly OLAP (GROUP BY, aggregation, scan) --> 'column'
  |
  +-- Both point lookups AND analytics --> 'row,column'
  |
  +-- Unsure --> 'row,column' (safe default)
```

### Comparison

| Feature | Column Store | Row Store | Row-Column Store |
|---------|:----------:|:---------:|:----------------:|
| Full scan / aggregation | Fast | Slow | Fast |
| Point lookup by PK | Slow | Fast | Fast |
| Write throughput | High | Medium | Medium |
| Storage cost | Low (compressed) | Medium | Higher (stores both) |
| Primary key | Optional | Required | Required |
| Supports clustering_key | Yes | No (uses PK) | Yes (column part) |
| Supports bitmap_columns | Yes | No | Yes (column part) |

## distribution_key (Distribution Key)

Controls how rows are hash-distributed across shards.

```sql
-- Single column
WITH (distribution_key = 'user_id')

-- Two columns
WITH (distribution_key = 'order_id,user_id')

-- Legacy
CALL set_table_property('table_name', 'distribution_key', 'user_id');
```

### Selection Rules

1. **Choose JOIN key** -- Ensures co-located joins (local join, no shuffle)
2. **Choose GROUP BY key** -- Enables local aggregation
3. **High cardinality** -- Avoids data skew across shards
4. **Max 1-2 columns** -- More columns weaken distribution
5. **Must be subset of PK** -- If table has a primary key
6. **Immutable** -- Cannot change after table creation

### Common Patterns

| Scenario | distribution_key | Reason |
|----------|-----------------|--------|
| User table | `user_id` | Unique per user |
| Order table, joins user | `user_id` | Co-locate with user table |
| Event log | `event_id` or `user_id` | Even distribution or join alignment |
| Two-table join on A.x = B.x | Both use `x` | Local join |

### Anti-Patterns

| Bad Choice | Problem |
|-----------|---------|
| Low-cardinality column (status, gender) | Severe data skew |
| Timestamp column | All concurrent writes hit same shard |
| Too many columns (3+) | Hash distribution becomes random |
| Different keys for joined tables | Forces shuffle join |

## clustering_key (Clustering Key / Sorted Index)

Physically sorts data files. Accelerates range scans and range filters.

```sql
-- Ascending (default)
WITH (clustering_key = 'order_time:asc')

-- Multi-column with explicit order
WITH (clustering_key = 'ds:asc,order_time:desc')

-- Legacy
CALL set_table_property('table_name', 'clustering_key', 'order_time:asc');
```

### Selection Rules

1. **Use range-query columns** -- Columns with `>`, `<`, `BETWEEN`, `ORDER BY`
2. **Put highest-selectivity column first** -- Most filtered column first
3. **Max 2-3 columns** -- Diminishing returns with more
4. **Column store only** -- Row store uses PK as sort key
5. **Specify sort order** -- `:asc` (default) or `:desc`
6. **Immutable** -- Cannot change after table creation

### Interaction with event_time_column

```
Query: WHERE event_time BETWEEN ... AND ... AND status = 'active'
        |
        +-- event_time_column = 'event_time'  -> file-level pruning (coarse)
        +-- clustering_key = 'event_time:asc'  -> within-file range scan (fine)
        +-- bitmap_columns = 'status'          -> bitmap filter within files
```

## event_time_column (Segment Key)

Organizes data files by time ranges. Enables file-level pruning before data is read.

```sql
WITH (event_time_column = 'event_time')

-- Legacy
CALL set_table_property('table_name', 'event_time_column', 'event_time');
```

### Selection Rules

1. **Must be time-correlated column** -- Increasing over time
2. **Only 1 column** -- Cannot set multiple
3. **Column store only** -- Ignored for row store
4. **Best with TIMESTAMPTZ or TEXT date** -- ds (yyyyMMdd) or timestamp
5. **Combine with partition** -- Partition for coarse, segment for fine pruning
6. **Immutable** -- Cannot change after table creation

### When to Use vs. Partition

| Condition | Recommendation |
|-----------|---------------|
| Daily data < 100M rows | `event_time_column` only (no partition) |
| Daily data >= 100M rows | Partition + `event_time_column` |
| Non-time-based data | Neither (use clustering_key for filtering) |

## bitmap_columns (Bitmap Index)

Builds bitmap indexes for fast equality filtering.

```sql
WITH (bitmap_columns = 'status,payment_type,region')

-- Alterable after creation
ALTER TABLE table_name SET (bitmap_columns = 'status,payment_type,region,channel');

-- Legacy
CALL set_table_property('table_name', 'bitmap_columns', 'status,payment_type,region');
```

### Selection Rules

1. **Equality filter columns** -- `WHERE status = 'active'`, `WHERE region IN (...)`
2. **Low-to-medium cardinality** -- status (5), region (50), category (200)
3. **Column store only** -- Ignored for row store
4. **TEXT columns auto-enabled** -- No need to explicitly set for TEXT
5. **Alterable** -- Can add/remove after creation
6. **Avoid high-cardinality** -- user_id, order_id -- no benefit, wastes storage

### Recommended Cardinality

| Cardinality Range | Suitability |
|------------------|-------------|
| < 100 | Excellent |
| 100 ~ 10,000 | Good |
| 10,000 ~ 100,000 | Marginal |
| > 100,000 | Not recommended |

## dictionary_encoding_columns (Dictionary Encoding)

Compresses text by mapping to integers. Speeds up GROUP BY and filter on encoded columns.

```sql
WITH (dictionary_encoding_columns = 'country:auto,status:auto')

-- Alterable after creation
ALTER TABLE table_name SET (dictionary_encoding_columns = 'country:auto,status:auto');

-- Legacy
CALL set_table_property('table_name', 'dictionary_encoding_columns', 'country:auto,status:auto');
```

### Modes

| Mode | Description |
|------|-------------|
| `:auto` | Hologres decides based on cardinality (recommended) |
| `:on` | Force enable |
| `:off` | Force disable |

### Selection Rules

1. **Use `:auto` mode** -- Safest choice, let engine decide
2. **Good for low-cardinality text** -- country, status, category
3. **Avoid for high-cardinality** -- No compression benefit
4. **Column store only** -- Ignored for row store
5. **Alterable** -- Can change after creation

## time_to_live_in_seconds (TTL) — NOT RECOMMENDED

> **Do NOT use `time_to_live_in_seconds`.** The actual deletion time is non-deterministic — data will be deleted at an arbitrary time after the specified TTL, not at a precise point. This makes it unreliable for any data lifecycle management scenario.
>
> **Recommended alternative:** Use **dynamic partition management** — create daily/hourly partitions and drop old partitions on a schedule (via cron or external scheduling system). This gives precise, predictable lifecycle control.

### Syntax (for reference only)

```sql
-- NOT recommended
WITH (time_to_live_in_seconds = '2592000')  -- 30 days

-- Alterable after creation
ALTER TABLE table_name SET (time_to_live_in_seconds = '604800');  -- 7 days
```

### Why NOT to Use

| Problem | Description |
|---------|-------------|
| Non-deterministic deletion | Data is deleted at an arbitrary time AFTER the TTL, not at the precise TTL point |
| No visibility | Cannot predict or observe when deletion will actually happen |
| No atomicity | Partial data may be deleted while other rows in the same time range remain |
| Poor for compliance | Cannot guarantee data retention or deletion deadlines |

### Recommended Alternative: Partition-Based Lifecycle

```sql
-- Create table with daily partitions
CREATE TABLE events (
  event_id BIGINT NOT NULL,
  ds TEXT NOT NULL,
  PRIMARY KEY (ds, event_id)
) PARTITION BY LIST (ds)
WITH (orientation = 'column', distribution_key = 'event_id');

-- Drop old partitions on schedule (precise, deterministic)
-- e.g., retain 30 days: drop partitions older than 30 days via cron
DROP TABLE IF EXISTS events_20251101;
```

## storage_mode (Storage Tiering)

Controls hot/cold data storage placement.

```sql
WITH (storage_mode = 'hot')

-- Alterable
ALTER TABLE table_name SET (storage_mode = 'cold');
```

| Mode | Description |
|------|-------------|
| `hot` | SSD storage (default, fast) |
| `cold` | Cheaper storage (slow, for archival) |

## table_group

Associates the table with a specific Table Group for resource isolation.

```sql
WITH (table_group = 'my_group')
```

> **Note:** Table Group must be created in advance by an admin. Immutable after table creation.

## Property Selection Cheat Sheet

```
Step 1: Choose orientation
  - OLAP → 'column'
  - KV lookups → 'row'
  - Both / unsure → 'row,column'

Step 2: Set distribution_key
  - JOIN key or GROUP BY key
  - High cardinality, 1-2 columns
  - Must be PK subset

Step 3: Set clustering_key (column store only)
  - Range query columns
  - Time columns with :asc
  - Max 2-3 columns

Step 4: Set event_time_column (column store only)
  - Time/date column that increases
  - Only if time-range queries are common

Step 5: Set bitmap_columns (column store only)
  - WHERE = filter columns
  - Low-medium cardinality

Step 6: Data lifecycle
  - Use partition-based lifecycle (drop old partitions on schedule)
  - Do NOT use time_to_live_in_seconds (non-deterministic deletion)

Step 7: Consider partition
  - Only if daily data > 100M rows
```
