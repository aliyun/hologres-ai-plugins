# Hologres CLI Command Reference

Complete command reference for Hologres CLI.

## Global Options

| Option | Description |
|--------|-------------|
| `--profile, -p` | Use named profile from config |
| `-f, --format` | Output format: json, table, csv, jsonl |
| `--version` | Show version and exit |

## config

Manage Hologres CLI configuration profiles.

### config (no subcommand)

Run interactive configuration wizard.

```bash
hologres config
hologres config --profile prod
```

### config list

List all profiles with current marker.

```bash
hologres config list
```

### config show

Show current profile details (sensitive fields masked).

```bash
hologres config show
hologres config show --profile prod
```

### config current

Show current active profile name.

```bash
hologres config current
```

### config switch

Switch active profile.

```bash
hologres config switch prod
```

### config set

Set a configuration value.

```bash
hologres config set region_id cn-shanghai
hologres config set database mydb
hologres config set auth_mode basic
```

Settable keys: `region_id`, `instance_id`, `nettype`, `auth_mode`, `access_key_id`, `access_key_secret`, `username`, `password`, `database`, `warehouse`, `endpoint`, `port`, `output_format`, `language`.

### config get

Get a configuration value.

```bash
hologres config get region_id
hologres config get database
```

### config delete

Delete a profile (requires `--confirm`).

```bash
hologres config delete old-profile --confirm
```

## status

Check database connection status.

```bash
hologres status
hologres --profile prod status
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

Export DDL for a table using hg_dump_script().

```bash
hologres schema dump public.my_table
hologres schema dump myschema.orders
```

### schema size

Get storage size of a table using pg_relation_size().

```bash
hologres schema size public.my_table
hologres schema size myschema.orders
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "schema": "public",
    "table": "my_table",
    "size": "123 MB",
    "size_bytes": 128974848
  }
}
```

## sql

Execute SQL queries.

### sql run

Execute a SQL query (read-only by default).

### Read-only queries

```bash
hologres sql run "SELECT * FROM users LIMIT 10"
hologres sql run "SELECT count(*) FROM orders"
```

### Write operations

Requires `--write` flag.

```bash
# INSERT
hologres sql run --write "INSERT INTO logs VALUES (now(), 'event')"

# UPDATE (must have WHERE)
hologres sql run --write "UPDATE users SET status='active' WHERE id=123"

# DELETE (must have WHERE)
hologres sql run --write "DELETE FROM logs WHERE created_at < '2024-01-01'"
```

### Options

| Option | Description |
|--------|-------------|
| `--write` | Enable write operations |
| `--no-limit-check` | Disable row limit protection |
| `--no-mask` | Disable sensitive data masking |
| `--with-schema` | Include column name/type info in output |

### sql explain

Show execution plan for a SQL query.

```bash
hologres sql explain "SELECT * FROM orders"
hologres sql explain "SELECT * FROM orders WHERE status = 'active'"
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "plan": [
      "Seq Scan on orders  (cost=0.00..35.50 rows=2550 width=36)",
      "  Filter: (status = 'active'::text)"
    ],
    "query": "SELECT * FROM orders WHERE status = 'active'"
  }
}
```

## data

Data import/export commands.

### data export

Export table or query results.

```bash
# Export table to CSV
hologres data export my_table -f output.csv

# Export with custom query
hologres data export -q "SELECT * FROM users WHERE active=true" -f users.csv

# Export with custom delimiter
hologres data export my_table -f output.csv --delimiter '|'
```

### data import

Import data from file.

```bash
# Import CSV to table
hologres data import my_table -f input.csv

# Import with truncate (clear table first)
hologres data import my_table -f input.csv --truncate

# Import with custom delimiter
hologres data import my_table -f input.csv --delimiter '|'
```

### data count

Count rows in table.

```bash
# Count all rows
hologres data count my_table

# Count with filter
hologres data count my_table --where "status='active'"
```

## table

Table management commands.

### table create

Create a new table. Regular/physical partition tables use `CALL set_table_property` (compatible syntax).
Logical partition tables (V3.1+) use `WITH(...)` syntax.

```bash
# Minimal creation
hologres table create --name public.my_table \
  --columns "id BIGINT NOT NULL, name TEXT"

# Full example with properties
hologres table create --name public.orders \
  --columns "order_id BIGINT NOT NULL, user_id INT, amount DECIMAL(10,2), created_at TIMESTAMPTZ" \
  --primary-key order_id --orientation column \
  --distribution-key order_id --clustering-key "created_at:asc" \
  --ttl 7776000 --dry-run

