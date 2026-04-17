# Getting Started

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [hologres-cli/README.md](file://hologres-cli/README.md)
- [hologres-cli/pyproject.toml](file://hologres-cli/pyproject.toml)
- [hologres-cli/src/hologres_cli/main.py](file://hologres-cli/src/hologres_cli/main.py)
- [hologres-cli/src/hologres_cli/connection.py](file://hologres-cli/src/hologres_cli/connection.py)
- [hologres-cli/src/hologres_cli/commands/status.py](file://hologres-cli/src/hologres_cli/commands/status.py)
- [hologres-cli/src/hologres_cli/commands/schema.py](file://hologres-cli/src/hologres_cli/commands/schema.py)
- [hologres-cli/src/hologres_cli/commands/sql.py](file://hologres-cli/src/hologres_cli/commands/sql.py)
- [hologres-cli/src/hologres_cli/output.py](file://hologres-cli/src/hologres_cli/output.py)
- [hologres-cli/src/hologres_cli/logger.py](file://hologres-cli/src/hologres_cli/logger.py)
- [agent-skills/skills/hologres-cli/SKILL.md](file://agent-skills/skills/hologres-cli/SKILL.md)
- [agent-skills/skills/hologres-cli/references/commands.md](file://agent-skills/skills/hologres-cli/references/commands.md)
- [agent-skills/skills/hologres-cli/references/safety-features.md](file://agent-skills/skills/hologres-cli/references/safety-features.md)
- [hologres-cli/tests/test_connection.py](file://hologres-cli/tests/test_connection.py)
- [hologres-cli/tests/conftest.py](file://hologres-cli/tests/conftest.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [Initial Configuration](#initial-configuration)
6. [Quick Start](#quick-start)
7. [Core Components](#core-components)
8. [Architecture Overview](#architecture-overview)
9. [Detailed Component Analysis](#detailed-component-analysis)
10. [Dependency Analysis](#dependency-analysis)
11. [Performance Considerations](#performance-considerations)
12. [Troubleshooting Guide](#troubleshooting-guide)
13. [Verification Checklist](#verification-checklist)
14. [First-Time User Scenarios](#first-time-user-scenarios)
15. [Conclusion](#conclusion)

## Introduction
This guide helps you quickly install, configure, and use the Hologres AI Plugins CLI tool. It covers Python 3.11+ setup, installation via pip or uv, development dependencies, DSN configuration through CLI flags, environment variables, and config files, plus a step-by-step quick start with connection verification, table listing, and basic SQL queries. It also documents safety features, output formats, and common setup issues.

## Project Structure
The repository provides:
- A Python CLI package under hologres-cli with commands for status, schema inspection, SQL execution, data import/export, and history.
- AI agent skills under agent-skills for Copilot integration.
- Comprehensive tests and documentation.

```mermaid
graph TB
A["Repository Root"] --> B["hologres-cli/"]
A --> C["agent-skills/"]
B --> B1["src/hologres_cli/"]
B1 --> B2["main.py"]
B1 --> B3["connection.py"]
B1 --> B4["commands/"]
B4 --> B4a["status.py"]
B4 --> B4b["schema.py"]
B4 --> B4c["sql.py"]
B1 --> B5["output.py"]
B1 --> B6["logger.py"]
B --> D["README.md"]
B --> E["pyproject.toml"]
C --> C1["skills/hologres-cli/"]
C1 --> C1a["SKILL.md"]
C1 --> C1b["references/commands.md"]
C1 --> C1c["references/safety-features.md"]
```

**Diagram sources**
- [README.md:5-15](file://README.md#L5-L15)
- [hologres-cli/README.md:1-314](file://hologres-cli/README.md#L1-L314)
- [hologres-cli/pyproject.toml:1-68](file://hologres-cli/pyproject.toml#L1-L68)

**Section sources**
- [README.md:5-15](file://README.md#L5-L15)
- [hologres-cli/README.md:1-314](file://hologres-cli/README.md#L1-L314)

## Prerequisites
- Python 3.11+ installed on your system.
- Access to an Alibaba Cloud Hologres instance with a valid database endpoint.
- Basic familiarity with SQL and command-line tools.

**Section sources**
- [README.md:97-101](file://README.md#L97-L101)
- [hologres-cli/README.md:13-16](file://hologres-cli/README.md#L13-L16)

## Installation
Choose one of the following methods:

- Standard editable install:
  - Change to the CLI directory and install in development mode.
  - Use uv to create a virtual environment with Python 3.11 and install.

- Development install (includes test dependencies):
  - Install with dev extras to enable pytest and coverage.

Notes:
- The CLI exposes console scripts for both "hologres" and "hologres-cli".
- The project requires Python >= 3.11.

**Section sources**
- [hologres-cli/README.md:13-36](file://hologres-cli/README.md#L13-L36)
- [hologres-cli/pyproject.toml:1-68](file://hologres-cli/pyproject.toml#L1-L68)
- [README.md:102-111](file://README.md#L102-L111)

## Initial Configuration
The CLI resolves the database DSN in priority order:
1. CLI flag: --dsn "hologres://user:pass@host:port/db"
2. Environment variable: HOLOGRES_DSN
3. Config file: ~/.hologres/config.env with HOLOGRES_DSN=...

DSN format:
- hologres://[user[:password]@]host[:port]/database

Optional instance DSN resolution:
- Named instances can be resolved via HOLOGRES_DSN_<instance_name> in environment or config file.

Configuration file example:
- ~/.hologres/config.env contains HOLOGRES_DSN="hologres://..."

Validation and parsing:
- The CLI validates scheme, host, and database presence, and supports query parameters for connection tuning.

**Section sources**
- [hologres-cli/README.md:89-106](file://hologres-cli/README.md#L89-L106)
- [hologres-cli/src/hologres_cli/connection.py:39-117](file://hologres-cli/src/hologres_cli/connection.py#L39-L117)
- [hologres-cli/src/hologres_cli/connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)

## Quick Start
Follow these steps to verify your installation and connect to Hologres:

1. Install the CLI (see Installation).
2. Set the DSN via one of the configuration methods (CLI flag, environment variable, or config file).
3. Verify connectivity:
   - Run the status command to confirm connection and fetch server info.
4. Explore schema:
   - List tables.
   - Describe a table structure.
   - Export DDL for a table.
   - Get table storage size.
5. Execute SQL:
   - Run read-only queries with LIMIT for large result sets.
   - Review command history.

Expected outcomes:
- status returns connection status, version, database, user, and server address.
- schema tables lists non-system tables.
- schema describe shows column metadata and primary keys.
- sql returns rows and counts; respects row limit protection and masking.

**Section sources**
- [hologres-cli/README.md:110-199](file://hologres-cli/README.md#L110-L199)
- [hologres-cli/src/hologres_cli/commands/status.py:14-61](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L61)
- [hologres-cli/src/hologres_cli/commands/schema.py:42-80](file://hologres-cli/src/hologres_cli/commands/schema.py#L42-L80)
- [hologres-cli/src/hologres_cli/commands/schema.py:83-152](file://hologres-cli/src/hologres_cli/commands/schema.py#L83-L152)
- [hologres-cli/src/hologres_cli/commands/schema.py:155-220](file://hologres-cli/src/hologres_cli/commands/schema.py#L155-L220)
- [hologres-cli/src/hologres_cli/commands/schema.py:223-301](file://hologres-cli/src/hologres_cli/commands/schema.py#L223-L301)
- [hologres-cli/src/hologres_cli/commands/sql.py:34-63](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L63)

## Core Components
- CLI entry point and global options:
  - Provides --dsn, --format, version, and subcommands registration.
- Connection management:
  - Resolves DSN from CLI flag, environment, or config file.
  - Parses DSN into connection parameters with defaults and query overrides.
  - Wraps psycopg connections with helpers for execution and cursors.
- Commands:
  - status: connection health and server info.
  - schema: tables, describe, dump, size.
  - sql: read-only execution with safety checks.
  - data: import/export/count (refer to command reference).
  - history: reads audit log.
- Output formatting:
  - JSON, table, CSV, JSONL with unified success/error wrappers.
- Safety and masking:
  - Row limit protection, write guardrails, sensitive data masking.
- Audit logging:
  - Writes JSONL entries to ~/.hologres/sql-history.jsonl with redaction.

**Section sources**
- [hologres-cli/src/hologres_cli/main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [hologres-cli/src/hologres_cli/connection.py:39-117](file://hologres-cli/src/hologres_cli/connection.py#L39-L117)
- [hologres-cli/src/hologres_cli/connection.py:178-228](file://hologres-cli/src/hologres_cli/connection.py#L178-L228)
- [hologres-cli/src/hologres_cli/commands/status.py:14-61](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L61)
- [hologres-cli/src/hologres_cli/commands/schema.py:42-301](file://hologres-cli/src/hologres_cli/commands/schema.py#L42-L301)
- [hologres-cli/src/hologres_cli/commands/sql.py:34-199](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L199)
- [hologres-cli/src/hologres_cli/output.py:16-54](file://hologres-cli/src/hologres_cli/output.py#L16-L54)
- [hologres-cli/src/hologres_cli/logger.py:36-73](file://hologres-cli/src/hologres_cli/logger.py#L36-L73)

## Architecture Overview
High-level flow from CLI invocation to database execution and output formatting.

```mermaid
graph TB
U["User"] --> M["CLI Main<br/>main.py"]
M --> O["Global Options<br/>--dsn, --format"]
O --> C["Connection Resolver<br/>connection.py"]
C --> P["DSN Parser<br/>connection.py"]
M --> CMD["Command Handler<br/>status/schema/sql"]
CMD --> CONN["HologresConnection<br/>connection.py"]
CONN --> DB["PostgreSQL/Hologres"]
CMD --> OUT["Output Formatter<br/>output.py"]
CMD --> LOG["Audit Logger<br/>logger.py"]
```

**Diagram sources**
- [hologres-cli/src/hologres_cli/main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [hologres-cli/src/hologres_cli/connection.py:39-170](file://hologres-cli/src/hologres_cli/connection.py#L39-L170)
- [hologres-cli/src/hologres_cli/output.py:23-54](file://hologres-cli/src/hologres_cli/output.py#L23-L54)
- [hologres-cli/src/hologres_cli/logger.py:36-73](file://hologres-cli/src/hologres_cli/logger.py#L36-L73)

## Detailed Component Analysis

### CLI Entry Point and Commands
- Registers subcommands and attaches global options.
- Exposes ai-guide and history commands.
- Handles DSNError and generic exceptions with structured error output.

```mermaid
sequenceDiagram
participant U as "User"
participant CLI as "CLI Main"
participant Conn as "Connection Resolver"
participant Cmd as "Command Handler"
participant DB as "Database"
U->>CLI : "hologres status"
CLI->>Conn : resolve_raw_dsn()
Conn-->>CLI : "DSN string"
CLI->>Cmd : status_cmd(ctx)
Cmd->>DB : execute SELECT ...
DB-->>Cmd : "rows"
Cmd-->>U : "JSON success"
```

**Diagram sources**
- [hologres-cli/src/hologres_cli/main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [hologres-cli/src/hologres_cli/commands/status.py:14-61](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L61)
- [hologres-cli/src/hologres_cli/connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)

**Section sources**
- [hologres-cli/src/hologres_cli/main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [hologres-cli/src/hologres_cli/commands/status.py:14-61](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L61)

### Connection Management
- Priority resolution: CLI flag > environment > config file.
- DSN parsing supports multiple schemes and query parameters.
- Connection wrapper handles lazy connection, cursor creation, and execution.

```mermaid
flowchart TD
Start(["resolve_raw_dsn"]) --> CheckFlag["CLI --dsn present?"]
CheckFlag --> |Yes| ReturnFlag["Return flag DSN"]
CheckFlag --> |No| CheckEnv["HOLOGRES_DSN env var?"]
CheckEnv --> |Yes| ReturnEnv["Return env DSN"]
CheckEnv --> |No| CheckFile["~/.hologres/config.env exists?"]
CheckFile --> |Yes| ReadFile["Read HOLOGRES_DSN"]
ReadFile --> Found{"Value found?"}
Found --> |Yes| ReturnFile["Return file DSN"]
Found --> |No| RaiseErr["Raise DSNError"]
CheckFile --> |No| RaiseErr
```

**Diagram sources**
- [hologres-cli/src/hologres_cli/connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)

**Section sources**
- [hologres-cli/src/hologres_cli/connection.py:39-117](file://hologres-cli/src/hologres_cli/connection.py#L39-L117)
- [hologres-cli/src/hologres_cli/connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)

### SQL Execution and Safety
- Enforces row limit protection for SELECT without LIMIT (>100 rows).
- Blocks write operations by default; requires explicit intent.
- Masks sensitive fields by column name patterns.
- Supports multiple output formats and JSONL for streaming.

```mermaid
flowchart TD
QStart(["sql_cmd"]) --> Split["Split statements"]
Split --> ExecSingle["_execute_single"]
ExecSingle --> WriteCheck{"Write keyword?"}
WriteCheck --> |Yes| BlockWrite["Return WRITE_BLOCKED"]
WriteCheck --> |No| IsSelect{"SELECT?"}
IsSelect --> |No| RunQuery["Execute query"]
IsSelect --> |Yes| HasLimit{"Has LIMIT?"}
HasLimit --> |Yes| RunQuery
HasLimit --> |No| Probe["Probe with LIMIT 101"]
Probe --> TooMany{"Rows > 100?"}
TooMany --> |Yes| LimitErr["Return LIMIT_REQUIRED"]
TooMany --> |No| RunQuery
RunQuery --> Mask["Apply masking if enabled"]
Mask --> Done(["Return rows + count"])
```

**Diagram sources**
- [hologres-cli/src/hologres_cli/commands/sql.py:34-134](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L134)

**Section sources**
- [hologres-cli/src/hologres_cli/commands/sql.py:34-199](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L199)
- [hologres-cli/src/hologres_cli/output.py:16-54](file://hologres-cli/src/hologres_cli/output.py#L16-L54)

### Schema Inspection
- tables: lists non-system tables optionally filtered by schema.
- describe: returns columns and primary keys for a table.
- dump: exports DDL via internal function.
- size: reports pretty and byte sizes for a table.

```mermaid
sequenceDiagram
participant U as "User"
participant CLI as "schema describe"
participant Conn as "HologresConnection"
participant DB as "Database"
U->>CLI : "hologres schema describe public.users"
CLI->>Conn : execute information_schema queries
DB-->>CLI : "columns + PK"
CLI-->>U : "JSON with schema and columns"
```

**Diagram sources**
- [hologres-cli/src/hologres_cli/commands/schema.py:83-152](file://hologres-cli/src/hologres_cli/commands/schema.py#L83-L152)

**Section sources**
- [hologres-cli/src/hologres_cli/commands/schema.py:42-301](file://hologres-cli/src/hologres_cli/commands/schema.py#L42-L301)

## Dependency Analysis
- Python version requirement: >= 3.11.
- Core runtime dependencies: click, psycopg[binary], tabulate.
- Optional dev dependencies: pytest, pytest-cov, pytest-mock.
- Console scripts expose "hologres" and "hologres-cli".

```mermaid
graph TB
P["Python >= 3.11"] --> R["Runtime deps"]
R --> R1["click"]
R --> R2["psycopg[binary]"]
R --> R3["tabulate"]
R --> Dev["Dev deps"]
Dev --> Dev1["pytest"]
Dev --> Dev2["pytest-cov"]
Dev --> Dev3["pytest-mock"]
```

**Diagram sources**
- [hologres-cli/pyproject.toml:5-21](file://hologres-cli/pyproject.toml#L5-L21)

**Section sources**
- [hologres-cli/pyproject.toml:5-21](file://hologres-cli/pyproject.toml#L5-L21)

## Performance Considerations
- Use LIMIT for large result sets to avoid timeouts and excessive memory usage.
- Prefer JSON output for automation and JSONL for streaming logs.
- Use data export/import for bulk operations instead of ad-hoc SQL for large datasets.
- Keep queries targeted and leverage table size information from schema size.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common setup issues and resolutions:

- No DSN configured:
  - Symptom: DSNError indicating missing DSN.
  - Resolution: Provide DSN via --dsn flag, HOLOGRES_DSN environment variable, or ~/.hologres/config.env.

- Invalid DSN scheme or missing components:
  - Symptom: DSNError mentioning invalid scheme or missing hostname/database.
  - Resolution: Ensure hologres:// or postgresql:// scheme, include host and database.

- Connection failures:
  - Symptom: CONNECTION_ERROR in output.
  - Resolution: Verify network access, credentials, and endpoint; test with status.

- Row limit errors:
  - Symptom: LIMIT_REQUIRED when SELECT returns >100 rows without LIMIT.
  - Resolution: Add LIMIT or use --no-limit-check cautiously.

- Write operations blocked:
  - Symptom: WRITE_BLOCKED when attempting INSERT/UPDATE/DELETE.
  - Resolution: Use --write flag explicitly; ensure WHERE clause for UPDATE/DELETE.

- Sensitive data exposure concerns:
  - Symptom: Unmasked sensitive fields in output.
  - Resolution: Use --no-mask to disable masking if needed; review masking patterns.

- History not recorded:
  - Symptom: Empty history or missing log file.
  - Resolution: Ensure ~/.hologres directory is writable; run commands that trigger logging.

**Section sources**
- [hologres-cli/src/hologres_cli/connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [hologres-cli/src/hologres_cli/connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [hologres-cli/src/hologres_cli/commands/sql.py:78-101](file://hologres-cli/src/hologres_cli/commands/sql.py#L78-L101)
- [hologres-cli/src/hologres_cli/commands/sql.py:164-178](file://hologres-cli/src/hologres_cli/commands/sql.py#L164-L178)
- [hologres-cli/src/hologres_cli/logger.py:36-73](file://hologres-cli/src/hologres_cli/logger.py#L36-L73)

## Verification Checklist
- Python 3.11+ is installed.
- CLI installed in development mode or with dev extras.
- DSN configured via one of the supported methods.
- status command returns connected state and basic server info.
- schema tables lists expected tables.
- sql returns rows with appropriate counts and respects LIMIT.
- history command shows recent operations.

**Section sources**
- [hologres-cli/README.md:13-36](file://hologres-cli/README.md#L13-L36)
- [hologres-cli/src/hologres_cli/commands/status.py:14-61](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L61)
- [hologres-cli/src/hologres_cli/commands/schema.py:42-80](file://hologres-cli/src/hologres_cli/commands/schema.py#L42-L80)
- [hologres-cli/src/hologres_cli/commands/sql.py:34-63](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L63)
- [hologres-cli/src/hologres_cli/logger.py:89-105](file://hologres-cli/src/hologres_cli/logger.py#L89-L105)

## First-Time User Scenarios
- Scenario 1: Basic connection and inspection
  - Steps: Set HOLOGRES_DSN, run status, list tables, describe a table, export DDL.
  - Expected: JSON responses with success ok: true and data payload.

- Scenario 2: Safe SQL exploration
  - Steps: Run SELECT with LIMIT; observe row limit enforcement; adjust LIMIT or use --no-limit-check.
  - Expected: Controlled results; LIMIT_REQUIRED error when exceeding threshold without LIMIT.

- Scenario 3: Audit and history
  - Steps: Execute several commands; run history to review recent operations.
  - Expected: History entries with timestamps, commands, and statuses.

**Section sources**
- [hologres-cli/README.md:289-309](file://hologres-cli/README.md#L289-L309)
- [hologres-cli/src/hologres_cli/commands/sql.py:91-101](file://hologres-cli/src/hologres_cli/commands/sql.py#L91-L101)
- [hologres-cli/src/hologres_cli/logger.py:89-105](file://hologres-cli/src/hologres_cli/logger.py#L89-L105)

## Conclusion
You now have the essentials to install, configure, and use the Hologres AI Plugins CLI. Start with status to verify connectivity, explore schema to understand your database layout, and run safe SQL queries with proper LIMIT clauses. Use the provided configuration methods to persist your DSN and leverage safety features and structured output for reliable automation.

[No sources needed since this section summarizes without analyzing specific files]