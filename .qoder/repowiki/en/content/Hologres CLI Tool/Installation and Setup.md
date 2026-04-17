# Installation and Setup

<cite>
**Referenced Files in This Document**
- [README.md](file://hologres-cli/README.md)
- [pyproject.toml](file://hologres-cli/pyproject.toml)
- [main.py](file://hologres-cli/src/hologres_cli/main.py)
- [connection.py](file://hologres-cli/src/hologres_cli/connection.py)
- [status.py](file://hologres-cli/src/hologres_cli/commands/status.py)
- [output.py](file://hologres-cli/src/hologres_cli/output.py)
- [logger.py](file://hologres-cli/src/hologres_cli/logger.py)
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
This document provides comprehensive installation and setup instructions for the Hologres CLI tool. It covers Python version requirements, dependency installation via pip, DSN configuration through command-line flags, environment variables, and configuration files, along with a step-by-step initial setup guide and verification commands. It also addresses common installation issues and troubleshooting steps, and includes examples of DSN formats for various deployment scenarios.

## Project Structure
The Hologres CLI is organized as a Python package with a console script entry point. The CLI exposes commands for status checks, schema inspection, SQL execution, data import/export, and history viewing. Configuration is resolved from multiple sources with a defined priority order.

```mermaid
graph TB
subgraph "Package"
A["hologres_cli.main<br/>Console script entry point"]
B["hologres_cli.connection<br/>DSN resolution and connection management"]
C["hologres_cli.output<br/>Output formatting (JSON, table, CSV, JSONL)"]
D["hologres_cli.logger<br/>Audit logging to ~/.hologres/sql-history.jsonl"]
E["hologres_cli.commands.*<br/>Command implementations"]
end
A --> B
A --> C
A --> E
B --> D
E --> B
E --> C
```

**Diagram sources**
- [main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [connection.py:17-26](file://hologres-cli/src/hologres_cli/connection.py#L17-L26)
- [output.py:16-20](file://hologres-cli/src/hologres_cli/output.py#L16-L20)
- [logger.py:11-12](file://hologres-cli/src/hologres_cli/logger.py#L11-L12)

**Section sources**
- [main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [pyproject.toml:23-25](file://hologres-cli/pyproject.toml#L23-L25)

## Core Components
- Console script entry point: The CLI is exposed via the console script name defined in the project metadata.
- DSN resolution: The CLI resolves the DSN from three sources in priority order: command-line flag, environment variable, and configuration file.
- Connection management: The CLI wraps a PostgreSQL-compatible connection with safe defaults and keepalive settings.
- Output formatting: The CLI supports multiple output formats (JSON, table, CSV, JSONL) consistently across commands.
- Audit logging: All operations are logged to a JSON Lines file under the user’s home directory.

**Section sources**
- [pyproject.toml:23-25](file://hologres-cli/pyproject.toml#L23-L25)
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [output.py:16-20](file://hologres-cli/src/hologres_cli/output.py#L16-L20)
- [logger.py:11-12](file://hologres-cli/src/hologres_cli/logger.py#L11-L12)

## Architecture Overview
The CLI follows a layered architecture:
- Command layer: Click-based commands define the CLI surface.
- Configuration layer: DSN resolution and environment handling.
- Connection layer: A thin wrapper around the underlying database driver.
- Output layer: Unified formatting for consistent user experience.
- Logging layer: Persistent audit trail of operations.

```mermaid
graph TB
subgraph "CLI Layer"
CLI["Click CLI group"]
end
subgraph "Configuration Layer"
RES["resolve_raw_dsn()<br/>Priority: CLI flag -> Env var -> Config file"]
end
subgraph "Connection Layer"
CONN["HologresConnection<br/>psycopg3 wrapper"]
end
subgraph "Output Layer"
OUT["print_output()<br/>format selection"]
end
subgraph "Logging Layer"
LOG["log_operation()<br/>~/.hologres/sql-history.jsonl"]
end
CLI --> RES
CLI --> OUT
CLI --> LOG
RES --> CONN
CLI --> CONN
```

**Diagram sources**
- [main.py:15-49](file://hologres-cli/src/hologres_cli/main.py#L15-L49)
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [output.py:120-122](file://hologres-cli/src/hologres_cli/output.py#L120-L122)
- [logger.py:36-73](file://hologres-cli/src/hologres_cli/logger.py#L36-L73)

## Detailed Component Analysis

### Installation and Dependencies
- Python requirement: Python 3.11 or newer.
- Core dependencies: Click, psycopg with binary support, and tabulate.
- Optional development dependencies: pytest, pytest-cov, pytest-mock.
- Installation methods:
  - Editable install with pip.
  - Using uv to create a virtual environment and install.
  - Development install with dev dependencies.

Verification steps:
- Confirm Python version meets the requirement.
- Install the package in editable mode.
- Optionally install dev dependencies for testing.

**Section sources**
- [README.md:13-36](file://hologres-cli/README.md#L13-L36)
- [pyproject.toml:5-10](file://hologres-cli/pyproject.toml#L5-L10)
- [pyproject.toml:16-21](file://hologres-cli/pyproject.toml#L16-L21)

### DSN Configuration
The CLI supports three configuration methods with the following priority:
1. Command-line flag: --dsn
2. Environment variable: HOLOGRES_DSN
3. Configuration file: ~/.hologres/config.env

DSN format:
- hologres://[user[:password]@]host[:port]/database[?options]

Additional instance-specific DSNs:
- Named instances can be configured via HOLOGRES_DSN_<instance_name> in environment or config file.

Configuration resolution flow:
```mermaid
flowchart TD
Start(["Resolve DSN"]) --> CheckFlag["CLI --dsn provided?"]
CheckFlag --> |Yes| UseFlag["Use CLI flag"]
CheckFlag --> |No| CheckEnv["HOLOGRES_DSN env var?"]
CheckEnv --> |Yes| UseEnv["Use environment variable"]
CheckEnv --> |No| CheckFile["~/.hologres/config.env exists?"]
CheckFile --> |Yes| ReadFile["Read HOLOGRES_DSN from file"]
ReadFile --> Found{"Value found?"}
Found --> |Yes| UseFile["Use file value"]
Found --> |No| RaiseError["Raise DSNError with guidance"]
CheckFile --> |No| RaiseError
UseFlag --> End(["Resolved"])
UseEnv --> End
UseFile --> End
RaiseError --> End
```

**Diagram sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [connection.py:67-86](file://hologres-cli/src/hologres_cli/connection.py#L67-L86)

**Section sources**
- [README.md:89-106](file://hologres-cli/README.md#L89-L106)
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [connection.py:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)

### First-Time Setup Workflow
Step-by-step guide:
1. Install Python 3.11+.
2. Install the CLI in editable mode.
3. Choose a DSN configuration method:
   - Option A: Pass DSN via --dsn flag for a single command.
   - Option B: Set HOLOGRES_DSN environment variable for the current session.
   - Option C: Create ~/.hologres/config.env and add HOLOGRES_DSN.
4. Verify the setup:
   - Run a status check to confirm connectivity.
   - Try a simple schema or SQL command to validate output formatting.

Verification commands:
- Check connection status.
- List tables in a chosen output format.
- Execute a simple read-only query with a LIMIT clause.

**Section sources**
- [README.md:13-36](file://hologres-cli/README.md#L13-L36)
- [README.md:110-115](file://hologres-cli/README.md#L110-L115)
- [README.md:134-151](file://hologres-cli/README.md#L134-L151)
- [README.md:200-209](file://hologres-cli/README.md#L200-L209)

### Output Formatting
The CLI supports multiple output formats:
- json (default)
- table
- csv
- jsonl

Commands consistently honor the selected format, and the status command demonstrates the unified response structure.

**Section sources**
- [output.py:16-20](file://hologres-cli/src/hologres_cli/output.py#L16-L20)
- [README.md:200-209](file://hologres-cli/README.md#L200-L209)
- [status.py:45-54](file://hologres-cli/src/hologres_cli/commands/status.py#L45-L54)

### Audit Logging
All operations are logged to ~/.hologres/sql-history.jsonl with redaction of sensitive literals. The logger rotates the log file when it exceeds a maximum size and provides functions to read recent entries.

**Section sources**
- [logger.py:11-12](file://hologres-cli/src/hologres_cli/logger.py#L11-L12)
- [logger.py:36-73](file://hologres-cli/src/hologres_cli/logger.py#L36-L73)
- [logger.py:89-104](file://hologres-cli/src/hologres_cli/logger.py#L89-L104)

## Dependency Analysis
The CLI depends on:
- Click for command-line interface.
- psycopg (with binary support) for PostgreSQL-compatible connectivity.
- tabulate for human-readable table output.

Optional development dependencies enable testing and coverage reporting.

```mermaid
graph TB
P["pyproject.toml"]
D1["click"]
D2["psycopg[binary]"]
D3["tabulate"]
DEV["pytest, pytest-cov, pytest-mock"]
P --> D1
P --> D2
P --> D3
P --> DEV
```

**Diagram sources**
- [pyproject.toml:5-10](file://hologres-cli/pyproject.toml#L5-L10)
- [pyproject.toml:16-21](file://hologres-cli/pyproject.toml#L16-L21)

**Section sources**
- [pyproject.toml:5-10](file://hologres-cli/pyproject.toml#L5-L10)
- [pyproject.toml:16-21](file://hologres-cli/pyproject.toml#L16-L21)

## Performance Considerations
- Connection reuse: The connection wrapper maintains a single connection per command invocation and closes it afterward.
- Keepalive settings: Default keepalive parameters are applied to reduce idle connection issues.
- Output formatting overhead: Table and CSV formatting rely on external libraries; JSON is native and generally fastest.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common installation and configuration issues:
- Python version mismatch: Ensure Python 3.11+ is installed.
- Missing dependencies: Install the package with dev dependencies for testing or the minimal dependencies for runtime.
- DSN not configured: The CLI raises a DSNError with guidance when no DSN is found. Provide a DSN via --dsn, HOLOGRES_DSN, or ~/.hologres/config.env.
- Invalid DSN format: The CLI validates the DSN scheme and required components (hostname, database). Ensure the DSN starts with the correct scheme and includes host and database.
- Connection failures: Verify network reachability, credentials, and port settings. Use the status command to diagnose connectivity.
- Output format issues: Confirm the selected format is one of the supported formats.

**Section sources**
- [README.md:13-36](file://hologres-cli/README.md#L13-L36)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [output.py:16-20](file://hologres-cli/src/hologres_cli/output.py#L16-L20)

## Conclusion
The Hologres CLI provides a robust, configurable, and secure interface for interacting with Hologres databases. By following the installation and setup steps outlined here, configuring DSN through your preferred method, and verifying connectivity with the provided commands, you can quickly become productive with the CLI. Use the troubleshooting section to resolve common issues, and leverage the audit logging and output formatting capabilities to streamline your workflows.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### A. DSN Format Examples
- Standard format: hologres://[user[:password]@]host[:port]/database
- With options: hologres://user:pass@host:port/db?option1=value1&option2=value2
- Environment variable: export HOLOGRES_DSN="hologres://user:pass@host:port/db"
- Configuration file example: Add HOLOGRES_DSN="hologres://user:pass@host:port/db" to ~/.hologres/config.env

**Section sources**
- [README.md:91-95](file://hologres-cli/README.md#L91-L95)
- [README.md:97-106](file://hologres-cli/README.md#L97-L106)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)

### B. Verification Commands
- Check connection status: hologres status
- List tables in table format: hologres -f table schema tables
- Query with JSON output: hologres sql "SELECT * FROM orders WHERE status='pending' LIMIT 20"
- Check warehouse info: hologres warehouse
- View command history: hologres history

**Section sources**
- [README.md:110-115](file://hologres-cli/README.md#L110-L115)
- [README.md:134-151](file://hologres-cli/README.md#L134-L151)
- [README.md:185-191](file://hologres-cli/README.md#L185-L191)
- [README.md:289-309](file://hologres-cli/README.md#L289-L309)