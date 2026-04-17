# Testing and Development

<cite>
**Referenced Files in This Document**
- [pyproject.toml](file://hologres-cli/pyproject.toml)
- [README.md](file://hologres-cli/README.md)
- [conftest.py](file://hologres-cli/tests/conftest.py)
- [integration/conftest.py](file://hologres-cli/tests/integration/conftest.py)
- [test_masking.py](file://hologres-cli/tests/test_masking.py)
- [test_connection.py](file://hologres-cli/tests/test_connection.py)
- [test_output.py](file://hologres-cli/tests/test_output.py)
- [test_logger.py](file://hologres-cli/tests/test_logger.py)
- [test_main.py](file://hologres-cli/tests/test_main.py)
- [test_connection_live.py](file://hologres-cli/tests/integration/test_connection_live.py)
- [test_data_live.py](file://hologres-cli/tests/integration/test_data_live.py)
- [test_sql_live.py](file://hologres-cli/tests/integration/test_sql_live.py)
- [test_output_format_live.py](file://hologres-cli/tests/integration/test_output_format_live.py)
- [main.py](file://hologres-cli/src/hologres_cli/main.py)
- [connection.py](file://hologres-cli/src/hologres_cli/connection.py)
- [masking.py](file://hologres-cli/src/hologres_cli/masking.py)
- [output.py](file://hologres-cli/src/hologres_cli/output.py)
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
This document describes the testing and development practices for the Hologres CLI project. It covers:
- Test strategy: unit tests (pytest -m unit) and integration tests (pytest -m integration) with database requirements
- Test environment setup: HOLOGRES_TEST_DSN configuration and test data requirements
- Development workflow: installation with dev dependencies, running coverage reports, and test execution patterns
- Test structure and organization: unit tests for individual components and integration tests for end-to-end functionality
- Contribution guidelines, code quality standards, and best practices for extending the CLI tool
- Guidance on adding new commands, safety features, and output formats

## Project Structure
The repository is organized into:
- A Python package under src/hologres_cli implementing the CLI and core logic
- A comprehensive test suite under tests with two categories:
  - Unit tests under tests/ for isolated component testing
  - Integration tests under tests/integration/ for end-to-end scenarios against a real database
- Tooling configuration for pytest and coverage reporting

```mermaid
graph TB
subgraph "Package"
SRC_MAIN["src/hologres_cli/main.py"]
SRC_CONN["src/hologres_cli/connection.py"]
SRC_MASK["src/hologres_cli/masking.py"]
SRC_OUT["src/hologres_cli/output.py"]
end
subgraph "Unit Tests"
T_MASK["tests/test_masking.py"]
T_CONN["tests/test_connection.py"]
T_OUT["tests/test_output.py"]
T_LOG["tests/test_logger.py"]
T_MAIN["tests/test_main.py"]
U_FIXTURES["tests/conftest.py"]
end
subgraph "Integration Tests"
IT_CONN["tests/integration/test_connection_live.py"]
IT_DATA["tests/integration/test_data_live.py"]
IT_SQL["tests/integration/test_sql_live.py"]
IT_FMT["tests/integration/test_output_format_live.py"]
IT_FIXTURES["tests/integration/conftest.py"]
end
SRC_MAIN --> SRC_CONN
SRC_MAIN --> SRC_MASK
SRC_MAIN --> SRC_OUT
T_MASK --> SRC_MASK
T_CONN --> SRC_CONN
T_OUT --> SRC_OUT
T_LOG --> SRC_MAIN
IT_CONN --> SRC_CONN
IT_DATA --> SRC_MAIN
IT_SQL --> SRC_MAIN
IT_FMT --> SRC_OUT
```

**Diagram sources**
- [main.py:1-111](file://hologres-cli/src/hologres_cli/main.py#L1-L111)
- [connection.py:1-229](file://hologres-cli/src/hologres_cli/connection.py#L1-L229)
- [masking.py:1-93](file://hologres-cli/src/hologres_cli/masking.py#L1-L93)
- [output.py:1-143](file://hologres-cli/src/hologres_cli/output.py#L1-L143)
- [test_masking.py:1-455](file://hologres-cli/tests/test_masking.py#L1-L455)
- [test_connection.py:1-385](file://hologres-cli/tests/test_connection.py#L1-L385)
- [test_output.py:1-355](file://hologres-cli/tests/test_output.py#L1-L355)
- [test_logger.py:1-382](file://hologres-cli/tests/test_logger.py#L1-L382)
- [test_main.py:1-195](file://hologres-cli/tests/test_main.py#L1-L195)
- [test_connection_live.py:1-148](file://hologres-cli/tests/integration/test_connection_live.py#L1-L148)
- [test_data_live.py:1-203](file://hologres-cli/tests/integration/test_data_live.py#L1-L203)
- [test_sql_live.py:1-324](file://hologres-cli/tests/integration/test_sql_live.py#L1-L324)
- [test_output_format_live.py:1-80](file://hologres-cli/tests/integration/test_output_format_live.py#L1-L80)

**Section sources**
- [pyproject.toml:1-68](file://hologres-cli/pyproject.toml#L1-L68)
- [README.md:1-314](file://hologres-cli/README.md#L1-L314)

## Core Components
This section outlines the core components relevant to testing and development.

- CLI entrypoint and commands
  - The CLI groups commands and exposes global options for DSN and output format. It registers subcommands for schema, sql, data, status, instance, and warehouse.
  - The main entrypoint wraps the CLI and handles DSN and internal errors, returning structured JSON responses.

- Connection management
  - Provides DSN resolution from CLI flag, environment variable, or config file.
  - Parses DSN into connection parameters, supports multiple schemes, and validates required parts.
  - Wraps psycopg3 connections with lazy initialization, reconnection on closed connections, and context manager support.

- Output formatting
  - Unified response structure with ok/data or ok/error.
  - Supports JSON, table, CSV, and JSONL output formats.
  - Includes helpers for common error codes and printing.

- Sensitive data masking
  - Masks phone, email, password, ID card, and bank card fields based on column name patterns.
  - Applies masking to rows returned by queries.

- Audit logging
  - Redacts sensitive data from SQL logs and writes JSONL entries to a user directory.

**Section sources**
- [main.py:1-111](file://hologres-cli/src/hologres_cli/main.py#L1-L111)
- [connection.py:1-229](file://hologres-cli/src/hologres_cli/connection.py#L1-L229)
- [output.py:1-143](file://hologres-cli/src/hologres_cli/output.py#L1-L143)
- [masking.py:1-93](file://hologres-cli/src/hologres_cli/masking.py#L1-L93)
- [test_main.py:1-195](file://hologres-cli/tests/test_main.py#L1-L195)
- [test_connection.py:1-385](file://hologres-cli/tests/test_connection.py#L1-L385)
- [test_output.py:1-355](file://hologres-cli/tests/test_output.py#L1-L355)
- [test_masking.py:1-455](file://hologres-cli/tests/test_masking.py#L1-L455)
- [test_logger.py:1-382](file://hologres-cli/tests/test_logger.py#L1-L382)

## Architecture Overview
The testing architecture separates concerns into unit and integration layers:
- Unit tests rely on mocks for database connectivity and focus on pure logic, formatting, and CLI behavior.
- Integration tests require a real Hologres database and validate end-to-end flows, including transactions, output formats, and safety guardrails.

```mermaid
graph TB
subgraph "Unit Layer"
U_CONN["Unit: connection.py"]
U_MASK["Unit: masking.py"]
U_OUT["Unit: output.py"]
U_MAIN["Unit: main.py"]
U_FIX["Unit Fixtures<br/>tests/conftest.py"]
end
subgraph "Integration Layer"
I_CONN["Integration: connection_live.py"]
I_SQL["Integration: sql_live.py"]
I_DATA["Integration: data_live.py"]
I_FMT["Integration: output_format_live.py"]
I_FIX["Integration Fixtures<br/>tests/integration/conftest.py"]
DB["Real Hologres Database"]
end
U_FIX --> U_CONN
U_FIX --> U_MASK
U_FIX --> U_OUT
U_FIX --> U_MAIN
I_FIX --> I_CONN
I_FIX --> I_SQL
I_FIX --> I_DATA
I_FIX --> I_FMT
I_CONN --> DB
I_SQL --> DB
I_DATA --> DB
I_FMT --> DB
```

**Diagram sources**
- [test_connection.py:1-385](file://hologres-cli/tests/test_connection.py#L1-L385)
- [test_masking.py:1-455](file://hologres-cli/tests/test_masking.py#L1-L455)
- [test_output.py:1-355](file://hologres-cli/tests/test_output.py#L1-L355)
- [test_main.py:1-195](file://hologres-cli/tests/test_main.py#L1-L195)
- [conftest.py:1-174](file://hologres-cli/tests/conftest.py#L1-L174)
- [test_connection_live.py:1-148](file://hologres-cli/tests/integration/test_connection_live.py#L1-L148)
- [test_sql_live.py:1-324](file://hologres-cli/tests/integration/test_sql_live.py#L1-L324)
- [test_data_live.py:1-203](file://hologres-cli/tests/integration/test_data_live.py#L1-L203)
- [test_output_format_live.py:1-80](file://hologres-cli/tests/integration/test_output_format_live.py#L1-L80)
- [integration/conftest.py:1-98](file://hologres-cli/tests/integration/conftest.py#L1-L98)

## Detailed Component Analysis

### Unit Tests: Connection and DSN Resolution
- Purpose: Validate DSN parsing, masking, and connection behavior without touching a database.
- Key fixtures: Mock environment variables, temporary config files, and mocked psycopg connections/cursors.
- Coverage areas:
  - DSN parsing with various schemes and parameters
  - Masking of DSN passwords
  - Config file reading and precedence
  - Lazy connection creation and reconnection semantics
  - Context manager usage and cursor execution

```mermaid
sequenceDiagram
participant Test as "Unit Test"
participant Conn as "HologresConnection"
participant Psycopg as "Mocked psycopg.connect"
Test->>Conn : Initialize with DSN
Test->>Conn : Access conn property
Conn->>Psycopg : connect(**parsed_params)
Psycopg-->>Conn : Connection object
Test->>Conn : execute(sql, params)
Conn->>Psycopg : cursor().execute(sql, params)
Psycopg-->>Conn : fetchall() or none
Conn-->>Test : Rows or empty list
```

**Diagram sources**
- [test_connection.py:264-361](file://hologres-cli/tests/test_connection.py#L264-L361)
- [connection.py:178-223](file://hologres-cli/src/hologres_cli/connection.py#L178-L223)
- [conftest.py:60-88](file://hologres-cli/tests/conftest.py#L60-L88)

**Section sources**
- [test_connection.py:1-385](file://hologres-cli/tests/test_connection.py#L1-L385)
- [connection.py:1-229](file://hologres-cli/src/hologres_cli/connection.py#L1-L229)
- [conftest.py:1-174](file://hologres-cli/tests/conftest.py#L1-L174)

### Unit Tests: Output Formatting and Error Helpers
- Purpose: Validate unified response formatting across JSON, table, CSV, and JSONL.
- Coverage areas:
  - success and success_rows formatting
  - error helpers and specific guards
  - table, CSV, and JSONL rendering
  - CLI-level format option propagation

```mermaid
flowchart TD
Start(["Call success/success_rows"]) --> ChooseFmt{"Format?"}
ChooseFmt --> |JSON| JsonResp["Build JSON response"]
ChooseFmt --> |TABLE| TableFmt["Render table"]
ChooseFmt --> |CSV| CsvFmt["Render CSV"]
ChooseFmt --> |JSONL| JsonlFmt["Render JSONL"]
JsonResp --> End(["Return string"])
TableFmt --> End
CsvFmt --> End
JsonlFmt --> End
```

**Diagram sources**
- [test_output.py:29-141](file://hologres-cli/tests/test_output.py#L29-L141)
- [output.py:23-117](file://hologres-cli/src/hologres_cli/output.py#L23-L117)

**Section sources**
- [test_output.py:1-355](file://hologres-cli/tests/test_output.py#L1-L355)
- [output.py:1-143](file://hologres-cli/src/hologres_cli/output.py#L1-L143)

### Unit Tests: Sensitive Data Masking
- Purpose: Validate masking logic for phone, email, password, ID card, and bank card fields.
- Coverage areas:
  - Pattern matching by column name
  - Masking functions behavior with various inputs
  - Row-level masking preserving non-sensitive fields

```mermaid
flowchart TD
Rows["Input rows"] --> Detect["Detect sensitive columns"]
Detect --> Apply["Apply mask function per column"]
Apply --> Result["Return masked rows"]
```

**Diagram sources**
- [test_masking.py:355-455](file://hologres-cli/tests/test_masking.py#L355-L455)
- [masking.py:66-93](file://hologres-cli/src/hologres_cli/masking.py#L66-L93)

**Section sources**
- [test_masking.py:1-455](file://hologres-cli/tests/test_masking.py#L1-L455)
- [masking.py:1-93](file://hologres-cli/src/hologres_cli/masking.py#L1-L93)

### Unit Tests: Logger and Audit Logging
- Purpose: Validate SQL redaction, log rotation, and reading recent logs.
- Coverage areas:
  - Redaction of sensitive patterns in SQL
  - Log directory creation and rotation
  - Reading recent entries with error handling

**Section sources**
- [test_logger.py:1-382](file://hologres-cli/tests/test_logger.py#L1-L382)

### Integration Tests: Real Database Connectivity
- Purpose: Validate real database connectivity, query execution, and error handling.
- Coverage areas:
  - Establishing connections and executing SELECT statements
  - Parameterized queries and context manager usage
  - Masked DSN behavior and connection lifecycle

**Section sources**
- [test_connection_live.py:1-148](file://hologres-cli/tests/integration/test_connection_live.py#L1-L148)
- [integration/conftest.py:21-50](file://hologres-cli/tests/integration/conftest.py#L21-L50)

### Integration Tests: SQL Command and Safety Guardrails
- Purpose: Validate SQL execution, transactions, safety checks, and output formats.
- Coverage areas:
  - SELECT, INSERT, UPDATE, DELETE operations
  - Transaction commit/rollback semantics
  - Safety guardrails: write guard, dangerous write blocking, row limit enforcement
  - Output formats: CSV, JSONL, table

```mermaid
sequenceDiagram
participant CLI as "CLI"
participant Conn as "HologresConnection"
participant DB as "Hologres Database"
CLI->>Conn : execute(sql, params)
Conn->>DB : cursor().execute(sql, params)
DB-->>Conn : rows or affected rows
Conn-->>CLI : rows[]
CLI-->>CLI : apply masking / format output
CLI-->>CLI : enforce safety rules
```

**Diagram sources**
- [test_sql_live.py:165-324](file://hologres-cli/tests/integration/test_sql_live.py#L165-L324)
- [connection.py:199-211](file://hologres-cli/src/hologres_cli/connection.py#L199-L211)

**Section sources**
- [test_sql_live.py:1-324](file://hologres-cli/tests/integration/test_sql_live.py#L1-L324)

### Integration Tests: Data Import/Export and Round-Trip
- Purpose: Validate CSV export/import and round-trip integrity.
- Coverage areas:
  - Export table/query to CSV
  - Import CSV into table with optional truncate
  - Count rows and verify round-trip data integrity

**Section sources**
- [test_data_live.py:1-203](file://hologres-cli/tests/integration/test_data_live.py#L1-L203)

### Integration Tests: Output Format Variants
- Purpose: Validate consistent output across commands and formats.
- Coverage areas:
  - SQL query outputs in CSV and JSONL
  - Data count outputs in CSV
  - Schema tables outputs in JSONL

**Section sources**
- [test_output_format_live.py:1-80](file://hologres-cli/tests/integration/test_output_format_live.py#L1-L80)

## Dependency Analysis
The CLI depends on:
- Click for CLI framework
- psycopg3 for database connectivity
- tabulate for table formatting

Tooling dependencies:
- pytest for test execution and markers
- pytest-cov for coverage reporting
- pytest-mock for mocking

```mermaid
graph LR
PY["pyproject.toml"]
MAIN["main.py"]
CONN["connection.py"]
MASK["masking.py"]
OUT["output.py"]
PY --> MAIN
PY --> CONN
PY --> MASK
PY --> OUT
MAIN --> CONN
MAIN --> OUT
MAIN --> MASK
```

**Diagram sources**
- [pyproject.toml:1-68](file://hologres-cli/pyproject.toml#L1-L68)
- [main.py:1-111](file://hologres-cli/src/hologres_cli/main.py#L1-L111)
- [connection.py:1-229](file://hologres-cli/src/hologres_cli/connection.py#L1-L229)
- [masking.py:1-93](file://hologres-cli/src/hologres_cli/masking.py#L1-L93)
- [output.py:1-143](file://hologres-cli/src/hologres_cli/output.py#L1-L143)

**Section sources**
- [pyproject.toml:1-68](file://hologres-cli/pyproject.toml#L1-L68)

## Performance Considerations
- Unit tests are fast and deterministic, relying on mocks to avoid network latency.
- Integration tests require a real database and may be slower; use selective markers (-m unit or -m integration) to reduce runtime.
- Coverage thresholds are enforced to maintain high code coverage.

## Troubleshooting Guide
Common issues and resolutions:
- Missing HOLOGRES_TEST_DSN
  - Integration tests automatically skip when the environment variable is not set. Set HOLOGRES_TEST_DSN to enable them.
- DSN configuration precedence
  - CLI flag overrides environment variable, which overrides config file. Ensure the intended source is set.
- Connection failures
  - Verify DSN format and reachability. The CLI catches DSN errors and returns structured error responses.
- Safety guardrail violations
  - Write operations require --write; dangerous operations (e.g., DELETE/UPDATE without WHERE) are blocked.
- Output format mismatches
  - Ensure the chosen format matches the command’s capabilities and that the output is parsed correctly.

**Section sources**
- [integration/conftest.py:21-31](file://hologres-cli/tests/integration/conftest.py#L21-L31)
- [test_connection.py:216-262](file://hologres-cli/tests/test_connection.py#L216-L262)
- [test_sql_live.py:238-324](file://hologres-cli/tests/integration/test_sql_live.py#L238-L324)
- [README.md:38-87](file://hologres-cli/README.md#L38-L87)

## Conclusion
The Hologres CLI employs a robust dual-layer testing strategy:
- Unit tests validate logic, formatting, and CLI behavior using mocks
- Integration tests validate end-to-end functionality against a real database, ensuring safety guardrails and output correctness

Development follows clear patterns: install with dev dependencies, run targeted tests with markers, and maintain high coverage. Extending the CLI involves adding new commands, integrating safety features, and supporting additional output formats while adhering to the established patterns.

## Appendices

### Test Execution Patterns
- Run unit tests only (fast, no database required)
  - pytest -m unit
- Run integration tests only (requires database)
  - pytest -m integration
- Run all tests with coverage
  - pytest --cov=src/hologres_cli --cov-report=term-missing
- Specific test files
  - pytest tests/test_masking.py
  - pytest tests/test_commands/test_sql.py

**Section sources**
- [README.md:38-87](file://hologres-cli/README.md#L38-L87)
- [pyproject.toml:34-47](file://hologres-cli/pyproject.toml#L34-L47)

### Test Environment Setup
- HOLOGRES_TEST_DSN
  - Required for integration tests. Example: export HOLOGRES_TEST_DSN="hologres://user:password@host:port/database"
  - Integration fixtures will skip tests if unset.
- Temporary test resources
  - Integration fixtures create temporary tables and manage cleanup automatically.

**Section sources**
- [integration/conftest.py:21-98](file://hologres-cli/tests/integration/conftest.py#L21-L98)

### Development Workflow
- Install with dev dependencies
  - pip install -e ".[dev]"
- Run coverage
  - pytest --cov=src/hologres_cli --cov-report=term-missing
- Use markers to filter tests
  - pytest -m unit or pytest -m integration

**Section sources**
- [README.md:30-37](file://hologres-cli/README.md#L30-L37)
- [pyproject.toml:16-47](file://hologres-cli/pyproject.toml#L16-L47)

### Adding New Commands
- Follow the established pattern:
  - Define a new command module under src/hologres_cli/commands/
  - Register the command in main.py
  - Add unit tests under tests/test_commands/
  - Add integration tests under tests/integration/ with appropriate fixtures
- Ensure safety guardrails and output formatting are consistent with existing commands.

**Section sources**
- [main.py:42-49](file://hologres-cli/src/hologres_cli/main.py#L42-L49)
- [test_main.py:152-195](file://hologres-cli/tests/test_main.py#L152-L195)

### Extending Safety Features and Output Formats
- Safety features
  - Enforce row limits, write protections, and dangerous operation blocking consistently across commands.
  - Use error helpers for standardized error responses.
- Output formats
  - Extend output.py to support new formats if needed, and update tests to validate rendering.

**Section sources**
- [output.py:120-143](file://hologres-cli/src/hologres_cli/output.py#L120-L143)
- [test_output.py:1-355](file://hologres-cli/tests/test_output.py#L1-L355)