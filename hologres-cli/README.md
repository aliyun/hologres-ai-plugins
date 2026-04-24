# Hologres CLI

AI-agent-friendly command-line interface for Hologres database with safety guardrails and structured JSON output.

## Features

- **Structured Output**: All commands return JSON by default for easy parsing
- **Safety Guardrails**: Row limits, write protection, dangerous operation blocking
- **Multiple Formats**: JSON, table, CSV, JSONL output formats
- **Sensitive Data Masking**: Auto-masks phone, email, password fields
- **Audit Logging**: All operations logged to `~/.hologres/sql-history.jsonl`

## Notes
- schema.py是老的实现无需继续更新，新的实现迁移到 table.py 中

## Installation

Requires Python 3.11+

```bash
cd hologres-cli
pip install -e .
```

Or using `uv`:

```bash
uv venv --python 3.11
source .venv/bin/activate
uv pip install -e .
```

### Development Installation

To run tests, install with dev dependencies:

```bash
pip install -e ".[dev]"
```

## Testing

### Unit Tests

Unit tests use mocks and run without a database connection:

```bash
# Run unit tests only (fast, no database required)
pytest -m unit

# Run specific test file
pytest tests/test_masking.py
pytest tests/test_commands/test_sql.py

# Run with coverage report
pytest --cov=src/hologres_cli --cov-report=term-missing
```

### Integration Tests

Integration tests require a real Hologres database connection:

```bash
# Set test database DSN
export HOLOGRES_TEST_DSN="hologres://user:password@host:port/database"

# Run integration tests
pytest -m integration

# Run all tests (unit + integration)
pytest
```

Integration tests will be **automatically skipped** if `HOLOGRES_TEST_DSN` is not set.

### Test Markers

| Marker | Description |
|--------|-------------|
| `unit` | Unit tests with mocks (fast) |
| `integration` | Integration tests requiring database |
| `slow` | Slow running tests |

```bash
pytest -m unit           # Run unit tests only
pytest -m integration    # Run integration tests only
pytest -m "not slow"     # Skip slow tests
```

Current test coverage: **95%+** with 345 test cases (342 unit + 46 integration).

## Configuration

### DSN Format

```
hologres://[user[:password]@]host[:port]/database
```

### Configuration Methods (priority order)

1. **CLI flag**: `--dsn "hologres://user:pass@host:port/db"`
2. **Environment variable**: `export HOLOGRES_DSN="hologres://..."`
3. **Config file**: `~/.hologres/config.env`

```bash
# ~/.hologres/config.env
HOLOGRES_DSN="hologres://user:password@endpoint:port/database"
```

## Commands

### Status

```bash
# Check connection status
hologres status
```

### Instance Information

```bash
# Query instance version and max connections
hologres instance <instance_name>
```

### Warehouse (计算组)

```bash
# List all warehouses
hologres warehouse

# Query specific warehouse
hologres warehouse <warehouse_name>
```

### Table Management

```bash
# List all tables
hologres table list

# List tables in a specific schema
hologres table list --schema public
hologres table list -s myschema
```

### Schema Inspection

```bash
# List all tables
hologres schema tables

# Describe table structure
hologres schema describe <table_name>
hologres schema describe public.my_table

# Export DDL using hg_dump_script()
hologres schema dump <schema.table>
hologres schema dump public.my_table

# Get table storage size
hologres schema size <schema.table>
hologres schema size public.my_table
```

### Table Management

```bash
# List all tables
hologres table list

# List tables in a specific schema
hologres table list --schema public
hologres table list -s myschema

# Export DDL using hg_dump_script()
hologres table dump <schema.table>
hologres table dump public.my_table

# Show table structure (columns, types, nullable, defaults, primary key, comments)
hologres table show <table_name>
hologres table show public.my_table

# Get table storage size
hologres table size <schema.table>
hologres table size public.my_table
```

### Extension Management