# Physical partition table
hologres table create --name public.events \
  --columns "event_id BIGINT NOT NULL, ds TEXT NOT NULL, payload JSONB" \
  --primary-key "event_id,ds" --partition-by ds \
  --orientation column

# Row-store table (point lookup)
hologres table create --name public.dim_user \
  --columns "user_id TEXT NOT NULL, user_level INT, data JSONB" \
  --primary-key user_id --orientation row

# Logical partition table (V3.1+)
hologres table create --name public.logs \
  --columns "a TEXT, b INT, ds DATE NOT NULL" \
  --primary-key "b,ds" --partition-by ds \
  --partition-mode logical --orientation column \
  --distribution-key b \
  --partition-expiration-time "30 day" \
  --partition-keep-hot-window "15 day" \
  --partition-require-filter true \
  --binlog replica --binlog-ttl 86400 --dry-run

# Logical partition table with two partition keys
hologres table create --name public.events_2pk \
  --columns "a TEXT, b INT, yy TEXT NOT NULL, mm TEXT NOT NULL" \
  --partition-by "yy, mm" --partition-mode logical \
  --orientation column --partition-require-filter true --dry-run
```

**Options:**

| Option | Description |
|--------|-------------|
| `--name, -n TABLE` | Table name `[schema.]table_name` (required) |
| `--columns, -c COLS` | Column definitions (required) |
| `--primary-key PK` | Primary key columns (comma-separated) |
| `--orientation` | `column` (default) / `row` / `row,column` |
| `--distribution-key` | Distribution key columns |
| `--clustering-key` | Clustering key with sort order, e.g. `created_at:asc` |
| `--event-time-column` | Event time column (Segment Key) |
| `--bitmap-columns` | Bitmap index columns (comma-separated) |
| `--dictionary-encoding-columns` | Dictionary encoding columns |
| `--ttl SECONDS` | Data TTL in seconds |
| `--storage-mode` | `hot` (SSD) / `cold` (HDD/OSS) |
| `--table-group` | Table Group name |
| `--partition-by COL` | Enable LIST partition on this column(s). Supports up to 2 columns for logical partition |
| `--partition-mode` | `physical` (default) / `logical` (V3.1+) |
| `--binlog` | Binlog level: `none` / `replica` |
| `--binlog-ttl` | Binlog TTL in seconds (default: 2592000 = 30 days) |
| `--partition-expiration-time` | Partition expiration time (logical only). E.g. `'30 day'` |
| `--partition-keep-hot-window` | Partition hot storage window (logical only). E.g. `'15 day'` |
| `--partition-require-filter` | Require partition filter in queries (logical only): `true` / `false` |
| `--partition-generate-binlog-window` | Binlog generation window (logical only). E.g. `'3 day'` |
| `--if-not-exists` | Add IF NOT EXISTS clause |
| `--dry-run` | Only display the SQL without executing |

**Note on SQL syntax:**
- Regular/physical partition tables generate `BEGIN; CREATE TABLE ...; CALL set_table_property(...); COMMIT;`
- Logical partition tables generate `CREATE TABLE ... LOGICAL PARTITION BY LIST (...) WITH (...);`
- Property names differ between syntaxes: `WITH` uses underscores (`binlog_level`), `CALL` uses dots (`binlog.level`)

**Dry-run output (regular table):**
```json
{
  "ok": true,
  "data": {
    "sql": "BEGIN;\n\nCREATE TABLE public.orders (\n    ...\n);\n\nCALL set_table_property(...);\n\nCOMMIT;",
    "dry_run": true
  },
  "message": "SQL generated (dry-run mode)"
}
```

**Dry-run output (logical partition table):**
```json
{
  "ok": true,
  "data": {
    "sql": "CREATE TABLE public.logs (\n    ...\n)\nLOGICAL PARTITION BY LIST (ds)\nWITH (\n    ...\n);",
    "dry_run": true
  },
  "message": "SQL generated (dry-run mode)"
}
```

**Executed output:**
```json
{
  "ok": true,
  "data": {
    "sql": "...",
    "executed": true
  },
  "message": "Table created successfully"
}
```

### table list

List all tables in the database (excluding system schemas).

```bash
# List all tables
hologres table list

