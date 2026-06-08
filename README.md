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
    │   ├── hologres-slow-query-analysis/  # Slow query diagnosis skill
    │   ├── hologres-schema-generator/     # DDL schema design expert skill
    │   ├── hologres-privileges/           # Privilege management skill
    │   ├── hologres-uv-compute/           # UV/PV deduplication skill
    │   ├── hologres-bsi-profile-analysis/ # BSI profile analysis skill
    │   ├── hologres-ad-campaign/          # Ad creative generation & campaign analysis skill
    │   ├── hologres-instance-health-analyse/ # Instance health diagnosis & inspection skill
    │   ├── hologres-diagnosis-cpu/        # CPU anomaly diagnosis skill
    │   ├── hologres-diagnosis-memory/     # Memory anomaly diagnosis skill (OOM / leak / skew)
    │   ├── hologres-daily-report/         # Daily ops diagnosis report skill
    │   └── hologres-knowledge-base/       # Search & RAG knowledge base skill (HGraph + fulltext)
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
- **Dual Connection Mode** — JDBC (psycopg) with automatic OpenAPI `ExecuteStatement` fallback when JDBC is unavailable
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
| `hologres table create --name TABLE --columns COLS [options] [--dry-run]` | Create a table (supports logical partition V3.1+) |
| `hologres table dump <schema.table>` | Export DDL for a table |
| `hologres table show <table>` | Show table structure |
| `hologres table size <schema.table>` | Get table storage size |
| `hologres table properties <table>` | Show table properties (orientation, distribution_key, TTL, etc.) |
| `hologres table drop <table> [--if-exists] [--cascade] --confirm` | Drop a table (dry-run by default) |
| `hologres table truncate <table> --confirm` | Truncate (empty) a table (dry-run by default) |
| `hologres table alter TABLE [options] [--dry-run]` | Alter table properties (add column, rename, TTL, etc.; logical partition tables support SET syntax for partition properties) |
| `hologres partition list <table>` | List partitions of a logical partition table |
| `hologres partition alter --table <table> --partition <value> --set <key=value> [--dry-run]` | Alter partition properties of a logical partition table (keep_alive/storage_mode/generate_binlog) |
| `hologres view list [--schema S]` | List all views |
| `hologres view show <view>` | Show view definition and structure |
| `hologres sql run "<query>"` | Execute read-only SQL |
| `hologres sql explain "<query>"` | Show query execution plan |
| `hologres extension list` | List installed extensions |
| `hologres extension create <name>` | Create (install) an extension |
| `hologres guc show <param>` | Show GUC parameter value |
| `hologres guc set <param> <value>` | Set GUC parameter at database level |
| `hologres guc reset <param>` | Reset GUC parameter to default value |
| `hologres guc list [--filter keyword]` | List common GUC parameters and current values |
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
| `hologres ai gen "<prompt>" [--model]` | Generate text using AI function |
| `hologres ai image-gen "<prompt>" -o volume://vol/path [options]` | Generate images to OSS volume using AI function |
| `hologres ai t2v "<prompt>" -o volume://vol/path [options]` | Generate video from text (text-to-video) |
| `hologres ai i2v "<prompt>" --img-url <url> -o volume://vol/path [options]` | Generate video from first-frame image (image-to-video) |
| `hologres ai r2v "<prompt>" --reference-url <url> -o volume://vol/path [options]` | Generate video from reference images (reference-to-video) |
| `hologres ai video-edit "<prompt>" --video <url> -o volume://vol/path [options]` | Edit video with text instructions |
| `hologres volume create <name> --endpoint <ep> --root <root> --rolearn <arn> --access-key <ak> --access-secret <sk>` | Create a local volume configuration (also creates OSS directory placeholder) |
| `hologres volume list` | List all volumes in current profile |
| `hologres volume delete <name>` | Delete a volume configuration |
| `hologres volume list-files --volume <name> [--prefix P] [--max-count N] [--net internet\|intranet]` | List files in volume |
| `hologres volume delete-file --volume <name> --file <path> [--confirm] [--net internet\|intranet]` | Delete file from volume |
| `hologres volume download-file --volume <name> --file <path> -d <dir> [--net internet\|intranet]` | Download file from volume |
| `hologres volume upload-file --volume <name> --local-file <path> --target-file <path> [--net internet\|intranet]` | Upload file to volume |
| `hologres volume view volume://<name>/path/file [--net internet\|intranet]` | Download file to temp dir and open with system viewer |
| `hologres model list [--task T] [--model-type T] [--search S]` | List registered external AI models |
| `hologres model delete <model_name> [--confirm]` | Delete a registered external AI model (dry-run by default) |
| `hologres instance-manage list` | List all Hologres instances |
| `hologres instance-manage get` | Get instance details |
| `hologres instance-manage stop / resume / restart` | Instance lifecycle operations |
| `hologres instance-manage enable-execute-statement` | Enable ExecuteStatement API for the instance |
| `hologres instance-manage disable-execute-statement` | Disable ExecuteStatement API |
| `hologres instance-manage get-execute-statement-enabled` | Check if ExecuteStatement is enabled |

**Quick Start:**

