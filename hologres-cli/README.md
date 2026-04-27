# Hologres CLI

AI-agent-friendly command-line interface for Hologres database with safety guardrails and structured JSON output.

## Features

- **Profile-Based Configuration**: Multi-profile management via `~/.hologres/config.json`, interactive wizard setup
- **Structured Output**: All commands return JSON by default for easy parsing
- **Safety Guardrails**: Row limits, write protection, dangerous operation blocking
- **Multiple Formats**: JSON, table, CSV, JSONL output formats
- **Dynamic Table Management**: Full lifecycle management for Dynamic Tables (V3.1+)
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

```bash
pip install -e ".[dev]"
```

## Configuration

The CLI uses a **profile-based** configuration stored in `~/.hologres/config.json`. Each profile contains connection parameters including region, instance, auth credentials, database, and warehouse.

### Quick Setup

Run the interactive configuration wizard:

```bash
hologres config
```

The wizard will prompt for:
- **Region** (e.g., `cn-hangzhou`, `cn-shanghai`)
- **Instance ID** (e.g., `hgprecn-cn-xxx`)
- **Network type**: `internet` / `intranet` / `vpc`
- **Auth mode**: `basic` (username/password) or `ram` (AccessKey)
- **Database name**
- **Warehouse** (computing group)
- **Endpoint** (optional, auto-constructed from instance_id + region_id + nettype)
- **Port** (default: `80`)

### Endpoint Auto-Construction

If no custom endpoint is provided, the host is auto-constructed based on `nettype`:

| nettype | Host pattern |
|---------|-------------|
| internet | `{instance_id}-{region_id}.hologres.aliyuncs.com` |
| intranet | `{instance_id}-{region_id}-internal.hologres.aliyuncs.com` |
| vpc | `{instance_id}-{region_id}-vpc-st.hologres.aliyuncs.com` |

### Profile Management

```bash
hologres config                       # Interactive wizard (create/edit profile)
hologres config list                   # List all profiles
hologres config show                   # Show current profile details
hologres config current                # Show current profile name
hologres config switch <name>          # Switch active profile
hologres config set <key> <value>      # Set a configuration value
hologres config get <key>              # Get a configuration value
hologres config delete <name> --confirm  # Delete a profile
```

### Profile Resolution Priority

1. **CLI flag**: `hologres --profile <name> status`
2. **Current profile**: The active profile set via `config switch`
3. **Error**: Prompted to run `hologres config` if no profile found

### Config File Structure

```json
{
  "current": "default",
  "profiles": [
    {
      "name": "default",
      "region_id": "cn-hangzhou",
      "instance_id": "hgprecn-cn-xxx",
      "nettype": "internet",
      "auth_mode": "basic",
      "username": "BASIC$myuser",
      "password": "mypassword",
      "database": "mydb",
      "warehouse": "default_warehouse",
      "endpoint": "",
      "port": 80,
      "output_format": "json",
      "language": "zh"
    }
  ]
}
```

## Commands

### Status

```bash
hologres status                        # Check connection and version
hologres --profile prod status         # Check with specific profile
```

### Instance Information

```bash
hologres instance <instance_name>
```

### Warehouse (Computing Group)

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

### Table Management

```bash
# List all tables
hologres table list

# List tables in a specific schema
hologres table list --schema public
hologres table list -s myschema

# Create a table (uses compatible syntax with CALL set_table_property)
hologres table create --name public.orders \
  --columns "order_id BIGINT NOT NULL, user_id INT, amount DECIMAL(10,2), created_at TIMESTAMPTZ" \
  --primary-key order_id --orientation column \
  --distribution-key user_id --clustering-key "created_at:asc" \
  --ttl 7776000 --dry-run

# Create a physical partition table
hologres table create --name public.events \
  --columns "event_id BIGINT NOT NULL, ds TEXT NOT NULL, payload JSONB" \
  --primary-key "event_id,ds" --partition-by ds \
  --orientation column --dry-run

# Create a logical partition table (V3.1+, uses WITH syntax)
hologres table create --name public.logs \
  --columns "a TEXT, b INT, ds DATE NOT NULL" \
  --primary-key "b,ds" --partition-by ds \
  --partition-mode logical --orientation column \
  --distribution-key b \
  --partition-expiration-time "30 day" \
  --partition-keep-hot-window "15 day" \
  --partition-require-filter true \
  --binlog replica --binlog-ttl 86400 --dry-run

# Create a logical partition table with two partition keys
hologres table create --name public.events_2pk \
  --columns "a TEXT, b INT, yy TEXT NOT NULL, mm TEXT NOT NULL" \
  --partition-by "yy, mm" --partition-mode logical \
  --orientation column --partition-require-filter true --dry-run

# Export DDL using hg_dump_script()
hologres table dump <schema.table>
hologres table dump public.my_table

# Show table structure (columns, types, nullable, defaults, primary key, comments)
hologres table show <table_name>
hologres table show public.my_table

# Get table storage size
hologres table size <schema.table>
hologres table size public.my_table

# Show table properties (orientation, distribution_key, clustering_key, TTL, etc.)
hologres table properties <table_name>
hologres table properties public.my_table

# Drop a table (dry-run by default, use --confirm to execute)
hologres table drop my_table              # dry-run, shows SQL
hologres table drop my_table --confirm    # actually drops
hologres table drop my_table --if-exists --confirm
hologres table drop my_table --cascade --confirm

# Truncate (empty) a table (dry-run by default, use --confirm to execute)
hologres table truncate my_table              # dry-run, shows SQL
hologres table truncate my_table --confirm    # actually truncates
```

