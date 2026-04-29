---
name: hologres-schema-generator
description: |
  Hologres DDL schema design and table creation expert. Use for generating CREATE TABLE statements,
  choosing storage formats (column/row/row-column), configuring table properties (distribution_key,
  clustering_key, bitmap_columns, event_time_column), designing partition tables, selecting data types,
  and optimizing table schemas for different query patterns.
  Triggers: "hologres建表", "hologres create table", "hologres schema", "hologres DDL",
  "distribution_key", "clustering_key", "bitmap_columns", "event_time_column", "列存", "行存",
  "行列共存", "分区表", "hologres table design", "表设计", "hologres数据类型"
---

## Prerequisites

This skill requires **hologres-cli** to be installed first:

```bash
pip install hologres-cli
```

All SQL execution depends on `hologres-cli` commands (`hologres sql run --write`, `hologres table create`).

# Hologres Schema Design & Table Creation

Generate optimized Hologres DDL statements with proper storage format, indexing, and distribution strategies.

## Information Gathering (IMPORTANT)

Before generating DDL, check whether the user has provided enough context. Many Hologres table properties are **immutable after creation** (orientation, distribution_key, clustering_key, event_time_column, primary key, partition column) — getting them wrong means recreating the table.

### Required Information

If ANY of the following are unclear, **ask the user before generating DDL**:

| Dimension | Why Critical | Example Question |
|-----------|-------------|-----------------|
| **Query pattern** | Determines `orientation` (column/row/row-column) | "This table is mainly used for OLAP analytics, KV point lookups, or both?" |
| **Column definitions** | Core schema structure | "Can you list the main columns and their rough types (text, number, timestamp, etc.)?" |
| **Primary key / unique key** | Determines UPSERT capability; immutable | "Does this table need deduplication or updates by a unique key? If so, which column(s)?" |
| **Main query conditions** | Determines distribution_key, clustering_key, bitmap | "What columns are most often used in WHERE, JOIN, or GROUP BY?" |

### Conditionally Required

Ask these only when relevant signals appear:

| Signal | Follow-up Question |
|--------|-------------------|
| Table looks like time-series or log data | "What is the estimated daily data volume? (determines whether to use partitioning)" |
| User mentions JOIN with other tables | "Which column will this table JOIN on, and what is the distribution_key of the other table?" |
| Large data volume or mentions retention | "How long should data be retained? (recommend dynamic partition management for lifecycle)" |
| User mentions both analytics and serving | "What is the read pattern — batch scans, point lookups by ID, or both?" |

### Can Use Defaults (No Need to Ask)

| Property | Default Behavior |
|----------|-----------------|
| `bitmap_columns` | Auto-enabled for TEXT columns; can ALTER later |
| `dictionary_encoding_columns` | Use `:auto` mode; can ALTER later |
| `storage_mode` | Default `hot`; can ALTER later |
| `time_to_live_in_seconds` | **Not recommended.** Deletion time is non-deterministic. Use dynamic partition management instead |

### Gathering Flow

```
User request → Check available info
  |
  +-- Columns + query pattern + key info all clear?
  |     → Generate DDL directly
  |
  +-- Missing critical info?
  |     → Ask 1-3 focused questions (batch them, don't ask one at a time)
  |
  +-- Very vague request (e.g., "help me create a user table")?
        → Ask: 1) main columns  2) query pattern  3) key/dedup needs
```

> **Principle:** Batch questions into a single round. Never ask more than 3-4 questions at once. If the user provides partial info, fill in reasonable defaults for the rest and explain your assumptions in comments.

## Storage Formats

Choose the storage format based on your primary query pattern.

| Format | Syntax | Best For | Primary Key |
|--------|--------|----------|-------------|
| **Column store** | `orientation = 'column'` | OLAP, aggregation, scan-heavy queries | Optional |
| **Row store** | `orientation = 'row'` | Point lookups, high-QPS KV queries | Required |
| **Row-column store** | `orientation = 'row,column'` | Mixed workloads (OLAP + point lookup) | Required |

