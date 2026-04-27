---
name: hologres-cli
description: |
  AI-agent-friendly Hologres CLI with safety guardrails and structured JSON output.
  Use for database operations, schema inspection, SQL execution, data import/export, Dynamic Table lifecycle management (V3.1+ syntax), and GUC parameter management.
  Triggers: "hologres cli", "hologres command", "hologres database", "dynamic table", "hologres查询", "hologres guc", "GUC parameter"
---

# Hologres CLI

AI-agent-friendly command-line interface for Hologres with safety guardrails and structured JSON output.

## Installation

```bash
# Requires Python 3.11+
cd hologres-cli
pip install -e .
```

## Configuration

DSN format: `hologres://[user[:password]@]host[:port]/database`

Priority: `--dsn` flag > `HOLOGRES_DSN` env > `~/.hologres/config.env`

## Quick Start

```bash
export HOLOGRES_DSN="hologres://user:pass@endpoint:port/database"
hologres status
hologres schema tables
hologres sql "SELECT * FROM orders LIMIT 10"
hologres dt list
```

## Core Commands

| Command | Description |
|---------|-------------|
| `hologres status` | Check connection status |
| `hologres instance <name>` | Query instance version/connections |
| `hologres warehouse [name]` | List or query warehouses |
| `hologres schema tables` | List all tables |
| `hologres schema describe <table>` | Show table structure |
| `hologres schema dump <schema.table>` | Export DDL |
| `hologres schema size <schema.table>` | Get table storage size |
| `hologres table list [--schema S]` | List all tables |
| `hologres table create -n TABLE -c COLS [options] [--dry-run]` | Create a table (compatible syntax) |
| `hologres table dump <schema.table>` | Export DDL for a table |
| `hologres table show <table>` | Show table structure (columns, types, nullable, defaults, primary key, comments) |
| `hologres table size <schema.table>` | Get table storage size |
| `hologres table properties <table>` | Show Hologres-specific table properties (orientation, distribution_key, clustering_key, TTL, etc.) |
| `hologres table drop <table> [--if-exists] [--cascade] --confirm` | Drop a table (dry-run by default) |
| `hologres table truncate <table> --confirm` | Truncate (empty) a table (dry-run by default) |
| `hologres view list [--schema S]` | List all views |
| `hologres view show <view>` | Show view definition and structure |
| `hologres extension list` | List installed extensions |
| `hologres extension create <name> [--if-not-exists]` | Create (install) a database extension |
| `hologres guc show <param>` | Show current value of a GUC parameter |
| `hologres guc set <param> <value>` | Set GUC parameter at database level (persistent) |
| `hologres sql run "<query>"` | Execute read-only SQL |
| `hologres sql run --write "<dml>"` | Execute write SQL |
| `hologres sql explain "<query>"` | Show SQL execution plan |
| `hologres data export <table> -f out.csv [-q <query>] [-d <delimiter>]` | Export to CSV |
| `hologres data import <table> -f in.csv [-d <delimiter>] [--truncate]` | Import from CSV |
| `hologres data count <table> [-w <where>]` | Count rows |
| `hologres history [-n <count>]` | Show command history |
| `hologres ai-guide` | Generate AI agent guide |

## Dynamic Table Commands (V3.1+)

Full lifecycle management for Hologres Dynamic Tables.

| Command | Description |
|---------|-------------|
| `hologres dt create` | Create a Dynamic Table |
| `hologres dt list` | List all Dynamic Tables |
| `hologres dt show <table>` | Show Dynamic Table properties |
| `hologres dt ddl <table>` | Show DDL (CREATE statement) |
| `hologres dt lineage <table>` | Show dependency lineage |
| `hologres dt lineage --all` | Show lineage for all DTs |
| `hologres dt storage <table>` | Show storage details |
| `hologres dt state-size <table>` | Show state table size (incremental) |
| `hologres dt refresh <table>` | Trigger manual refresh |
| `hologres dt alter <table>` | Alter DT properties |
| `hologres dt drop <table>` | Drop DT (dry-run by default) |
| `hologres dt convert [table]` | Convert V3.0 → V3.1 syntax |

### dt create

```bash
# Minimal
hologres dt create -t my_dt --freshness "10 minutes" \
  -q "SELECT col1, SUM(col2) FROM src GROUP BY col1"

# With partitioning and serverless
hologres dt create -t ads_report --freshness "5 minutes" --refresh-mode auto \
  --logical-partition-key ds --partition-active-time "2 days" \
  --partition-time-format YYYY-MM-DD \
  --computing-resource serverless --serverless-cores 32 \
  -q "SELECT repo_name, COUNT(*) AS events, ds FROM src GROUP BY repo_name, ds"

# Incremental refresh
hologres dt create -t tpch_q1 --freshness "3 minutes" --refresh-mode incremental \
  -q "SELECT l_returnflag, l_linestatus, COUNT(*) FROM lineitem GROUP BY 1,2"

# Dry-run (preview SQL without executing)
hologres dt create -t my_dt --freshness "10 minutes" -q "SELECT 1" --dry-run
```

**Key create options:**