### View Management

```bash
# List all views
hologres view list

# List views in a specific schema
hologres view list --schema public
hologres view list -s myschema

# Show view definition and structure
hologres view show <view_name>
hologres view show analytics.daily_stats
```

### Partition Management

```bash
# List partitions of a logical partition table
hologres partition list my_table
hologres partition list public.logs

# With table format output
hologres partition list public.logs -f table
```

> **Note:** Currently only logical partition tables are supported. Non-logical partition tables will return a `NOT_LOGICAL_PARTITION` error.

### Extension Management

```bash
# List installed extensions
hologres extension list

# Create (install) an extension
hologres extension create roaring_bitmap

# Create with IF NOT EXISTS
hologres extension create postgis --if-not-exists
```

### GUC Parameter Management

```bash
# Show current value of a GUC parameter
hologres guc show optimizer_join_order

# Set a GUC parameter at database level (persistent)
hologres guc set optimizer_join_order query
hologres guc set statement_timeout '5min'
```

> **Note:** `guc set` sets parameters at the database level using `ALTER DATABASE`, which persists across sessions and applies to all new connections.

### SQL Execution

```bash
# Read-only query (LIMIT required for >100 rows)
hologres sql run "SELECT * FROM users LIMIT 10"

# Include column schema in output
hologres sql run --with-schema "SELECT * FROM users LIMIT 10"

# Disable row limit check
hologres sql run --no-limit-check "SELECT * FROM large_table"
```

> **Note:** Write operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, etc.) are blocked for safety.

### SQL Explain

```bash
# Show execution plan
hologres sql explain "SELECT * FROM orders WHERE status = 'active'"
```

### Data Import/Export

```bash
# Export table to CSV
hologres data export my_table -f output.csv

# Export with custom query
hologres data export -q "SELECT * FROM users WHERE active=true" -f users.csv

# Export with custom delimiter
hologres data export my_table -f output.csv --delimiter '|'

# Import CSV to table
hologres data import my_table -f input.csv

# Import with truncate
hologres data import my_table -f input.csv --truncate

# Import with custom delimiter
hologres data import my_table -f input.csv --delimiter '|'

# Count rows
hologres data count my_table
hologres data count my_table --where "status='active'"
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

### Drop Safety

`hologres table drop` and `hologres table truncate` default to dry-run mode. Use `--confirm` to actually execute.

`hologres dt drop` also defaults to dry-run mode. Use `--confirm` to actually execute.

## Error Codes

| Code | Description |
|------|-------------|
| `CONNECTION_ERROR` | Failed to connect to database |
| `QUERY_ERROR` | SQL execution error |
| `LIMIT_REQUIRED` | Query needs LIMIT clause |
| `WRITE_GUARD_ERROR` | Write operation attempted without `--write` flag |
| `DANGEROUS_WRITE_BLOCKED` | DELETE/UPDATE without WHERE clause |
| `WRITE_BLOCKED` | Write operation not allowed |
| `NOT_FOUND` | Table or resource not found |
| `INVALID_INPUT` | Invalid identifier or input validation failed |
| `INVALID_ARGS` | Invalid or missing arguments |
| `NO_CHANGES` | No properties specified to alter |
| `EXPORT_ERROR` | Data export failed |
| `IMPORT_ERROR` | Data import failed |
| `VIEW_NOT_FOUND` | View not found |
| `NOT_LOGICAL_PARTITION` | Table is not a logical partition table |

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

## Testing

```bash
# Unit tests (no database required)
pytest -m unit

# Run specific test files
pytest tests/test_commands/test_dt.py                # DT command tests
pytest tests/test_commands/test_config.py            # Config command tests
pytest tests/test_config_store.py                    # Config store unit tests

# With coverage
pytest --cov=src/hologres_cli --cov-report=term-missing

# Integration tests (requires configured profile)
export HOLOGRES_DSN="hologres://user:pass@endpoint:port/database"
pytest -m integration
```

Integration tests (in `tests/integration/`) require a configured profile and are skipped by default.

## License

MIT
