# Hologres AI Plugins

A collection of AI-agent-friendly tools and skills for [Alibaba Cloud Hologres](https://www.alibabacloud.com/product/hologres) database management. This project provides a safety-guarded CLI and a set of AI agent skills to help automate database operations, query optimization, and performance diagnosis.

## Project Structure

```
hologres-ai-plugins/
├── hologres-cli/          # Python CLI tool for Hologres database operations
└── agent-skills/          # AI agent skills for IDE / Copilot integration
    ├── src/
    │   └── holo_plugin_installer/     # Interactive skills installer
    ├── skills/
    │   ├── hologres-cli/                  # CLI usage skill
    │   ├── hologres-query-optimizer/      # Query execution plan analysis skill
    │   └── hologres-slow-query-analysis/  # Slow query diagnosis skill
    ├── pyproject.toml
    └── upload_to_pypi.py
```

## Components

### 1. Hologres CLI

An AI-agent-friendly command-line interface with built-in safety guardrails and structured JSON output.

**Key Features:**

- **Profile-Based Configuration** — Multi-profile management via `~/.hologres/config.json` with interactive wizard
- **Structured Output** — All commands return JSON by default for easy parsing by AI agents
- **Safety Guardrails** — Row limit protection, write operation blocking, dangerous SQL detection
- **Dynamic Table Management** — Full lifecycle management for Dynamic Tables (V3.1+ syntax)
- **Sensitive Data Masking** — Auto-masks phone, email, password, ID card, and bank card fields
- **Multiple Output Formats** — JSON, table, CSV, JSON Lines (JSONL)
- **Audit Logging** — All operations logged to `~/.hologres/sql-history.jsonl`

**Available Commands:**

| Command | Description |
|---------|-------------|
| `hologres config` | Interactive configuration wizard |
| `hologres config list` | List all profiles |
| `hologres config show` | Show current profile details |
| `hologres config switch <name>` | Switch active profile |
| `hologres config set <key> <value>` | Set a configuration value |
| `hologres status` | Check connection status |
| `hologres instance <name>` | Query instance version and max connections |
| `hologres warehouse [name]` | List or query warehouses |
| `hologres schema tables` | List all tables |
| `hologres schema describe <table>` | Show table structure |
| `hologres schema dump <schema.table>` | Export DDL |
| `hologres schema size <schema.table>` | Get table storage size |
| `hologres table list [--schema S]` | List all tables |
| `hologres table dump <schema.table>` | Export DDL for a table |
| `hologres table show <table>` | Show table structure |
| `hologres table size <schema.table>` | Get table storage size |
| `hologres table properties <table>` | Show table properties (orientation, distribution_key, TTL, etc.) |
| `hologres table drop <table> [--if-exists] [--cascade] --confirm` | Drop a table (dry-run by default) |
| `hologres table truncate <table> --confirm` | Truncate (empty) a table (dry-run by default) |
| `hologres view list [--schema S]` | List all views |
| `hologres view show <view>` | Show view definition and structure |
| `hologres sql run "<query>"` | Execute read-only SQL |
| `hologres sql explain "<query>"` | Show query execution plan |
| `hologres extension list` | List installed extensions |
| `hologres extension create <name>` | Create (install) an extension |
| `hologres guc show <param>` | Show GUC parameter value |
| `hologres guc set <param> <value>` | Set GUC parameter at database level |
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

# Run interactive configuration wizard
hologres config

# Check connection
hologres status

# List tables
hologres -f table schema tables

# Query data
hologres sql "SELECT * FROM orders LIMIT 10"

# Use a specific profile
hologres --profile prod status

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

**Quick Install:**

```bash
# Install skills to your AI tool (Claude Code, Cursor, Codex, etc.)
uvx hologres-agent-skills
```

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

### Install Agent Skills

```bash
# Option 1: One-command install (recommended)
uvx hologres-agent-skills

# Option 2: Install from source
cd hologres-ai-plugins/agent-skills
uv sync
uv run hologres-agent-skills
```

## Configuration

The CLI uses **profile-based** configuration stored in `~/.hologres/config.json`:

```bash
# Interactive setup wizard
hologres config

# Or set values directly
hologres config set region_id cn-hangzhou
hologres config set instance_id hgprecn-cn-xxx
hologres config set database mydb
```

Connection resolution priority:
1. **CLI flag**: `hologres --profile <name> status`
2. **Current profile**: The active profile in `config.json`
3. **Error**: Prompted to run `hologres config`

## Testing

```bash
cd hologres-cli

# Unit tests (no database required)
pytest tests/ --ignore=tests/integration

# Integration tests (requires configured profile)
pytest tests/integration/

# All tests with coverage
pytest --cov=src/hologres_cli --cov-report=term-missing
```

## License

[Apache License 2.0](LICENSE) — Copyright 2026 Alibaba Cloud