# Filter by schema
hologres table list --schema public
hologres table list -s myschema
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"schema": "public", "table_name": "users", "owner": "admin"},
      {"schema": "public", "table_name": "orders", "owner": "admin"}
    ],
    "count": 2
  }
}
```

### table dump

Export DDL for a table using hg_dump_script().

```bash
hologres table dump public.my_table
hologres table dump myschema.orders
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "schema": "public",
    "table": "my_table",
    "ddl": "CREATE TABLE public.my_table (...);"
  }
}
```

### table show

Show table structure: columns, types, nullable, defaults, primary key, comments.

```bash
hologres table show my_table
hologres table show public.my_table
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "schema": "public",
    "table": "users",
    "primary_key": ["id"],
    "columns": [
      {"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": null, "ordinal_position": 1, "comment": "primary id"},
      {"column_name": "name", "data_type": "text", "is_nullable": "YES", "column_default": null, "ordinal_position": 2, "comment": "user name"}
    ]
  }
}
```

### table size

Get storage size of a table using pg_relation_size().

```bash
hologres table size public.my_table
hologres table size myschema.orders
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "schema": "public",
    "table": "my_table",
    "size": "123 MB",
    "size_bytes": 128974848
  }
}
```

### table properties

Show Hologres-specific table properties (orientation, distribution_key, clustering_key, TTL, etc.).

```bash
hologres table properties my_table
hologres table properties public.my_table
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"property_key": "orientation", "property_value": "column"},
      {"property_key": "distribution_key", "property_value": "user_id"},
      {"property_key": "clustering_key", "property_value": "created_at:asc"},
      {"property_key": "time_to_live_in_seconds", "property_value": "2592000"}
    ],
    "count": 4
  }
}
```

### table drop

Drop a table from the database. **Defaults to dry-run for safety.**

```bash
hologres table drop my_table               # Dry-run (preview only)
hologres table drop my_table --confirm     # Actually execute
hologres table drop my_table --if-exists --confirm
hologres table drop my_table --cascade --confirm
```

**Options:**

| Option | Description |
|--------|-------------|
| `--if-exists` | Add IF EXISTS clause. No error if table does not exist |
| `--cascade` | Add CASCADE clause to drop dependent objects too |
| `--confirm` | [REQUIRED to execute] Confirm the drop operation. Without --confirm, only dry-run SQL is shown |

**Dry-run output:**
```json
{
  "ok": true,
  "data": {
    "sql": "DROP TABLE public.my_table",
    "dry_run": true
  },
  "message": "SQL generated (dry-run mode)"
}
```

**Executed output:**
```json
{
  "ok": true,
  "data": {
    "sql": "DROP TABLE public.my_table",
    "executed": true
  },
  "message": "Statement executed successfully"
}
```

### table truncate

Truncate (empty) a table. **Defaults to dry-run for safety.**

```bash
hologres table truncate my_table               # Dry-run (preview only)
hologres table truncate my_table --confirm     # Actually execute
```

**Options:**

| Option | Description |
|--------|-------------|
| `--confirm` | [REQUIRED to execute] Confirm the truncate operation. Without --confirm, only dry-run SQL is shown |

**Dry-run output:**
```json
{
  "ok": true,
  "data": {
    "sql": "TRUNCATE TABLE public.my_table",
    "dry_run": true
  },
  "message": "SQL generated (dry-run mode)"
}
```

**Executed output:**
```json
{
  "ok": true,
  "data": {
    "sql": "TRUNCATE TABLE public.my_table",
    "executed": true
  },
  "message": "Statement executed successfully"
}
```

## view

View management commands.

### view list

List all views in the database (excluding system schemas).

```bash
# List all views
hologres view list

# Filter by schema
hologres view list --schema public
hologres view list -s myschema
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"schema": "public", "view_name": "active_users", "owner": "admin"},
      {"schema": "analytics", "view_name": "daily_stats", "owner": "analyst"}
    ],
    "count": 2
  }
}
```

### view show

Show view structure: definition, columns, types, nullable, defaults, comments.

```bash
# Show view in public schema
hologres view show my_view

