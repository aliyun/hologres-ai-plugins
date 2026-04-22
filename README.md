# Hologres AI Plugins

A collection of AI-agent-friendly tools and skills for [Alibaba Cloud Hologres](https://www.alibabacloud.com/product/hologres) database management. This project provides a safety-guarded CLI and a set of AI agent skills to help automate database operations, query optimization, and performance diagnosis.

## Project Structure

```
hologres-ai-plugins/
├── hologres-cli/          # Python CLI tool for Hologres database operations
└── agent-skills/          # AI agent skills for IDE / Copilot integration
    └── skills/
        ├── hologres-cli/                  # CLI usage skill
        ├── hologres-query-optimizer/      # Query execution plan analysis skill
        └── hologres-slow-query-analysis/  # Slow query diagnosis skill
```

## Components

### 1. Hologres CLI

An AI-agent-friendly command-line interface with built-in safety guardrails and structured JSON output.

**Key Features:**

- **Structured Output** — All commands return JSON by default for easy parsing by AI agents
- **Safety Guardrails** — Row limit protection, write operation blocking, dangerous SQL detection
- **Dynamic Table Management** — Full lifecycle management for Dynamic Tables (V3.1+ syntax)
- **Sensitive Data Masking** — Auto-masks phone, email, password, ID card, and bank card fields
- **Multiple Output Formats** — JSON, table, CSV, JSON Lines (JSONL)
- **Audit Logging** — All operations logged to `~/.hologres/sql-history.jsonl`

**Available Commands:**

| Command | Description |
|---------|-------------|
| `hologres status` | Check connection status |
| `hologres instance <name>` | Query instance version and max connections |
| `hologres warehouse [name]` | List or query warehouses |
| `hologres schema tables` | List all tables |
| `hologres schema describe <table>` | Show table structure |
| `hologres schema dump <schema.table>` | Export DDL |
| `hologres schema size <schema.table>` | Get table storage size |
| `hologres sql "<query>"` | Execute read-only SQL |
| `hologres data export <table> -f out.csv` | Export table to CSV |
| `hologres data import <table> -f in.csv` | Import CSV to table |
| `hologres data count <table>` | Count rows |
| `hologres dt create` | Create a Dynamic Table (V3.1+ syntax) |
| `hologres dt list` | List all Dynamic Tables |
| `hologres dt show <table>` | Show Dynamic Table properties |
| `hologres dt ddl <table>` | Show Dynamic Table DDL |
| `hologres dt lineage <table>` | Show Dynamic Table dependency lineage |
| `hologres dt storage <table>` | Show Dynamic Table storage details |
| `hologres dt state-size <table>` | Show state table size (incremental) |
| `hologres dt refresh <table>` | Trigger manual refresh |
| `hologres dt alter <table>` | Alter Dynamic Table properties |
| `hologres dt drop <table>` | Drop a Dynamic Table (safe by default) |
| `hologres dt convert [table]` | Convert from V3.0 to V3.1 syntax |
| `hologres history` | Show recent command history |
| `hologres ai-guide` | Generate AI agent guide |

**Quick Start:**

```bash
# Requires Python 3.11+
cd hologres-cli
pip install -e .

# Set connection DSN
export HOLOGRES_DSN="hologres://user:password@endpoint:port/database"

# Check connection
hologres status

# List tables
hologres -f table schema tables

# Query data
hologres sql "SELECT * FROM orders LIMIT 10"

# Create a Dynamic Table
hologres dt create -t my_dt --freshness "10 minutes" \
  -q "SELECT col1, SUM(col2) FROM src GROUP BY col1"

# List Dynamic Tables
hologres dt list

# View lineage
hologres dt lineage public.my_dt
```

For full documentation, see [hologres-cli/README.md](hologres-cli/README.md).

### 2. AI Agent Skills

Pre-built skills that can be loaded by AI coding assistants (IDE copilots) to provide domain-specific knowledge about Hologres.

#### hologres-cli

Teaches the AI agent how to use the Hologres CLI tool effectively, including command usage, safety features, output format handling, and best practices.

#### hologres-query-optimizer

Enables the AI agent to analyze and optimize Hologres SQL query execution plans:

- Interpret `EXPLAIN` and `EXPLAIN ANALYZE` output
- Understand query operators (Seq Scan, Index Scan, Hash Join, etc.)
- Identify performance bottlenecks and data skew
- Recommend optimization strategies (indexes, distribution keys, GUC parameters)

#### hologres-slow-query-analysis

Equips the AI agent to diagnose slow and failed queries using the `hologres.hg_query_log` system table:

- Find resource-heavy queries (CPU, memory, I/O)
- Identify failed queries and error patterns
- Analyze query phase bottlenecks (optimization / startup / execution)
- Compare performance across time periods

## Requirements

- Python 3.11+
- Access to an Alibaba Cloud Hologres instance

## Installation

```bash
git clone <repo-url>
cd hologres-ai-plugins/hologres-cli
pip install -e .

# For development (includes test dependencies)
pip install -e ".[dev]"
```

## Configuration

The CLI resolves the database connection DSN in the following priority order:

1. **CLI flag**: `--dsn "hologres://user:pass@host:port/db"`
2. **Environment variable**: `export HOLOGRES_DSN="hologres://..."`
3. **Config file**: `~/.hologres/config.env`

## Testing

```bash
cd hologres-cli

# Unit tests (no database required)
pytest -m unit

# Integration tests (requires database)
export HOLOGRES_TEST_DSN="hologres://user:password@host:port/database"
pytest -m integration

# All tests with coverage
pytest --cov=src/hologres_cli --cov-report=term-missing
```

Current test coverage: **95%+**.

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Alibaba Cloud
