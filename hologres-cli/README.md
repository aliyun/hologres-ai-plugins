# Hologres CLI

AI-agent-friendly command-line interface for Hologres database with safety guardrails and structured JSON output.

## Features

- **Structured Output**: All commands return JSON by default for easy parsing
- **Safety Guardrails**: Row limits, write protection, dangerous operation blocking
- **Multiple Formats**: JSON, table, CSV, JSONL output formats
- **Dynamic Table Management**: Full lifecycle management for Dynamic Tables (V3.1+)
- **Sensitive Data Masking**: Auto-masks phone, email, password fields
- **Audit Logging**: All operations logged to `~/.hologres/sql-history.jsonl`

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

```bash
pip install -e ".[dev]"
```

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
hologres status
```

### Instance Information

```bash
hologres instance <instance_name>
```

### Warehouse (计算组)

```bash
hologres warehouse                    # List all warehouses
hologres warehouse <warehouse_name>   # Query specific warehouse
```

### Schema Inspection

```bash
hologres schema tables                      # List all tables
hologres schema describe <table_name>       # Describe table structure
hologres schema dump <schema.table>         # Export DDL
hologres schema size <schema.table>         # Get table storage size
```

### SQL Execution

```bash
hologres sql "SELECT * FROM users LIMIT 10"                 # Read-only query
hologres sql --no-limit-check "SELECT * FROM large_table"   # Disable row limit
```

> **Note:** Write operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, etc.) are blocked for safety.

### Data Import/Export

```bash
hologres data export my_table -f output.csv                           # Export to CSV
hologres data export -q "SELECT * FROM users WHERE active" -f out.csv # Export with query
hologres data import my_table -f input.csv                            # Import CSV
hologres data import my_table -f input.csv --truncate                 # Import with truncate
hologres data count my_table                                          # Count rows
hologres data count my_table --where "status='active'"                # Count with filter
```

### Dynamic Table (V3.1+)

Full lifecycle management for Hologres Dynamic Tables using the V3.1+ new syntax.

#### Create

```bash
# Minimal creation
hologres dt create -t my_dt --freshness "10 minutes" \
  -q "SELECT col1, SUM(col2) FROM src GROUP BY col1"

# With partitioning and serverless computing
hologres dt create -t ads_report --freshness "5 minutes" --refresh-mode auto \
  --logical-partition-key ds --partition-active-time "2 days" \
  --partition-time-format YYYY-MM-DD \
  --computing-resource serverless --serverless-cores 32 \
  -q "SELECT repo_name, COUNT(*) AS events, ds FROM src GROUP BY repo_name, ds"

# Dry-run to preview SQL
hologres dt create -t my_dt --freshness "10 minutes" -q "SELECT 1" --dry-run
```

Key options: `--refresh-mode` (auto/full/incremental), `--auto-refresh/--no-auto-refresh`, `--cdc-format` (stream/binlog), `--computing-resource` (local/serverless/warehouse), `--orientation`, `--distribution-key`, `--clustering-key`, `--ttl`, etc. Use `hologres dt create --help` for full details.

#### List & Show

```bash
hologres dt list                    # List all Dynamic Tables
hologres dt show public.my_dt       # Show properties of a Dynamic Table
hologres dt list -f table           # List in table format
```

#### DDL (Table Structure)

```bash
hologres dt ddl public.my_dt        # Show CREATE statement via hg_dump_script()
```

#### Lineage (Blood Lineage)

```bash
hologres dt lineage public.my_dt    # View lineage for a single table
hologres dt lineage --all           # View lineage for all Dynamic Tables
hologres dt lineage my_dt -f table  # Table format output
```

base_table_type mapping: `r` = ordinary table, `v` = view, `m` = materialized view, `f` = foreign table, `d` = Dynamic Table.

#### Storage & State

```bash
hologres dt storage public.my_dt      # View storage size breakdown
hologres dt state-size public.my_dt   # View state table size (incremental refresh)
```

#### Refresh

```bash
hologres dt refresh my_dt                                                    # Trigger refresh
hologres dt refresh my_dt --overwrite --partition "ds = '2025-04-01'" --mode full  # Overwrite partition
hologres dt refresh my_dt --dry-run                                          # Preview SQL
```

#### Alter

```bash
hologres dt alter my_dt --freshness "30 minutes"
hologres dt alter my_dt --no-auto-refresh
hologres dt alter my_dt --refresh-mode full --computing-resource serverless
hologres dt alter my_dt --refresh-guc timezone=GMT-8:00 --dry-run
```

#### Drop

```bash
hologres dt drop my_dt               # Dry-run by default (safety)
hologres dt drop my_dt --confirm     # Actually drop
hologres dt drop my_dt --if-exists --confirm
```

#### Convert (V3.0 → V3.1)

```bash
hologres dt convert my_old_dt          # Convert single table
hologres dt convert --all              # Convert all V3.0 tables
hologres dt convert my_old_dt --dry-run
```

### History & AI Guide

```bash
hologres history          # Show recent command history
hologres history -n 50    # Show last 50 entries
hologres ai-guide         # Generate AI agent guide
```

## Output Formats

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
hologres sql "SELECT * FROM large_table LIMIT 50"           # OK
hologres sql --no-limit-check "SELECT * FROM large_table"   # Bypass limit check
```

### Write Protection

All write operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT, REVOKE) are blocked via `hologres sql`.

### Drop Safety

`hologres dt drop` defaults to dry-run mode. Use `--confirm` to actually execute.

## Error Codes

| Code | Description |
|------|-------------|
| `CONNECTION_ERROR` | Failed to connect to database |
| `QUERY_ERROR` | SQL execution error |
| `LIMIT_REQUIRED` | Query needs LIMIT clause |
| `WRITE_BLOCKED` | Write operation not allowed |
| `NOT_FOUND` | Table or resource not found |
| `INVALID_ARGS` | Invalid or missing arguments |
| `NO_CHANGES` | No properties specified to alter |

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
hologres sql --no-mask "SELECT * FROM users LIMIT 10"
```

## Testing

```bash
pytest -m unit                                          # Unit tests only (fast)
pytest -m integration                                   # Integration tests (needs DB)
pytest tests/test_commands/test_dt.py                   # DT command tests
pytest --cov=src/hologres_cli --cov-report=term-missing # With coverage
```

Integration tests require `HOLOGRES_TEST_DSN` environment variable and are auto-skipped otherwise.

## License

MIT