# Show view in specific schema
hologres view show analytics.daily_stats
```

**Output (JSON):**
```json
{
  "ok": true,
  "data": {
    "schema": "public",
    "view": "active_users",
    "owner": "admin",
    "definition": "SELECT id, name FROM users WHERE active = true",
    "columns": [
      {"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": null, "ordinal_position": 1, "comment": ""},
      {"column_name": "name", "data_type": "character varying", "is_nullable": "YES", "column_default": null, "ordinal_position": 2, "comment": ""}
    ]
  }
}
```

**Error (view not found):**
```json
{
  "ok": false,
  "error": {"code": "VIEW_NOT_FOUND", "message": "View 'public.nonexistent' not found"}
}
```

## partition

Partition management commands. Currently supports logical partition tables only.

### partition list

List partitions of a logical partition table.

```bash
hologres partition list <table>
hologres partition list public.logs
hologres partition list my_table        # defaults to public schema
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"partition": "2025-04-01"},
      {"partition": "2025-04-02"},
      {"partition": "2025-04-03"}
    ],
    "count": 3
  }
}
```

**Error (not a logical partition table):**
```json
{
  "ok": false,
  "error": {"code": "NOT_LOGICAL_PARTITION", "message": "Table 'public.my_table' is not a logical partition table. Only logical partition tables are supported."}
}
```

**Error (table not found):**
```json
{
  "ok": false,
  "error": {"code": "TABLE_NOT_FOUND", "message": "Table 'public.nonexistent' not found"}
}
```

### partition create

Create a partition for a logical partition table. Since logical partition tables create partitions automatically when data is inserted, this command is a no-op and returns a notice.

```bash
hologres partition create my_table
hologres partition create public.logs
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "notice": "Logical partition tables create partitions automatically when data is inserted. No explicit CREATE PARTITION is needed."
  },
  "message": "No action required"
}
```

### partition drop

Drop a partition from a logical partition table by deleting all rows matching the partition value. The partition disappears automatically after data is removed. **Defaults to dry-run for safety.**

```bash
# Single partition column
hologres partition drop my_table --partition "2025-04-01"              # dry-run
hologres partition drop my_table --partition "2025-04-01" --confirm    # execute

# Key=value format (also works for single column)
hologres partition drop my_table --partition "ds=2025-04-01" --confirm

# Multiple partition columns
hologres partition drop public.events --partition "yy=2025,mm=04" --confirm
```

**Options:**

| Option | Description |
|--------|-------------|
| `--partition VALUE` | Partition value to drop. Single column: `"2025-04-01"`. Multiple columns: `"yy=2025,mm=04"` (required) |
| `--confirm` | [REQUIRED to execute] Confirm the drop operation. Without --confirm, only dry-run SQL is shown |

**Dry-run output:**
```json
{
  "ok": true,
  "data": {
    "sql": "DELETE FROM public.logs WHERE ds = '2025-04-01'",
    "dry_run": true
  },
  "message": "SQL generated (dry-run mode)"
}
```

**Executed output:**
```json
{
  "ok": true,
  "data": {
    "sql": "DELETE FROM public.logs WHERE ds = '2025-04-01'",
    "executed": true
  },
  "message": "Partition dropped successfully"
}
```

**Dry-run output (multiple partition columns):**
```json
{
  "ok": true,
  "data": {
    "sql": "DELETE FROM public.events WHERE yy = '2025' AND mm = '04'",
    "dry_run": true
  },
  "message": "SQL generated (dry-run mode)"
}
```

## extension

Extension management commands.

### extension list

List installed extensions in the database.

```bash
hologres extension list
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"name": "plpgsql", "version": "1.0", "schema": "pg_catalog"},
      {"name": "roaring_bitmap", "version": "0.5", "schema": "public"}
    ],
    "count": 2
  }
}
```

### extension create

Create (install) a database extension.

```bash
hologres extension create roaring_bitmap
hologres extension create postgis --if-not-exists
```

**Options:**

| Option | Description |
|--------|-------------|
| `--if-not-exists` | Do not error if extension already exists |

**Common extensions:**
- `flow_analysis` (漏斗/留存)
- `roaring_bitmap`
- `postgis`
- `hstore`
- `hologres_fdw` (跨库)

**Output:**
```json
{
  "ok": true,
  "data": {
    "extension": "roaring_bitmap",
    "created": true
  }
}
```

## guc

GUC parameter management commands.

### guc show

Show the current value of a GUC parameter.

```bash
hologres guc show <param_name>
```

**Example:**
```bash
hologres guc show optimizer_join_order
hologres guc show statement_timeout
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "param": "optimizer_join_order",
    "value": "exhaustive"
  }
}
```

### guc set

Set a GUC parameter at the database level (persistent).

This executes `ALTER DATABASE` to set the parameter, which persists across sessions and applies to all new connections to the database.

```bash
hologres guc set <param_name> <value>
```

**Example:**
```bash
hologres guc set optimizer_join_order query
hologres guc set statement_timeout '5min'
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "param": "optimizer_join_order",
    "value": "query",
    "scope": "database",
    "database": "mydb"
  }
}
```

> **Note:** The change takes effect for new sessions. Current sessions retain the old value.

## history

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
