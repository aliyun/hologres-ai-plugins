# Hologres Agent Skills

An interactive installer that distributes Hologres AI agent skills to various AI coding tools.

## Included Skills

| Skill | Depends on | Description |
|-------|------------|-------------|
| `hologres-cli` | — | Teaches AI agents how to use the Hologres CLI tool — command usage, safety features, output formats, and best practices |
| `hologres-query-optimizer` | `hologres-cli` | Enables AI agents to analyze and optimize Hologres SQL query execution plans |
| `hologres-slow-query-analysis` | `hologres-cli` | Equips AI agents to diagnose slow/failed queries using `hologres.hg_query_log` |
| `hologres-schema-generator` | `hologres-cli` | Hologres DDL schema design and table creation expert — storage format selection, index configuration, partition design |
| `hologres-privileges` | `hologres-cli` | Hologres privilege management using PostgreSQL standard GRANT/REVOKE authorization model |
| `hologres-uv-compute` | `hologres-cli` | Real-time UV/PV computation pipelines using Dynamic Tables and RoaringBitmap |
| `hologres-bsi-profile-analysis` | `hologres-cli` | BSI (Bit-Sliced Index) based user profile analysis — tag computation, crowd targeting, GMV analysis |
| `hologres-ad-campaign` | `hologres-cli` | AI-powered ad creative generation and campaign analysis — video synthesis, virtual delivery simulation, real-time ROI via Dynamic Tables |
| `hologres-instance-health-analyse` | `hologres-cli` | Instance health diagnosis — Warehouse resource inspection, FAILED query classification, CPU/memory slow query analysis, structured diagnostic reports |
| `hologres-diagnosis-cpu` | `hologres-cli` | CPU anomaly diagnosis — 4-quadrant root-cause analysis (macro qualitative / Worker-Shard distribution / query attribution / background task interference), structured diagnostic report and governance action list |
| `hologres-diagnosis-memory` | `hologres-cli` | Memory anomaly diagnosis — OOM / sustained-high / Worker imbalance / leak root-cause attribution along 4 lines (Query / skew / Write & background / System & metadata), with structured Markdown diagnostic report and action checklist |
| `hologres-daily-report` | `hologres-cli` | Daily ops diagnosis report — opinionated "diagnostic conclusion + root cause + action recommendation" report across 6 dimensions (health, availability, compute, SQL perf, cost governance, capacity forecast) |
| `hologres-knowledge-base` | `hologres-cli` | Search & RAG knowledge base — full-text inverted index (Tantivy + BM25), HGraph vector index, hybrid retrieval (vector + BM25 + scalar) in one SQL, optional embedding via Hologres `ai_gen()` or `holo-search-sdk` |

> **Note:** All skills except `hologres-cli` depend on it as the foundational skill. SQL execution, GUC management, and data operations are performed through CLI commands. Install `hologres-cli` skill first.

## Supported AI Tools

Claude Code, OpenClaw, Cursor, Codex, OpenCode, GitHub Copilot, Qoder, Trae

## Quick Start

### Install via uvx (Recommended)

```bash
# Run directly without installation
uvx hologres-agent-skills
```

### Install via pip

```bash
pip install hologres-agent-skills
hologres-agent-skills
```

### Install from source (Development)

```bash
cd agent-skills
uv sync
uv run hologres-agent-skills
```

## Usage

The installer guides you through an interactive workflow:

1. **Select tool** — Choose which AI coding tool to install skills for
2. **Confirm path** — Verify the installation directory
3. **Select skills** — Pick one or more skills to install
4. **Done** — Skills are copied to the tool's skills directory

```
$ hologres-agent-skills

🚀 Hologres Agent Skills Installer
==================================================

📋 Select tool to install to:
? Select one tool: Claude Code

📁 Project root: /path/to/your/project
   (Skills will be installed under .claude/skills)
? Install skills to this directory? Yes

📦 Select skills to install:
? Select skills:
  ● hologres-cli
  ● hologres-query-optimizer
  ● hologres-slow-query-analysis
  ● hologres-schema-generator
  ● hologres-privileges
  ● hologres-uv-compute
  ● hologres-bsi-profile-analysis
  ● hologres-ad-campaign
  ● hologres-instance-health-analyse
  ● hologres-diagnosis-cpu
  ● hologres-diagnosis-memory
  ● hologres-daily-report
  ● hologres-knowledge-base

✨ Installation complete
```

## Development

### Build & Publish to PyPI

```bash
cd agent-skills

# Build only (artifacts in dist/)
python upload_to_pypi.py --build

# Upload to TestPyPI (verification)
export TEST_PYPI_TOKEN="pypi-xxx"
python upload_to_pypi.py --test

# Upload to official PyPI
export UV_PUBLISH_TOKEN="pypi-xxx"
python upload_to_pypi.py --publish

# Bump version and publish
python upload_to_pypi.py --publish --version 0.2.0
```

### Publish to ClawHub (OpenClaw Skill Marketplace)

Publish skills to the [ClawHub](https://clawhub.ai) public skill registry:

```bash
cd agent-skills

# Prerequisites
npm i -g clawhub
clawhub login

# Publish all skills
python publish_to_clawhub.py

# Publish a specific skill
python publish_to_clawhub.py --skill hologres-cli

# Dry-run (preview without publishing)
python publish_to_clawhub.py --dry-run

# Bump patch version before publishing
python publish_to_clawhub.py --bump

# Set a specific version
python publish_to_clawhub.py --version 1.2.0

# Publish under an org handle
python publish_to_clawhub.py --owner holomcp
```

### Publish to Aone (contextlab)

Publish individual skills to the Aone platform:

```bash
cd agent-skills

# Set authentication token
export AONE_TOKEN=<your-token>

# Publish all skills
python publish_to_aone.py

# Publish a specific skill
python publish_to_aone.py --skill hologres-cli

# Dry-run (preview without publishing)
python publish_to_aone.py --dry-run

# Bump patch version before publishing
python publish_to_aone.py --bump

# Set a specific version
python publish_to_aone.py --version 1.2.0
```

### Project Structure

```
agent-skills/
├── skills/                          # Source skills
│   ├── hologres-cli/
│   ├── hologres-query-optimizer/
│   ├── hologres-slow-query-analysis/
│   ├── hologres-schema-generator/
│   ├── hologres-privileges/
│   ├── hologres-uv-compute/
│   ├── hologres-bsi-profile-analysis/
│   ├── hologres-ad-campaign/
│   ├── hologres-instance-health-analyse/
│   ├── hologres-diagnosis-cpu/
│   ├── hologres-diagnosis-memory/
│   ├── hologres-daily-report/
│   └── hologres-knowledge-base/
├── src/
│   └── holo_plugin_installer/
│       ├── __init__.py
│       └── main.py
├── pyproject.toml
├── MANIFEST.in
├── upload_to_pypi.py
├── publish_to_aone.py
├── README.md
└── README_CN.md
```

## License

[Apache License 2.0](../LICENSE) — Copyright 2026 Alibaba Cloud