> **Default recommendation:** Use `row,column` (row-column store) when the workload is unclear. It handles both OLAP and point queries well.

## Quick Start

```sql
-- Column store table (OLAP / analytics)
CREATE TABLE orders (
  order_id BIGINT NOT NULL,
  user_id BIGINT,
  amount DECIMAL(18,2),
  status TEXT,
  order_time TIMESTAMPTZ NOT NULL,
  ds TEXT NOT NULL,
  PRIMARY KEY (order_id)
)
PARTITION BY LIST (ds)
WITH (
  orientation = 'column',
  distribution_key = 'order_id',
  clustering_key = 'order_time:asc',
  event_time_column = 'order_time',
  bitmap_columns = 'status,user_id'
);

-- Row store table (high-QPS point lookup)
CREATE TABLE user_profile (
  user_id BIGINT NOT NULL,
  name TEXT,
  email TEXT,
  tags JSONB,
  updated_at TIMESTAMPTZ,
  PRIMARY KEY (user_id)
)
WITH (
  orientation = 'row',
  distribution_key = 'user_id',
  clustering_key = 'user_id'
);
```

## CREATE TABLE Syntax (V2.1+)

```sql
CREATE TABLE [IF NOT EXISTS] [schema.]table_name (
  column_name data_type [NOT NULL] [DEFAULT expr],
  ...
  [PRIMARY KEY (col1 [, col2, ...])]
)
[PARTITION BY LIST (partition_column)]
WITH (
  orientation = '{column | row | row,column}',
  distribution_key = 'col1[,col2]',
  clustering_key = 'col1[:asc|:desc][,col2[:asc|:desc]]',
  event_time_column = 'col',
  bitmap_columns = 'col1[,col2,...]',
  dictionary_encoding_columns = 'col1[:auto|:on|:off][,...]',
  time_to_live_in_seconds = 'N',          -- NOT recommended, see below
  storage_mode = '{hot | cold}',
  table_group = 'group_name'
);
```

### Legacy Syntax (All Versions)

```sql
BEGIN;
CREATE TABLE table_name (...);
CALL set_table_property('table_name', 'orientation', 'column');
CALL set_table_property('table_name', 'distribution_key', 'col1');
CALL set_table_property('table_name', 'clustering_key', 'col1:asc');
CALL set_table_property('table_name', 'event_time_column', 'col1');
CALL set_table_property('table_name', 'bitmap_columns', 'col1,col2');
COMMIT;
```

## Table Properties Reference

### distribution_key (Distribution Key)

Controls how data is hash-distributed across shards. Critical for JOIN and GROUP BY performance.

| Rule | Description |
|------|-------------|
| Choose high-cardinality columns | Avoid data skew |
| Use JOIN/GROUP BY columns | Enable local computation, avoid shuffle |
| Max 2 columns | More columns reduce distribution effectiveness |
| Must be subset of PK | If table has a primary key |
| Immutable after creation | Cannot ALTER, must recreate table |

```sql
-- Single column
distribution_key = 'user_id'

-- Two columns (join on both)
distribution_key = 'order_id,user_id'
```

### clustering_key (Clustering Key / Sorted Index)

Physically sorts data within files. Accelerates range queries and filters.

| Rule | Description |
|------|-------------|
| Use range-query columns | e.g., timestamp, date columns |
| Max 2-3 columns | More columns dilute sort benefit |
| Put high-selectivity column first | Most-filtered column goes first |
| Specify sort order | `:asc` (default) or `:desc` |
| Column store only | Row store uses PK as sort key |

```sql
clustering_key = 'order_time:asc'
clustering_key = 'ds:asc,order_time:asc'
```

### event_time_column (Segment Key)

Organizes data files by time ranges. Enables file-level pruning for time-range queries.

| Rule | Description |
|------|-------------|
| Use time/date columns | Timestamp of data ingestion or event time |
| At most 1 column | Only one segment key per table |
| Column store only | Not applicable to row store |
| Combine with partition | Partition for coarse pruning, segment key for fine pruning |

```sql
event_time_column = 'event_time'
```

