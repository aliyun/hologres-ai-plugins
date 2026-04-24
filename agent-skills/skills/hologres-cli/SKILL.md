---
name: hologres-cli
description: |
  AI-agent-friendly Hologres CLI with safety guardrails and structured JSON output.
  Use for database operations, schema inspection, SQL execution, and data import/export.
  Triggers: "hologres cli", "hologres command", "hologres database", "hologres查询"
---

# Hologres CLI

AI-agent-friendly command-line interface for Hologres with safety guardrails and structured JSON output.

## Installation

```bash
# Requires Python 3.11+
cd hologres-cli
pip install -e .

# Or using uv
uv venv --python 3.11 && source .venv/bin/activate && uv pip install -e .
```

## Configuration

### DSN Format
```
hologres://[user[:password]@]host[:port]/database
```

### Configuration Priority
1. CLI flag: `--dsn "hologres://user:pass@host:port/db"`
2. Environment variable: `export HOLOGRES_DSN="hologres://..."`
3. Config file: `~/.hologres/config.env`

## Quick Start

```bash
# Set connection
export HOLOGRES_DSN="hologres://user:pass@endpoint:port/database"

# Check connection
hologres status

# List tables
hologres schema tables

# Query data (JSON output by default)
hologres sql run "SELECT * FROM orders LIMIT 10"
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
| `hologres table dump <schema.table>` | Export DDL for a table |
| `hologres sql run "<query>"` | Execute read-only SQL |
| `hologres sql run --write "<dml>"` | Execute write SQL |
| `hologres data export <table> -f out.csv` | Export to CSV |
| `hologres data import <table> -f in.csv` | Import from CSV |
| `hologres data count <table>` | Count rows |
| `hologres history` | Show command history |
| `hologres ai-guide` | Generate AI agent guide |

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
| `WRITE_GUARD_ERROR` | Missing --write flag |
| `DANGEROUS_WRITE_BLOCKED` | DELETE/UPDATE without WHERE |
| `WRITE_BLOCKED` | Write operation not allowed |
| `EXPORT_ERROR` | Data export failed |
| `IMPORT_ERROR` | Data import failed |

## Sensitive Data Masking

Auto-masks by column name pattern:
- phone/mobile/tel → `138****5678`
- email → `j***@example.com`
- password/secret/token → `********`

Disable: `hologres sql run --no-mask "SELECT * FROM users LIMIT 10"`

## References

| Document | Content |
|----------|---------|
| [commands.md](references/commands.md) | Complete command reference |
| [safety-features.md](references/safety-features.md) | Safety guardrails details |

## Best Practices

1. Always use `LIMIT` for large result sets
2. Use `--write` flag explicitly for write operations
3. Include `WHERE` clause in DELETE/UPDATE
4. Use JSON output for automation/scripting
5. Check `hologres status` before batch operations
