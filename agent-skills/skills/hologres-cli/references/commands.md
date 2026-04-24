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

Export DDL for a table using hg_dump_script().

```bash
hologres schema dump public.my_table
hologres schema dump myschema.orders
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

## table

Table management commands.

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

## history

Show command history.

```bash
# Show recent 20 commands
hologres history

# Show more
hologres history -n 50
```

History is logged to `~/.hologres/sql-history.jsonl`.

## ai-guide

Generate AI agent guide with current schema and examples.

```bash
hologres ai-guide
```

Outputs a guide tailored for AI agents to interact with the database.