```bash
# List installed extensions
hologres extension list

# Create (install) an extension
hologres extension create roaring_bitmap

# Create with IF NOT EXISTS
hologres extension create postgis --if-not-exists
```

### SQL Execution

```bash
# Read-only query (LIMIT required for >100 rows)
hologres sql run "SELECT * FROM users LIMIT 10"

# Disable row limit check
hologres sql run --no-limit-check "SELECT * FROM large_table"
```

> **Note:** Write operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, etc.) are blocked for safety.

### Data Import/Export

```bash
# Export table to CSV
hologres data export my_table -f output.csv

# Export with custom query
hologres data export -q "SELECT * FROM users WHERE active=true" -f users.csv

# Import CSV to table
hologres data import my_table -f input.csv

# Import with truncate
hologres data import my_table -f input.csv --truncate

# Count rows
hologres data count my_table
hologres data count my_table --where "status='active'"
```

### History

```bash
# Show recent command history
hologres history
hologres history -n 50
```

### AI Guide

```bash
# Generate AI agent guide
hologres ai-guide
```

## Output Formats

Use `--format` or `-f` to change output format:

```bash
hologres -f json schema tables    # JSON (default)
hologres -f table schema tables   # Human-readable table
hologres -f csv schema tables     # CSV
hologres -f jsonl schema tables   # JSON Lines
```

### Response Structure

**Success:**
```json
{
  "ok": true,
  "data": {
    "rows": [...],
    "count": 10
  }
}
```

**Error:**
```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message"
  }
}
```

## Safety Features

### Row Limit Protection

Queries without `LIMIT` that return more than 100 rows will fail with `LIMIT_REQUIRED` error.

```bash
# This will fail if table has >100 rows
hologres sql run "SELECT * FROM large_table"

# Add LIMIT to fix
hologres sql run "SELECT * FROM large_table LIMIT 50"

# Or disable check (use with caution)
hologres sql run --no-limit-check "SELECT * FROM large_table"
```

### Write Protection

Write operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT, REVOKE) require the `--write` flag:

```bash
# This will return WRITE_GUARD_ERROR
hologres sql run "INSERT INTO logs VALUES (1, 'test')"

# Use --write flag to allow write operations
hologres sql run --write "INSERT INTO logs VALUES (1, 'test')"

# DELETE/UPDATE without WHERE clause is blocked even with --write
hologres sql run --write "DELETE FROM users"
# Error: DANGEROUS_WRITE_BLOCKED - DELETE without WHERE clause is blocked

# DELETE/UPDATE with WHERE clause is allowed
hologres sql run --write "DELETE FROM users WHERE id = 1"
```

## Error Codes

| Code | Description |
|------|-------------|
| `CONNECTION_ERROR` | Failed to connect to database |
| `QUERY_ERROR` | SQL execution error |
| `LIMIT_REQUIRED` | Query needs LIMIT clause |
| `WRITE_GUARD_ERROR` | Write operation attempted without `--write` flag |
| `DANGEROUS_WRITE_BLOCKED` | DELETE/UPDATE without WHERE clause |

## Sensitive Data Masking

The CLI automatically masks sensitive fields based on column names:

| Pattern | Masking |
|---------|---------|
| phone, mobile, tel | `138****5678` |
| email | `j***@example.com` |
| password, secret, token | `********` |
| id_card, ssn | `110***********1234` |
| bank_card, credit_card | `***************0123` |

Disable with `--no-mask`:

```bash
hologres sql run --no-mask "SELECT * FROM users LIMIT 10"
```

## Examples

```bash
# Set DSN
export HOLOGRES_DSN="hologres://user:pass@endpoint:port/database"

# Check connection
hologres status

# List tables in table format
hologres -f table schema tables

# Query with JSON output
hologres sql run "SELECT * FROM orders WHERE status='pending' LIMIT 20"

# Check warehouse info
hologres warehouse

# View command history
hologres history
```

## License

MIT
