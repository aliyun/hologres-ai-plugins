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
# ...or with uv: `uv sync --extra dev` (pytest etc. live in [project.optional-dependencies].dev)

# Run unit tests (no database needed)
pytest -m unit
# Env quirk: in a uv-managed venv, `uv run pytest` / `uv run python -m pytest` may resolve
# to the wrong interpreter (no pytest). Use `.venv/bin/python -m pytest` directly.

# Run single test file
pytest tests/test_commands/test_sql.py

# Run integration tests (requires TEST_PROFILE_NAME)
export TEST_PROFILE_NAME="default"
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
pytest tests/                       # Catalog consistency + publish checks
```

### Git Hooks (optional, recommended)

The repo ships `.githooks/pre-commit`. Enable once per clone:

```bash
git config --local core.hooksPath .githooks
```

It runs three stages: (1) forwards to your global pre-commit hook (e.g. AccessKey scanner) — required because `core.hooksPath` overrides the global hook path; (2) runs `agent-skills/tests/test_catalog_consistency.py` to block "ghost skills"; (3) runs `.githooks/check_uv_lock_sync.py` to block commits that edit dependency sections in any `pyproject.toml` (next to a tracked `uv.lock`) without also staging the lock — plain-text parsing, no tomllib, so it runs on the system `python3` (<3.11). Bypass a single commit with `git commit --no-verify`.

## Architecture

### hologres-cli

Built with **Click** (CLI framework) and **psycopg3** (Postgres driver). Entry point: `hologres_cli.main:cli`, exposed as both `hologres` and `hologres-cli` console scripts. Command groups are wired **manually** via `cli.add_command(...)` in `main.py` — a new `commands/*.py` module is NOT reachable until you register it there.

**Command flow**: `main.py` (Click group) → `commands/*.py` (subcommand groups) → `connection.py` (DB access) → `output.py` (format response)

Key modules:
- `connection.py` — `HologresConnection` wrapper around psycopg3. Resolves the connection via **Profile** config (`~/.hologres/config.json`; resolution: `--profile` flag > current profile > error). **Dual connection mode**: JDBC/PostgreSQL wire protocol (psycopg) is tried first, then transparently falls back to the OpenAPI `ExecuteStatement` API. Controlled by `connection_mode`: `auto` (default, JDBC→API fallback) / `jdbc` / `api`. **Auth modes** (`auth_mode` profile field): `ram` (AccessKey, default), `basic` (DB account — username uses `BASIC$<name>` format), `sts` (temporary credentials, see `credentials.py`). In `sts` mode `get_connection` resolves the 3-tuple and injects it into a profile copy before building the DSN; JDBC passes SecurityToken via libpq `options=sts_token=<token>` (URL-encoded, `quote(..., safe="")` — `+` must become `%2B` or `parse_qs` eats it).
- `credentials.py` — **STS credential hub**, shared by SQL / `instance-manage` / `metric` (all call `get_credential_client`). Returns a singleton `alibabacloud-credentials` `CredentialClient`: profile `credentials_uri` field → explicit `credentials_uri` provider (bypasses the default chain); else default chain (STS env vars → OIDC → `~/.aliyun/config.json` → ECS metadata → env `ALIBABA_CLOUD_CREDENTIALS_URI`). `resolve_sts_credentials()` extracts the {ak, sk, security_token} tuple for JDBC. Temporary credentials are **never persisted** to `config.json`; auto-refreshed in-process by the SDK (Session-type). Failures raise `CredentialsError` carrying a precise `ErrorCode` — when wiring a new command, catch it and translate via `output.error(e.code, str(e))`.
- `commands/sql.py` — SQL execution with safety: write guard (`--write` flag), LIMIT enforcement (>100 rows), dangerous write block (DELETE/UPDATE without WHERE), sensitive data masking, field truncation.
- `commands/schema.py` — Schema inspection. Uses `psycopg.sql.Identifier` for safe identifier escaping. Shared helpers `_list_tables`, `fetch_table_structure`, `_dump_table_ddl` are reused by `commands/table.py`.
- `commands/extension.py` — Extension management. List installed extensions and create new extensions with `psycopg.sql.Identifier` for safe identifier escaping.
- `output.py` — Unified output in JSON/table/CSV/JSONL. All responses follow `{ok: true/false, data/error: ...}`.
- `errors.py` — `ErrorCode` enum; each member's value is an `ErrorMeta(code, retryable, hint)` NamedTuple. `output.error(code, msg)` accepts either an `ErrorCode` member or a plain string (string is looked up in the registry to attach retryable/hint). Pattern for new commands: raise a module-specific exception, catch at the command layer, translate to `output.error(ErrorCode.X, msg)`; add new codes to this enum (the `_CODE_TO_META` registry auto-collects them).
- `masking.py` — Auto-masks phone/email/password/id_card/bank_card columns by name pattern matching.
- `logger.py` — Audit log to `~/.hologres/sql-history.jsonl` with auto-rotation at 10MB. Redacts sensitive SQL literals.

**Command groups** (all registered in `main.py`): `config`, `status`, `sql`, `schema` (legacy, see note below), `table` (new home), `view`, `partition`, `extension`, `guc`, `data`, `dt` (Dynamic Table), `ai`/`volume`/`model` (AI generation + OSS volume storage), `instance`/`warehouse`/`instance-manage`/`metric` (instance info + cloud-monitor metrics), `foreign` (FDW/MaxCompute), plus inline `history` / `ai-guide`. Each lives in `commands/<name>.py`; refer to the file or `--help` for options.

**Test structure**: Unit tests in `tests/test_*.py` and `tests/test_commands/` mock psycopg via `conftest.py` fixtures (`mock_psycopg`, `mock_get_connection`). Integration tests in `tests/integration/` hit a real database. Coverage threshold: 95%.

### agent-skills

`holo_plugin_installer/main.py` — Interactive CLI (using `questionary`) that copies skill directories from `skills/` to target tool directories (e.g., `.claude/skills`, `.cursor/skills`). Skills are SKILL.md + reference docs, not code.

`skills/` ships **13 skills** (each is a directory with `SKILL.md` + reference docs, not code). The **runtime source of truth** for which skills are installable is the `AVAILABLE_SKILLS` list in `holo_plugin_installer/main.py`. Coverage: CLI usage (`hologres-cli`); query tuning (`hologres-query-optimizer`, `hologres-slow-query-analysis`); DDL/auth/partitioning (`hologres-schema-generator`, `hologres-privileges`); analytics patterns (`hologres-uv-compute`, `hologres-bsi-profile-analysis`, `hologres-ad-campaign`); operations & diagnostics (`hologres-instance-health-analyse`, `hologres-diagnosis-cpu`, `hologres-diagnosis-memory`, `hologres-daily-report`, `hologres-knowledge-base`). See the **Catalog Consistency** convention below before adding or removing any skill.

## Key Conventions

- Hologres DSN uses `hologres://` scheme (internally normalized to `postgresql://` for psycopg)
- All CLI output is JSON by default with `{ok, data/error}` envelope; use `-f table|csv|jsonl` for other formats
- SQL safety: reads only by default; writes require `--write`; no DELETE/UPDATE without WHERE even with `--write`
- Shared command logic (e.g., `_list_tables`, `_dump_table_ddl`) lives in `schema.py` and is imported by `table.py` — when adding overlapping commands, extract to a shared function first
- Test markers: `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.slow`
- Hologres is a database that uses the PostgreSQL protocol.
- schema.py是老的实现无需继续更新，新的实现迁移到 table.py 中
- 当在 @hologres-cli 下实现/修改命令后，记得同时更新文档：@README.md @README_CN.md @hologres-cli/README.md @hologres-cli/README_CN.md @agent-skills/skills/hologres-cli/SKILL.md @agent-skills/skills/hologres-cli/references/commands.md
- 当在 @agent-skills/skills/ 下增删 skill 时，必须同步 5 个 catalog，否则 `test_catalog_consistency.py` 会报"ghost skill"：运行时真理源是 `holo_plugin_installer/main.py` 的 `AVAILABLE_SKILLS`，外加 `agent-skills/README.md`、`agent-skills/README_CN.md`、根 `README.md`、根 `README_CN.md`