### bitmap_columns (Bitmap Index)

Builds bitmap indexes for fast equality filtering on low-to-medium cardinality columns.

| Rule | Description |
|------|-------------|
| Use filter columns | Columns frequently in WHERE clause |
| Low-medium cardinality | status, type, region — NOT user_id |
| TEXT columns auto-enabled | Default bitmap for text columns |
| Can be added after creation | `ALTER TABLE ... SET (bitmap_columns = ...)` |

```sql
bitmap_columns = 'status,payment_type,region'
```

### dictionary_encoding_columns (Dictionary Encoding)

Compresses text columns by mapping values to integers. Speeds up GROUP BY and aggregations.

| Rule | Description |
|------|-------------|
| Use `:auto` mode | Let Hologres decide based on cardinality |
| Good for low-cardinality text | country, status, category |
| Avoid high-cardinality columns | user_id, order_id — no compression benefit |
| Don't set if unsure | Incorrect setting may hurt performance |

```sql
dictionary_encoding_columns = 'country:auto,status:auto'
```

### time_to_live_in_seconds (TTL) — NOT RECOMMENDED

> **Do NOT use `time_to_live_in_seconds`.** The actual deletion time is non-deterministic — data will be deleted at an arbitrary time after the specified TTL, not at a precise point. This makes it unreliable for data lifecycle management.
>
> **Recommended alternative:** Use **dynamic partition management** — create daily/hourly partitions and drop old partitions on a schedule (via cron or scheduling system). This gives you precise, predictable data lifecycle control.

```sql
-- BAD: TTL-based lifecycle (deletion time unpredictable)
-- time_to_live_in_seconds = '2592000'

-- GOOD: Partition-based lifecycle (precise control)
-- 1. Create table with daily partitions
CREATE TABLE events (
  event_id BIGINT NOT NULL,
  ds TEXT NOT NULL,
  PRIMARY KEY (ds, event_id)
) PARTITION BY LIST (ds)
WITH (orientation = 'column', distribution_key = 'event_id');

-- 2. Drop old partitions on schedule (e.g., retain 30 days)
DROP TABLE IF EXISTS events_20251101;  -- drop partition older than 30 days
```

## Primary Key Design

| Storage Format | PK Requirement | Notes |
|---------------|---------------|-------|
| Column store | Optional | Add PK only if needed for UPSERT |
| Row store | **Required** | PK drives the row-store index |
| Row-column store | **Required** | PK serves both point lookup and analytics |

**Rules:**
- Max 32 columns in composite PK
- PK columns must be NOT NULL and UNIQUE
- Prohibited types: `FLOAT`, `DOUBLE`, `NUMERIC`, `ARRAY`, `JSON`, `JSONB`
- PK cannot be altered after creation — must recreate table
- Avoid `SERIAL` as PK — causes table-level locks on write

## Partition Table Design

Use partitions for large tables with time-based or categorical data.

```sql
-- Parent table
CREATE TABLE events (
  event_id BIGINT NOT NULL,
  user_id BIGINT,
  event_type TEXT,
  ds TEXT NOT NULL,
  PRIMARY KEY (ds, event_id)
)
PARTITION BY LIST (ds)
WITH (
  orientation = 'column',
  distribution_key = 'event_id',
  clustering_key = 'ds:asc',
  event_time_column = 'ds'
);

-- Child partitions
CREATE TABLE events_20251201 PARTITION OF events FOR VALUES IN ('20251201');
CREATE TABLE events_20251202 PARTITION OF events FOR VALUES IN ('20251202');
```

**Rules:**
- Only `LIST` partitioning is supported
- Partition column must be part of PK (if PK exists)
- Supported partition column types: `TEXT`, `VARCHAR`, `INT`, `DATE` (V1.3.22+)
- Skip daily partitions if daily data < 100M rows — use `event_time_column` instead
- Always filter on partition column in queries for pruning

## Scenario-Based Templates

### 1. High-QPS Point Lookup (KV)

