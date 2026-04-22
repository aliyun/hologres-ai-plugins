# Hologres CLI Command Reference

Complete command reference for Hologres CLI.

## Global Options

| Option | Description |
|--------|-------------|
| `--dsn` | Database connection string |
| `-f, --format` | Output format: json, table, csv, jsonl |
| `--no-mask` | Disable sensitive data masking |
| `--no-limit-check` | Disable row limit check |

## status

Check database connection status.

```bash
hologres status
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "connected": true,
    "server_version": "2.1.0",
    "database": "mydb"
  }
}
```

## instance

Query instance information.

```bash
hologres instance <instance_name>
```

**Example:**
```bash
hologres instance my_hologres_instance
```

**Output:** Instance version, max connections, and configuration.

## warehouse

List or query compute warehouses (计算组).

```bash
# List all warehouses
hologres warehouse

# Query specific warehouse
hologres warehouse <warehouse_name>
```

**Output:** Warehouse name, status, resource allocation.

## schema

Schema inspection commands.

### schema tables

List all tables in database.

```bash
hologres schema tables
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"schema": "public", "table_name": "users", "table_type": "table"},
      {"schema": "public", "table_name": "orders", "table_type": "table"}
    ],
    "count": 2
  }
}
```

### schema describe

Show table structure.

```bash
hologres schema describe <table_name>
hologres schema describe public.my_table
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "columns": [
      {"name": "id", "type": "bigint", "nullable": false},
      {"name": "name", "type": "text", "nullable": true}
    ]
  }
}
```

### schema dump

Export DDL statements.

```bash
# Dump all tables
hologres schema dump

# Dump specific table
hologres schema dump --table my_table
```

## sql

Execute SQL queries.

### Read-only queries

```bash
hologres sql "SELECT * FROM users LIMIT 10"
hologres sql "SELECT count(*) FROM orders"
```

### Write operations

Requires `--write` flag.

```bash
# INSERT
hologres sql --write "INSERT INTO logs VALUES (now(), 'event')"

# UPDATE (must have WHERE)
hologres sql --write "UPDATE users SET status='active' WHERE id=123"

# DELETE (must have WHERE)
hologres sql --write "DELETE FROM logs WHERE created_at < '2024-01-01'"
```

### Options

| Option | Description |
|--------|-------------|
| `--write` | Enable write operations |
| `--no-limit-check` | Disable row limit protection |
| `--no-mask` | Disable sensitive data masking |

## data

Data import/export commands.

### data export

Export table or query results.

```bash
# Export table to CSV
hologres data export my_table -f output.csv

# Export with custom query
hologres data export -q "SELECT * FROM users WHERE active=true" -f users.csv
```

### data import

Import data from file.

```bash
# Import CSV to table
hologres data import my_table -f input.csv

# Import with truncate (clear table first)
hologres data import my_table -f input.csv --truncate
```

### data count

Count rows in table.

```bash
# Count all rows
hologres data count my_table

# Count with filter
hologres data count my_table --where "status='active'"
```

## history

Show command history.

```bash
hologres history
hologres history -n 50
```

History is logged to `~/.hologres/sql-history.jsonl`.

## ai-guide

Generate AI agent guide.

```bash
hologres ai-guide
```

## dt (Dynamic Table V3.1+)

Full lifecycle management for Hologres Dynamic Tables using V3.1+ new syntax.

### dt create

Create a Dynamic Table.

```bash
# Minimal
hologres dt create -t my_dt --freshness "10 minutes" \
  -q "SELECT col1, SUM(col2) FROM src GROUP BY col1"

# With partitioning
hologres dt create -t ads_report --freshness "5 minutes" --refresh-mode auto \
  --logical-partition-key ds --partition-active-time "2 days" \
  --partition-time-format YYYY-MM-DD \
  --computing-resource serverless --serverless-cores 32 \
  -q "SELECT repo_name, COUNT(*) AS events, ds FROM src GROUP BY repo_name, ds"

# Incremental refresh
hologres dt create -t tpch_q1 --freshness "3 minutes" --refresh-mode incremental \
  -q "SELECT l_returnflag, l_linestatus, COUNT(*) FROM lineitem GROUP BY 1,2"

# Dry-run
hologres dt create -t my_dt --freshness "10 minutes" -q "SELECT 1" --dry-run
```

**Options:**

