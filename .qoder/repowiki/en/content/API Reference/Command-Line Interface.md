# Command-Line Interface

<cite>
**Referenced Files in This Document**
- [main.py](file://hologres-cli/src/hologres_cli/main.py)
- [__init__.py](file://hologres-cli/src/hologres_cli/__init__.py)
- [schema.py](file://hologres-cli/src/hologres_cli/commands/schema.py)
- [sql.py](file://hologres-cli/src/hologres_cli/commands/sql.py)
- [data.py](file://hologres-cli/src/hologres_cli/commands/data.py)
- [status.py](file://hologres-cli/src/hologres_cli/commands/status.py)
- [instance.py](file://hologres-cli/src/hologres_cli/commands/instance.py)
- [warehouse.py](file://hologres-cli/src/hologres_cli/commands/warehouse.py)
- [connection.py](file://hologres-cli/src/hologres_cli/connection.py)
- [output.py](file://hologres-cli/src/hologres_cli/output.py)
- [logger.py](file://hologres-cli/src/hologres_cli/logger.py)
- [README.md](file://hologres-cli/README.md)
- [pyproject.toml](file://hologres-cli/pyproject.toml)
- [test_schema.py](file://hologres-cli/tests/test_commands/test_schema.py)
- [test_sql.py](file://hologres-cli/tests/test_commands/test_sql.py)
- [test_data.py](file://hologres-cli/tests/test_commands/test_data.py)
</cite>

## Table of Contents
1. [Introduction](#introduction)
2. [Project Structure](#project-structure)
3. [Core Components](#core-components)
4. [Architecture Overview](#architecture-overview)
5. [Detailed Component Analysis](#detailed-component-analysis)
6. [Dependency Analysis](#dependency-analysis)
7. [Performance Considerations](#performance-considerations)
8. [Troubleshooting Guide](#troubleshooting-guide)
9. [Conclusion](#conclusion)
10. [Appendices](#appendices)

## Introduction
This document provides comprehensive command-line interface (CLI) documentation for the Hologres CLI tool. It covers all available commands, their parameters and flags, usage patterns, global options, command chaining, parameter precedence, environment variable usage, output formats, exit codes, error handling, and practical examples. The CLI is designed to be AI-agent-friendly, with structured JSON output, safety guardrails, and audit logging.

## Project Structure
The CLI is organized around a central Click group with subcommands for schema, SQL execution, data import/export/count, status, instance, and warehouse. Global options apply to all commands, and shared modules handle connection management, output formatting, and logging.

```mermaid
graph TB
CLI["CLI Group<br/>Global Options"] --> SCHEMA["schema group<br/>tables/describe/dump/size"]
CLI --> SQL["sql command<br/>read-only queries"]
CLI --> DATA["data group<br/>export/import/count"]
CLI --> STATUS["status command"]
CLI --> INSTANCE["instance command"]
CLI --> WAREHOUSE["warehouse command"]
SCHEMA --> CONN["Connection Module"]
SQL --> CONN
DATA --> CONN
STATUS --> CONN
INSTANCE --> CONN
WAREHOUSE --> CONN
SCHEMA --> OUTPUT["Output Module"]
SQL --> OUTPUT
DATA --> OUTPUT
STATUS --> OUTPUT
INSTANCE --> OUTPUT
WAREHOUSE --> OUTPUT
SCHEMA --> LOGGER["Logger Module"]
SQL --> LOGGER
DATA --> LOGGER
STATUS --> LOGGER
INSTANCE --> LOGGER
WAREHOUSE --> LOGGER
```

**Diagram sources**
- [main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [schema.py:36-301](file://hologres-cli/src/hologres_cli/commands/schema.py#L36-L301)
- [sql.py:34-199](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L199)
- [data.py:44-266](file://hologres-cli/src/hologres_cli/commands/data.py#L44-L266)
- [status.py:14-62](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L62)
- [instance.py:14-71](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L71)
- [warehouse.py:22-106](file://hologres-cli/src/hologres_cli/commands/warehouse.py#L22-L106)
- [connection.py:225-229](file://hologres-cli/src/hologres_cli/connection.py#L225-L229)
- [output.py:16-143](file://hologres-cli/src/hologres_cli/output.py#L16-L143)
- [logger.py:36-105](file://hologres-cli/src/hologres_cli/logger.py#L36-L105)

**Section sources**
- [main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [pyproject.toml:23-25](file://hologres-cli/pyproject.toml#L23-L25)

## Core Components
- Global options:
  - --dsn: Hologres DSN (supports hologres://user:pass@host:port/db)
  - --format/-f: Output format (json, table, csv, jsonl)
  - --version: Print version and exit
- Command groups and commands:
  - schema: tables, describe, dump, size
  - sql: read-only SQL execution with safety checks
  - data: export, import, count
  - status: connection and server info
  - instance: instance metadata by name
  - warehouse: compute group info
- Additional commands:
  - ai-guide: generate AI agent guide
  - history: show recent command history

**Section sources**
- [main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [main.py:52-62](file://hologres-cli/src/hologres_cli/main.py#L52-L62)
- [main.py:86-96](file://hologres-cli/src/hologres_cli/main.py#L86-L96)
- [README.md:108-199](file://hologres-cli/README.md#L108-L199)

## Architecture Overview
The CLI follows a layered architecture:
- CLI layer: Click decorators define commands and options
- Command layer: Each command validates inputs, resolves DSN, executes queries, and formats output
- Infrastructure layer: Connection management, output formatting, and audit logging

```mermaid
sequenceDiagram
participant User as "User"
participant CLI as "CLI Main"
participant Cmd as "Command Handler"
participant Conn as "Connection"
participant DB as "Hologres DB"
User->>CLI : hologres [global options] <command> [args/flags]
CLI->>Cmd : dispatch to command handler
Cmd->>Conn : resolve DSN and connect
Conn->>DB : execute SQL/COPY
DB-->>Conn : results
Conn-->>Cmd : rows or status
Cmd->>Cmd : format output (JSON/table/csv/jsonl)
Cmd-->>CLI : formatted string
CLI-->>User : print output
```

**Diagram sources**
- [main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [connection.py:225-229](file://hologres-cli/src/hologres_cli/connection.py#L225-L229)
- [output.py:23-54](file://hologres-cli/src/hologres_cli/output.py#L23-L54)

## Detailed Component Analysis

### Global Options and Parameter Precedence
- DSN resolution precedence (highest to lowest):
  1. --dsn flag
  2. HOLOGRES_DSN environment variable
  3. ~/.hologres/config.env file
- Output format:
  - --format or -f selects among json, table, csv, jsonl
  - Default is json
- Version:
  - --version prints version and exits

```mermaid
flowchart TD
Start(["Resolve DSN"]) --> Flag{"--dsn provided?"}
Flag --> |Yes| UseFlag["Use CLI flag"]
Flag --> |No| Env{"HOLOGRES_DSN env var?"}
Env --> |Yes| UseEnv["Use environment variable"]
Env --> |No| File{"~/.hologres/config.env exists?"}
File --> |Yes| ReadFile["Read HOLOGRES_DSN from file"]
File --> |No| Error["Raise DSNError"]
UseFlag --> Done(["Resolved"])
UseEnv --> Done
ReadFile --> Done
Error --> Done
```

**Diagram sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)

**Section sources**
- [main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [README.md:89-106](file://hologres-cli/README.md#L89-L106)

### schema Command
- Subcommands:
  - schema tables [--schema SCHEMA]
  - schema describe TABLE
  - schema dump SCHEMA.TABLE
  - schema size SCHEMA.TABLE
- Behavior:
  - Connects using resolved DSN
  - Executes safe queries with identifier validation
  - Logs operations and prints structured output

```mermaid
sequenceDiagram
participant U as "User"
participant M as "CLI Main"
participant S as "schema.tables"
participant C as "Connection"
participant D as "DB"
U->>M : hologres schema tables [--schema]
M->>S : invoke handler
S->>C : get_connection(dsn)
S->>D : SELECT pg_tables (filtered by schema if provided)
D-->>S : rows
S->>S : log_operation
S-->>U : success_rows(JSON/table/csv/jsonl)
```

**Diagram sources**
- [schema.py:42-81](file://hologres-cli/src/hologres_cli/commands/schema.py#L42-L81)
- [connection.py:225-229](file://hologres-cli/src/hologres_cli/connection.py#L225-L229)
- [output.py:31-54](file://hologres-cli/src/hologres_cli/output.py#L31-L54)
- [logger.py:36-73](file://hologres-cli/src/hologres_cli/logger.py#L36-L73)

**Section sources**
- [schema.py:42-81](file://hologres-cli/src/hologres_cli/commands/schema.py#L42-L81)
- [schema.py:83-153](file://hologres-cli/src/hologres_cli/commands/schema.py#L83-L153)
- [schema.py:155-221](file://hologres-cli/src/hologres_cli/commands/schema.py#L155-L221)
- [schema.py:223-301](file://hologres-cli/src/hologres_cli/commands/schema.py#L223-L301)

### sql Command
- Purpose: Execute SQL queries and view execution plans
- Subcommands:
  - sql run: Execute read-only SQL with safety guardrails
  - sql explain: Show execution plan for a SQL query
- Flags (sql run):
  - --no-limit-check: Bypass row limit probe
  - --no-mask: Disable sensitive data masking
  - --with-schema: Include schema metadata in output
- Safety features (sql run):
  - Blocks write operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT, REVOKE)
  - Enforces LIMIT requirement for SELECT returning >100 rows (probe with LIMIT 101)
- Behavior:
  - sql run: Supports multiple statements separated by ';'; truncates large fields and masks sensitive data by default
  - sql explain: Prepends EXPLAIN to the query, returns execution plan lines; no safety guardrails needed (read-only operation)

```mermaid
flowchart TD
Start(["sql <query>"]) --> Split["Split statements by ';'"]
Split --> Exec["For each statement:<br/>- strip whitespace<br/>- detect write vs select"]
Exec --> Write{"Write operation?"}
Write --> |Yes| Block["Block with WRITE_BLOCKED"]
Write --> |No| Select{"SELECT without LIMIT?"}
Select --> |Yes| Probe["Run probe with LIMIT 101"]
Probe --> Many{"Rows > 100?"}
Many --> |Yes| LimitErr["Return LIMIT_REQUIRED"]
Many --> |No| RunSel["Execute original SELECT"]
Select --> |No| RunSel
RunSel --> Mask["Truncate large fields<br/>Apply masking if enabled"]
Mask --> Out["Format output (JSON/table/csv/jsonl)"]
Block --> Out
LimitErr --> Out
```

**Diagram sources**
- [sql.py:34-64](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L64)
- [sql.py:66-135](file://hologres-cli/src/hologres_cli/commands/sql.py#L66-L135)
- [sql.py:137-199](file://hologres-cli/src/hologres_cli/commands/sql.py#L137-L199)

**Section sources**
- [sql.py:34-64](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L64)
- [sql.py:66-135](file://hologres-cli/src/hologres_cli/commands/sql.py#L66-L135)
- [sql.py:137-199](file://hologres-cli/src/hologres_cli/commands/sql.py#L137-L199)
- [README.md:235-287](file://hologres-cli/README.md#L235-L287)

### data Command
- Subcommands:
  - data export TABLE --file FILE [--query QUERY] [--delimiter DELIMITER]
  - data import TABLE --file FILE [--delimiter DELIMITER] [--truncate]
  - data count TABLE [--where WHERE]
- Behavior:
  - Uses PostgreSQL COPY protocol for efficient I/O
  - Validates identifiers and builds safe SQL with psycopg.sql.Identifier
  - Handles CSV header detection and column mapping
  - Logs operations with row counts and durations

```mermaid
sequenceDiagram
participant U as "User"
participant M as "CLI Main"
participant D as "data.export"
participant C as "Connection"
participant F as "Filesystem"
U->>M : hologres data export <table> -f <file> [-q|-d]
M->>D : invoke handler
D->>C : get_connection(dsn)
D->>C : cursor.copy(COPY ... TO STDOUT)
C-->>D : streaming bytes
D->>F : write to file
D->>D : log_operation
D-->>U : success JSON with rows/file/duration
```

**Diagram sources**
- [data.py:50-123](file://hologres-cli/src/hologres_cli/commands/data.py#L50-L123)
- [data.py:125-214](file://hologres-cli/src/hologres_cli/commands/data.py#L125-L214)
- [data.py:216-266](file://hologres-cli/src/hologres_cli/commands/data.py#L216-L266)

**Section sources**
- [data.py:50-123](file://hologres-cli/src/hologres_cli/commands/data.py#L50-L123)
- [data.py:125-214](file://hologres-cli/src/hologres_cli/commands/data.py#L125-L214)
- [data.py:216-266](file://hologres-cli/src/hologres_cli/commands/data.py#L216-L266)

### status Command
- Purpose: Show connection status, version, database, user, and server address/port
- Output: Structured JSON with masked DSN

**Section sources**
- [status.py:14-62](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L62)

### instance Command
- Purpose: Query Hologres instance information by instance name
- Resolution: Uses HOLOGRES_DSN_<instance_name> from environment or ~/.hologres/config.env
- Output: Instance version and max connections

**Section sources**
- [instance.py:14-71](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L71)
- [connection.py:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)

### warehouse Command
- Purpose: Query compute group (warehouse) information
- Filters: Optional warehouse_name argument to filter results
- Output: Enriched rows with human-readable status and target_status descriptions

**Section sources**
- [warehouse.py:22-106](file://hologres-cli/src/hologres_cli/commands/warehouse.py#L22-L106)

### Additional Commands
- ai-guide: Generates a guide for AI agents using the CLI
- history: Shows recent command history from audit log

**Section sources**
- [main.py:52-62](file://hologres-cli/src/hologres_cli/main.py#L52-L62)
- [main.py:86-96](file://hologres-cli/src/hologres_cli/main.py#L86-L96)

## Dependency Analysis
- Entry points:
  - Script entry points: hologres and hologres-cli both map to the CLI group
- Internal dependencies:
  - All commands depend on connection.py for DSN resolution and database connectivity
  - All commands depend on output.py for consistent JSON/table/csv/jsonl formatting
  - All commands depend on logger.py for audit logging
- External libraries:
  - click: CLI framework
  - psycopg: PostgreSQL driver
  - tabulate: table format rendering

```mermaid
graph LR
P["pyproject.toml<br/>scripts"] --> M["main.py"]
M --> SC["schema.py"]
M --> SQ["sql.py"]
M --> DA["data.py"]
M --> ST["status.py"]
M --> IN["instance.py"]
M --> WH["warehouse.py"]
SC --> CONN["connection.py"]
SQ --> CONN
DA --> CONN
ST --> CONN
IN --> CONN
WH --> CONN
SC --> OUT["output.py"]
SQ --> OUT
DA --> OUT
ST --> OUT
IN --> OUT
WH --> OUT
SC --> LOG["logger.py"]
SQ --> LOG
DA --> LOG
ST --> LOG
IN --> LOG
WH --> LOG
```

**Diagram sources**
- [pyproject.toml:23-25](file://hologres-cli/pyproject.toml#L23-L25)
- [main.py:42-49](file://hologres-cli/src/hologres_cli/main.py#L42-L49)

**Section sources**
- [pyproject.toml:16-21](file://hologres-cli/pyproject.toml#L16-L21)
- [pyproject.toml:23-25](file://hologres-cli/pyproject.toml#L23-L25)

## Performance Considerations
- Use --format table or csv for human-readable output when inspecting results quickly.
- Prefer data export/import with COPY protocol for large datasets.
- Limit result sets with LIMIT clauses to avoid large memory usage.
- Use --no-limit-check judiciously for ad-hoc analysis; otherwise, the CLI probes with a small LIMIT to protect against unintentionally large queries.

## Troubleshooting Guide
- Connection errors:
  - Ensure DSN is provided via --dsn, HOLOGRES_DSN, or ~/.hologres/config.env
  - Verify host, port, and database name in the DSN
- Output formats:
  - Use --format json|table|csv|jsonl to switch output styles
- Safety guardrails:
  - Add LIMIT for queries returning >100 rows or use --no-limit-check
  - Write operations are blocked; remove write operations from queries
- Audit logs:
  - Review ~/.hologres/sql-history.jsonl for recent operations and errors
- Exit codes:
  - 0 on success
  - Non-zero on errors (e.g., CONNECTION_ERROR, QUERY_ERROR, LIMIT_REQUIRED, WRITE_BLOCKED)

**Section sources**
- [main.py:98-107](file://hologres-cli/src/hologres_cli/main.py#L98-L107)
- [output.py:125-143](file://hologres-cli/src/hologres_cli/output.py#L125-L143)
- [logger.py:36-73](file://hologres-cli/src/hologres_cli/logger.py#L36-L73)

## Conclusion
The Hologres CLI provides a robust, AI-agent-friendly interface for interacting with Hologres databases. Its global options, consistent output formatting, safety guardrails, and audit logging make it suitable for both interactive use and automation. By understanding parameter precedence, environment variables, and command-specific behaviors, users can integrate the CLI effectively into shell scripts and automated workflows.

## Appendices

### Practical Examples by Category
- Status and instance:
  - Check connection: hologres status
  - Instance info: hologres instance <instance_name>
- Schema inspection:
  - List tables: hologres schema tables
  - Describe table: hologres schema describe <table>
  - Export DDL: hologres schema dump <schema.table>
  - Storage size: hologres schema size <schema.table>
- SQL execution:
  - Read-only query: hologres sql "<SELECT ... LIMIT n>"
  - No limit check: hologres sql --no-limit-check "<SELECT ...>"
  - With schema metadata: hologres sql --with-schema "<SELECT ... LIMIT n>"
- Data operations:
  - Export CSV: hologres data export <table> -f <file.csv>
  - Export with custom query: hologres data export -q "<SELECT ...>" -f <file.csv>
  - Import CSV: hologres data import <table> -f <file.csv>
  - Import with truncate: hologres data import <table> -f <file.csv> --truncate
  - Count rows: hologres data count <table> [--where "..."]
- Compute group:
  - List warehouses: hologres warehouse
  - Query specific: hologres warehouse <warehouse_name>
- Output formats:
  - JSON (default): hologres -f json <command>
  - Table: hologres -f table <command>
  - CSV: hologres -f csv <command>
  - JSON Lines: hologres -f jsonl <command>
- AI agent guide and history:
  - AI guide: hologres ai-guide
  - History: hologres history [-n <count>]

**Section sources**
- [README.md:108-309](file://hologres-cli/README.md#L108-L309)

### Command Chaining and Shell Scripting
- Chain multiple statements in a single sql command using semicolon separation; the CLI executes each statement and aggregates results in JSON mode.
- Use --format table for quick inspection in shell scripts.
- Combine with shell constructs (loops, conditionals) to process outputs programmatically.

**Section sources**
- [sql.py:54-64](file://hologres-cli/src/hologres_cli/commands/sql.py#L54-L64)
- [output.py:23-54](file://hologres-cli/src/hologres_cli/output.py#L23-L54)

### Environment Variables and Configuration
- HOLOGRES_DSN: Primary DSN source
- HOLOGRES_DSN_<instance>: Per-instance DSN for instance command
- ~/.hologres/config.env: File-based configuration with key=value pairs
- Keepalives and connection options can be passed via DSN query parameters

**Section sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [connection.py:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [README.md:89-106](file://hologres-cli/README.md#L89-L106)

### Error Codes and Exit Codes
- Error codes:
  - CONNECTION_ERROR: DSN resolution or connection failure
  - QUERY_ERROR: SQL execution error
  - LIMIT_REQUIRED: SELECT without LIMIT returning >100 rows
  - WRITE_BLOCKED: Write operations attempted
- Exit codes:
  - 0: Success
  - 1: Error (e.g., connection or internal error)

**Section sources**
- [output.py:125-143](file://hologres-cli/src/hologres_cli/output.py#L125-L143)
- [main.py:98-107](file://hologres-cli/src/hologres_cli/main.py#L98-L107)