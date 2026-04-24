# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hologres AI Plugins — a monorepo with two Python packages for Alibaba Cloud Hologres (a Postgres-compatible database):
- **hologres-cli/**: AI-agent-friendly CLI with safety guardrails and structured JSON output
- **agent-skills/**: Interactive installer that distributes AI agent skills (SKILL.md files) to coding tools (Claude Code, Cursor, Copilot, etc.)

## Development Commands

### hologres-cli

```bash
cd hologres-cli

# Install (dev mode with test deps)
pip install -e ".[dev]"

# Run unit tests (no database needed)
pytest -m unit

# Run single test file
pytest tests/test_commands/test_sql.py

# Run integration tests (requires HOLOGRES_TEST_DSN)
export HOLOGRES_TEST_DSN="hologres://user:password@host:port/database"
pytest -m integration

# Run with coverage
pytest --cov=src/hologres_cli --cov-report=term-missing

# Run CLI locally
hologres status
hologres sql run "SELECT 1"
```

### agent-skills

```bash
cd agent-skills
uv sync
uv run hologres-agent-skills       # Interactive installer
uv run upload_to_pypi.py           # Build wheel for PyPI
```

## Architecture

### hologres-cli

Built with **Click** (CLI framework) and **psycopg3** (Postgres driver). Entry point: `hologres_cli.main:cli`.

**Command flow**: `main.py` (Click group) → `commands/*.py` (subcommand groups) → `connection.py` (DB access) → `output.py` (format response)

Key modules:
- `connection.py` — DSN resolution (CLI flag > env var > `~/.hologres/config.env`), `HologresConnection` wrapper around psycopg3. Accepts `hologres://` and `postgresql://` schemes.
- `commands/sql.py` — SQL execution with safety: write guard (`--write` flag), LIMIT enforcement (>100 rows), dangerous write block (DELETE/UPDATE without WHERE), sensitive data masking, field truncation.
- `commands/schema.py` — Schema inspection. Uses `psycopg.sql.Identifier` for safe identifier escaping. Shared helpers `_list_tables`, `fetch_table_structure`, `_dump_table_ddl` are reused by `commands/table.py`.
- `output.py` — Unified output in JSON/table/CSV/JSONL. All responses follow `{ok: true/false, data/error: ...}`.
- `masking.py` — Auto-masks phone/email/password/id_card/bank_card columns by name pattern matching.
- `logger.py` — Audit log to `~/.hologres/sql-history.jsonl` with auto-rotation at 10MB. Redacts sensitive SQL literals.

**Test structure**: Unit tests in `tests/test_*.py` and `tests/test_commands/` mock psycopg via `conftest.py` fixtures (`mock_psycopg`, `mock_get_connection`). Integration tests in `tests/integration/` hit a real database. Coverage threshold: 95%.

### agent-skills

`holo_plugin_installer/main.py` — Interactive CLI (using `questionary`) that copies skill directories from `skills/` to target tool directories (e.g., `.claude/skills`, `.cursor/skills`). Skills are SKILL.md + reference docs, not code.

Three bundled skills:
- `hologres-cli` — CLI usage guide for AI agents
- `hologres-query-optimizer` — EXPLAIN plan analysis
- `hologres-slow-query-analysis` — hg_query_log diagnostics

## Key Conventions

- Hologres DSN uses `hologres://` scheme (internally normalized to `postgresql://` for psycopg)
- All CLI output is JSON by default with `{ok, data/error}` envelope; use `-f table|csv|jsonl` for other formats
- SQL safety: reads only by default; writes require `--write`; no DELETE/UPDATE without WHERE even with `--write`
- Shared command logic (e.g., `_list_tables`, `_dump_table_ddl`) lives in `schema.py` and is imported by `table.py` — when adding overlapping commands, extract to a shared function first
- Test markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
- Hologres is a database that uses the PostgreSQL protocol.