```bash
# Install from PyPI
pip install hologres-cli

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

#### hologres-schema-generator

Hologres DDL schema design and table creation expert:

- Storage format selection (column / row / row-column)
- Index configuration (distribution_key, clustering_key, bitmap_columns, event_time_column)
- Partition table design (physical / logical partitions)
- Data type recommendations and schema optimization

#### hologres-privileges

Hologres privilege management using PostgreSQL standard authorization model (expert permission model):

- User creation and role management
- Fine-grained GRANT/REVOKE at Schema / table / column / view level
- Default privileges configuration (ALTER DEFAULT PRIVILEGES)
- Permission issue diagnosis and troubleshooting

#### hologres-uv-compute

Real-time UV/PV deduplication pipelines using Dynamic Tables and RoaringBitmap:

- RoaringBitmap bitmap deduplication (sub-second for billions of users)
- Dynamic Table incremental refresh pipelines
- Flexible time-range UV aggregation (`RB_OR_AGG` cross-day merge)
- UID dictionary encoding (text-to-int)

#### hologres-bsi-profile-analysis

BSI (Bit-Sliced Index) based user profile analysis:

- Attribute tags + behavior tags joint crowd targeting
- GMV analysis, tag distribution statistics, Top K queries
- Bucketed parallel computation
- BSI function usage (bsi_build, bsi_sum, bsi_filter, bsi_stat, bsi_topk)

#### hologres-ad-campaign

AI-powered ad creative generation and campaign analysis using Hologres AI Function:

- End-to-end SQL pipeline: material management → image generation → storyboard → video synthesis
- Virtual delivery simulation across channels (WeChat, Douyin, Xiaohongshu, Bilibili)
- Real-time ROI analysis via Dynamic Tables
- AI-driven strategy recommendations (budget allocation, stop-loss suggestions)

#### hologres-instance-health-analyse

Hologres instance health diagnosis and inspection, executing all SQL through `hologres-cli`:

- Warehouse resource inspection (CPU, memory, connections via `pg_stat_activity`)
- FAILED query classification and error pattern analysis (`hg_query_log`)
- Slow query analysis by CPU/memory consumption (digest-based aggregation)
- Structured diagnostic report with actionable optimization recommendations

#### hologres-diagnosis-cpu

Hologres CPU anomaly diagnosis skill — when CPU is saturated / sustained-high / Worker imbalance / background Compaction interference is suspected:

- CPU state classification (sustained saturation / sustained high / safe & stable)
- 4-quadrant root-cause attribution (macro qualitative / Worker-Shard distribution / query attribution / background task interference)
- Structured Markdown diagnostic report and governance action list
- Takes `instance_id` + time window as input, all SQL executed through `hologres-cli`

#### hologres-diagnosis-memory

Hologres instance memory anomaly diagnosis skill — for OOM events, sustained-high memory,
worker memory imbalance, leak suspicions, and memory attribution analysis:

- Takes `instance_id` + time window as input
- Auto-classifies memory waveform (global high / local skew / no-recovery sustained)
- Aligns with business metrics, then splits Query vs System/Cache memory
- Drills down along 4 attribution lines: Query / skew / Write & background / System & metadata
- Cloud monitor metrics via `hologres metric query`; metadata via `hologres sql run`;
  OOM/Jeprof/Coredump internals via `holo oncall common`
- Outputs structured Markdown diagnostic report + governance action checklist
- Root-cause only — Query SQL rewrite suggestions are out of scope (reports query IDs + resource snapshots)

#### hologres-daily-report

Hologres ops daily diagnostic report — not a metric-dashboard data dump, but an opinionated
**"diagnostic conclusion + root-cause explanation + action recommendation"** report generated
by the AI assistant.

- Inputs: `instance_id` + `report_date` (default: yesterday) + `region`
- Six dimensions: instance health, availability, compute resources, SQL performance, cost governance, capacity forecast
- All metrics queried through `hologres-cli`; report rendered as structured Markdown

#### hologres-knowledge-base

Build enterprise search & RAG knowledge bases on Hologres using the native building blocks
(no external vector DB needed):

- **Full-text inverted index** (Tantivy + BM25) with multiple Chinese/English tokenizers (jieba / IK / ngram / pinyin / …)
- **HGraph vector index** for high-performance approximate nearest-neighbor search (rabitq quantization, configurable memory/disk hybrid storage)
- **Hybrid search** — vector + full-text + scalar filters in a single SQL (RRF fusion)
- **holo-search-sdk** Python client for ergonomic ingest & search
- RAG patterns: in-Hologres embeddings via `ai_gen()`, or client-side embeddings via SDK
- Covers full lifecycle: create table with `WITH (...)` syntax → ingest chunks → vector / BM25 / hybrid retrieval → LLM Q&A

## Requirements

- Python 3.11+
- Access to an Alibaba Cloud Hologres instance

## Installation

### Hologres CLI

```bash
# Install from PyPI
pip install hologres-cli

# Or install a specific version
pip install hologres-cli==0.1.0

# Initial configuration
hologres config
```

### Development (from source)

```bash
git clone https://github.com/aliyun/hologres-ai-plugins.git
cd hologres-ai-plugins/hologres-cli
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
