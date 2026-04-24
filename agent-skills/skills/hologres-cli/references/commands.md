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