| Option | Description |
|--------|-------------|
| `-t, --table` | Table name `[schema.]table` (required) |
| `-q, --query` | SQL query defining the DT data (required) |
| `--freshness` | Data freshness target, e.g. `"10 minutes"` (required) |
| `--refresh-mode` | `auto` (default) / `full` / `incremental` |
| `--auto-refresh/--no-auto-refresh` | Enable/disable auto refresh |
| `--cdc-format` | `stream` (default) / `binlog` |
| `--computing-resource` | `local` / `serverless` (default) / `<warehouse_name>` |
| `--serverless-cores` | Serverless computing cores (when resource=serverless) |
| `--logical-partition-key` | Partition column for logical partition table |
| `--partition-active-time` | Active partition window, e.g. `"2 days"` |
| `--partition-time-format` | `YYYYMMDDHH24`, `YYYY-MM-DD`, `YYYYMMDD`, etc. |
| `--orientation` | `column` (default) / `row` / `row,column` |
| `--table-group` | Table Group name |
| `--distribution-key` | Distribution key columns (comma-separated) |
| `--clustering-key` | Clustering key, e.g. `"created_at:asc"` |
| `--event-time-column` | Event time column (Segment Key) |
| `--bitmap-columns` | Bitmap index columns (comma-separated) |
| `--dictionary-encoding-columns` | Dictionary encoding columns |
| `--ttl` | Data TTL in seconds |
| `--storage-mode` | `hot` (SSD, default) / `cold` (HDD/OSS) |
| `--columns` | Explicit column names (no types) |
| `--refresh-guc` | GUC params for refresh (repeatable), e.g. `timezone=GMT-8:00` |
| `--dry-run` | Preview SQL without executing |

### dt list

List all Dynamic Tables with refresh info.

```bash
hologres dt list
hologres dt list -f table
```

**Output:** schema_name, table_name, refresh_mode, freshness, auto_refresh, computing_resource.

### dt show

Show all properties of a Dynamic Table.

```bash
hologres dt show my_dt
hologres dt show public.my_dt -f table
```

**Output:** All property key-value pairs from `hologres.hg_dynamic_table_properties`.

### dt ddl

Show DDL (CREATE statement) of a Dynamic Table.

```bash
hologres dt ddl public.my_dt
```

**Output:** Full CREATE DYNAMIC TABLE statement via `hg_dump_script()`.

### dt lineage

Show dependency lineage of Dynamic Tables.

```bash
hologres dt lineage public.my_dt     # Single table
hologres dt lineage --all            # All DTs
hologres dt lineage my_dt -f table
```

**Output:** Dependency graph with base_table_type: `r`=ordinary table, `v`=view, `m`=materialized view, `f`=foreign table, `d`=Dynamic Table.

### dt storage

Show storage size breakdown of a Dynamic Table.

```bash
hologres dt storage public.my_dt
```

**Output:** Storage details via `hologres.hg_relation_size()`.

### dt state-size

Show state table storage size for incremental Dynamic Tables.

```bash
hologres dt state-size public.my_dt
```

**Output:** State table size. Note: if refresh mode is changed to full, state is auto-cleaned.

### dt refresh

Manually trigger a refresh.

```bash
hologres dt refresh my_dt
hologres dt refresh my_dt --overwrite --partition "ds = '2025-04-01'" --mode full
hologres dt refresh my_dt --dry-run
```

**Options:**

| Option | Description |
|--------|-------------|
| `--partition` | Partition value, e.g. `"ds = '2025-04-01'"` |
| `--mode` | Override: `full` / `incremental` |
| `--overwrite` | Use REFRESH OVERWRITE syntax |
| `--dry-run` | Preview SQL |

### dt alter

Alter properties of a Dynamic Table.

```bash
hologres dt alter my_dt --freshness "30 minutes"
hologres dt alter my_dt --no-auto-refresh
hologres dt alter my_dt --refresh-mode full --computing-resource serverless
hologres dt alter my_dt --refresh-guc timezone=GMT-8:00 --dry-run
```

**Options:**

| Option | Description |
|--------|-------------|
| `--freshness` | New freshness target |
| `--auto-refresh/--no-auto-refresh` | Toggle auto refresh |
| `--refresh-mode` | `auto` / `full` / `incremental` |
| `--computing-resource` | `local` / `serverless` / warehouse name |
| `--serverless-cores` | Serverless cores |
| `--partition-active-time` | Active partition window |
| `--refresh-guc` | GUC params (repeatable) |
| `--dry-run` | Preview SQL |

### dt drop

Drop a Dynamic Table. **Defaults to dry-run for safety.**

```bash
hologres dt drop my_dt               # Dry-run (preview only)
hologres dt drop my_dt --confirm     # Actually execute
hologres dt drop my_dt --if-exists --confirm
```

### dt convert

Convert Dynamic Table from V3.0 to V3.1 syntax.

```bash
hologres dt convert my_old_dt
hologres dt convert --all
hologres dt convert my_old_dt --dry-run
```

**Notes:**
- Requires Superuser privilege
- After conversion, auto-refresh enabled tables start immediately
- Only for non-partition tables; partition tables need manual recreation