```sql
CREATE TABLE user_kv (
  user_id BIGINT NOT NULL PRIMARY KEY,
  profile JSONB,
  updated_at TIMESTAMPTZ
)
WITH (
  orientation = 'row',
  distribution_key = 'user_id'
);
```

### 2. Prefix Range Scan

```sql
CREATE TABLE order_lines (
  order_id BIGINT NOT NULL,
  line_no INT NOT NULL,
  product_id BIGINT,
  quantity INT,
  PRIMARY KEY (order_id, line_no)
)
WITH (
  orientation = 'row',
  distribution_key = 'order_id',
  clustering_key = 'order_id'
);
```

### 3. Time-Range Analytics (Partitioned)

```sql
CREATE TABLE page_views (
  view_id BIGINT NOT NULL,
  user_id BIGINT,
  page_url TEXT,
  view_time TIMESTAMPTZ,
  ds TEXT NOT NULL,
  PRIMARY KEY (ds, view_id)
)
PARTITION BY LIST (ds)
WITH (
  orientation = 'column',
  distribution_key = 'view_id',
  clustering_key = 'view_time:asc',
  event_time_column = 'view_time',
  bitmap_columns = 'user_id,page_url'
);
```

### 4. Dimension Filtering (Non-Time)

```sql
CREATE TABLE product_stats (
  product_id BIGINT NOT NULL PRIMARY KEY,
  category TEXT,
  brand TEXT,
  sales_count BIGINT,
  revenue DECIMAL(18,2)
)
WITH (
  orientation = 'column',
  distribution_key = 'product_id',
  clustering_key = 'category:asc',
  bitmap_columns = 'category,brand'
);
```

### 5. JOIN-Optimized Fact + Dimension

```sql
-- Fact table: distribute by join key
CREATE TABLE fact_orders (
  order_id BIGINT NOT NULL PRIMARY KEY,
  customer_id BIGINT,
  amount DECIMAL(18,2),
  order_date TEXT
)
WITH (
  orientation = 'column',
  distribution_key = 'customer_id'
);

-- Dimension table: same distribution key
CREATE TABLE dim_customers (
  customer_id BIGINT NOT NULL PRIMARY KEY,
  name TEXT,
  region TEXT
)
WITH (
  orientation = 'row,column',
  distribution_key = 'customer_id'
);
-- JOIN on customer_id → local join, no shuffle
```

### 6. Mixed Workload (OLAP + Serving)

```sql
CREATE TABLE realtime_metrics (
  metric_id BIGINT NOT NULL,
  device_id BIGINT NOT NULL,
  value DOUBLE PRECISION,
  ts TIMESTAMPTZ NOT NULL,
  ds TEXT NOT NULL,
  PRIMARY KEY (ds, device_id, metric_id)
)
PARTITION BY LIST (ds)
WITH (
  orientation = 'row,column',
  distribution_key = 'device_id',
  clustering_key = 'ts:asc',
  event_time_column = 'ts',
  bitmap_columns = 'device_id'
);
```

## References

| Document | Content |
|----------|---------|
| [data-types.md](references/data-types.md) | Complete data type reference |
| [table-properties.md](references/table-properties.md) | Detailed table property guide with selection flowcharts |
| [partition-guide.md](references/partition-guide.md) | Partition table design and management |

## Best Practices

1. **Choose storage format first** — column for OLAP, row for KV, row-column when unsure
2. **Set `distribution_key` to JOIN/GROUP BY columns** — avoids cross-shard shuffle
3. **Set `clustering_key` for range-query columns** — improves time-range and filter queries
4. **Set `event_time_column` for time-series data** — enables file-level pruning
5. **Use `bitmap_columns` for low-cardinality filter columns** — status, type, region
6. **Partition by date only if daily data > 100M rows** — otherwise use segment key alone
7. **PK must include partition column** — required by Hologres for partition tables
8. **Align `distribution_key` across JOINed tables** — same column enables local join
9. **Use `WITH` syntax (V2.1+)** — cleaner than `CALL set_table_property` in transactions
10. **Avoid `SERIAL` as primary key** — causes table-level write locks