| Option | Description |
|--------|-------------|
| `-t, --table` | Table name `[schema.]table` (required) |
| `-q, --query` | SQL query for data definition (required) |
| `--freshness` | Data freshness target, e.g. `"10 minutes"` (required) |
| `--refresh-mode` | `auto` / `full` / `incremental` |
| `--auto-refresh/--no-auto-refresh` | Enable/disable auto refresh |
| `--cdc-format` | `stream` (default) / `binlog` |
| `--computing-resource` | `local` / `serverless` / `<warehouse>` |
| `--serverless-cores` | Serverless computing cores |
| `--logical-partition-key` | Partition column for logical partition |
| `--partition-active-time` | Active partition window, e.g. `"2 days"` |
| `--partition-time-format` | Partition key format, e.g. `YYYY-MM-DD` |
| `--orientation` | `column` / `row` / `row,column` |
| `--distribution-key` | Distribution key columns |
| `--clustering-key` | Clustering key with sort order |
| `--event-time-column` | Event time column (Segment Key) |
| `--ttl` | Data TTL in seconds |
| `--refresh-guc` | GUC params for refresh (repeatable) |
| `--dry-run` | Preview SQL without executing |

### dt list / show / ddl

```bash
hologres dt list                     # List all DTs with refresh info
hologres dt show public.my_dt        # Show all properties
hologres dt ddl public.my_dt         # Show CREATE statement
hologres dt list -f table            # Table format output
```

### dt lineage

```bash
hologres dt lineage public.my_dt     # Single table lineage
hologres dt lineage --all            # All DTs lineage
hologres dt lineage my_dt -f table   # Table format
```

base_table_type: `r`=table, `v`=view, `m`=materialized view, `f`=foreign table, `d`=Dynamic Table.

### dt storage / state-size

```bash
hologres dt storage public.my_dt      # Storage breakdown
hologres dt state-size public.my_dt   # State table size (incremental DTs)
```

### dt refresh

```bash
hologres dt refresh my_dt
hologres dt refresh my_dt --overwrite --partition "ds = '2025-04-01'" --mode full
hologres dt refresh my_dt --dry-run
```

### dt alter

```bash
hologres dt alter my_dt --freshness "30 minutes"
hologres dt alter my_dt --no-auto-refresh
hologres dt alter my_dt --refresh-mode full --computing-resource serverless
hologres dt alter my_dt --refresh-guc timezone=GMT-8:00 --dry-run
```

### dt drop

```bash
hologres dt drop my_dt               # Dry-run by default (safety)
hologres dt drop my_dt --confirm     # Actually drop
hologres dt drop my_dt --if-exists --confirm
```

### dt convert (V3.0 → V3.1)

```bash
hologres dt convert my_old_dt          # Convert single table
hologres dt convert --all              # Convert all V3.0 tables
hologres dt convert my_old_dt --dry-run
```

## Output Formats

```bash
hologres -f json schema tables    # JSON (default)
hologres -f table schema tables   # Human-readable table
hologres -f csv schema tables     # CSV
hologres -f jsonl schema tables   # JSON Lines
```

### Response Structure

```json
// Success
{"ok": true, "data": {"rows": [...], "count": 10}}

// Error
{"ok": false, "error": {"code": "ERROR_CODE", "message": "..."}}
```

## Safety Features

### 1. Row Limit Protection
Queries without `LIMIT` returning >100 rows fail with `LIMIT_REQUIRED`.

```bash
# Will fail if >100 rows
hologres sql run "SELECT * FROM large_table"

# Fix: add LIMIT
hologres sql run "SELECT * FROM large_table LIMIT 50"

# Or disable check
hologres sql run --no-limit-check "SELECT * FROM large_table"
```

### 2. Write Protection
Write operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT, REVOKE) require `--write` flag.

```bash
hologres sql run --write "INSERT INTO logs VALUES (1, 'test')"
```

### 3. Dangerous Write Blocking
DELETE/UPDATE without WHERE clause are blocked.

```bash
# Blocked
hologres sql run --write "DELETE FROM users"

# Must have WHERE
hologres sql run --write "DELETE FROM users WHERE status='inactive'"
```

## Error Codes

| Code | Description |
|------|-------------|
| `CONNECTION_ERROR` | Failed to connect |
| `QUERY_ERROR` | SQL execution error |
| `LIMIT_REQUIRED` | Need LIMIT clause |
| `WRITE_BLOCKED` | Write operation not allowed |
| `NOT_FOUND` | Table or resource not found |
| `INVALID_ARGS` | Invalid or missing arguments |
| `NO_CHANGES` | No properties specified to alter |
| `EXPORT_ERROR` | Data export failed |
| `IMPORT_ERROR` | Data import failed |
| `VIEW_NOT_FOUND` | View not found |

## Sensitive Data Masking

Auto-masks by column name pattern:
- phone/mobile/tel → `138****5678`
- email → `j***@example.com`
- password/secret/token → `********`

Disable: `hologres sql run --no-mask "SELECT * FROM users LIMIT 10"`

## References

| Document | Content |
|----------|--------|
| [commands.md](references/commands.md) | Complete command reference with DT commands |
| [safety-features.md](references/safety-features.md) | Safety guardrails details |

## Best Practices

1. Always use `LIMIT` for large result sets
2. Use `--dry-run` to preview DT SQL before executing
3. Use `--confirm` explicitly for destructive operations (table drop, table truncate, dt drop)
4. Include `WHERE` clause in DELETE/UPDATE
5. Use JSON output for automation/scripting
6. Check `hologres status` before batch operations
7. Use `hologres dt lineage` to understand DT dependencies before altering
