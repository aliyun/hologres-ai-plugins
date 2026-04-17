# Connection Management API

<cite>
**Referenced Files in This Document**
- [connection.py](file://hologres-cli/src/hologres_cli/connection.py)
- [main.py](file://hologres-cli/src/hologres_cli/main.py)
- [sql.py](file://hologres-cli/src/hologres_cli/commands/sql.py)
- [status.py](file://hologres-cli/src/hologres_cli/commands/status.py)
- [logger.py](file://hologres-cli/src/hologres_cli/logger.py)
- [output.py](file://hologres-cli/src/hologres_cli/output.py)
- [pyproject.toml](file://hologres-cli/pyproject.toml)
- [README.md](file://hologres-cli/README.md)
- [test_connection.py](file://hologres-cli/tests/test_connection.py)
- [test_connection_live.py](file://hologres-cli/tests/integration/test_connection_live.py)
- [conftest.py](file://hologres-cli/tests/conftest.py)
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
This document describes the Connection Management API for the Hologres CLI tool. It explains how the CLI resolves Data Source Names (DSNs), constructs connection parameters, and manages connections. It also documents supported DSN formats, environment variables, configuration file parsing, connection lifecycle, and error handling. Security features such as password masking and audit logging are covered, along with practical examples and production best practices.

## Project Structure
The connection management logic resides primarily in the connection module and is consumed by CLI commands. The main entry point integrates DSN configuration from flags and environment variables. Commands use the connection layer to execute queries safely and log operations.

```mermaid
graph TB
CLI["CLI Entry Point<br/>main.py"] --> ConnMgr["Connection Manager<br/>connection.py"]
ConnMgr --> Psycopg["psycopg3 Driver"]
CLI --> CmdSQL["Command: SQL<br/>sql.py"]
CLI --> CmdStatus["Command: Status<br/>status.py"]
CmdSQL --> ConnMgr
CmdStatus --> ConnMgr
Logger["Audit Logger<br/>logger.py"] --> CmdSQL
Logger --> CmdStatus
```

**Diagram sources**
- [main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)
- [sql.py:34-64](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L64)
- [status.py:14-33](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L33)
- [logger.py:36-74](file://hologres-cli/src/hologres_cli/logger.py#L36-L74)

**Section sources**
- [main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

## Core Components
- DSN Resolution: Priority-based resolution from CLI flag, environment variable, or config file.
- DSN Parsing: Validates scheme, extracts host/port/database/user/password, applies defaults, and parses query parameters.
- Connection Wrapper: Lazy connection creation, automatic autocommit, cursor factory, and safe execution helpers.
- Password Masking: Safe logging by masking passwords in DSNs.
- Error Types: Dedicated exceptions for DSN parsing and connection errors.

Key APIs and behaviors:
- DSN resolution and parsing: [resolve_raw_dsn:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64), [parse_dsn:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- Named instance lookup: [resolve_instance_dsn:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)
- Connection wrapper: [HologresConnection:178-223](file://hologres-cli/src/hologres_cli/connection.py#L178-L223)
- Connection acquisition: [get_connection:225-229](file://hologres-cli/src/hologres_cli/connection.py#L225-L229)
- Password masking: [mask_dsn_password:173-176](file://hologres-cli/src/hologres_cli/connection.py#L173-L176)

**Section sources**
- [connection.py:39-176](file://hologres-cli/src/hologres_cli/connection.py#L39-L176)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

## Architecture Overview
The CLI supports three DSN sources with explicit precedence. The DSN is normalized and parsed into connection parameters. Connections are lazily created via a wrapper that sets defaults and exposes convenience methods.

```mermaid
sequenceDiagram
participant User as "User"
participant CLI as "CLI (main.py)"
participant Conn as "Connection Manager (connection.py)"
participant DB as "Database"
User->>CLI : Invoke command with optional --dsn
CLI->>Conn : get_connection(dsn)
alt DSN provided
Conn->>Conn : resolve_raw_dsn(dsn)
else No DSN provided
Conn->>Conn : resolve_raw_dsn(None)
Conn->>Conn : resolve from HOLOGRES_DSN env
Conn->>Conn : resolve from ~/.hologres/config.env
end
Conn->>Conn : parse_dsn(normalized)
Conn->>DB : psycopg.connect(**params)
DB-->>Conn : Connection handle
Conn-->>CLI : HologresConnection
CLI->>Conn : execute()/cursor()
Conn-->>CLI : Results
CLI-->>User : Formatted output
```

**Diagram sources**
- [main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)
- [connection.py:39-170](file://hologres-cli/src/hologres_cli/connection.py#L39-L170)
- [connection.py:225-229](file://hologres-cli/src/hologres_cli/connection.py#L225-L229)

## Detailed Component Analysis

### DSN Resolution Mechanisms
- Supported formats:
  - Primary: hologres://[user[:password]@]host[:port]/database[?options]
  - Aliases: postgresql:// and postgres:// are accepted and normalized internally.
- Resolution priority:
  1) CLI --dsn flag
  2) HOLOGRES_DSN environment variable
  3) ~/.hologres/config.env with key HOLOGRES_DSN
- Named instance DSNs:
  - Lookup HOLOGRES_DSN_<instance_name> from environment or config file.
- Query parameters:
  - connect_timeout: passed through to driver.
  - options: passed through to driver.
  - keepalives family: keepalives, keepalives_idle, keepalives_interval, keepalives_count; integers validated and applied as defaults if unspecified.

```mermaid
flowchart TD
Start(["resolve_raw_dsn(dsn)"]) --> CheckFlag{"Explicit DSN provided?"}
CheckFlag --> |Yes| ReturnFlag["Return flag DSN"]
CheckFlag --> |No| CheckEnv["Read HOLOGRES_DSN"]
CheckEnv --> EnvFound{"Found?"}
EnvFound --> |Yes| ReturnEnv["Return env DSN"]
EnvFound --> |No| CheckFile["Read ~/.hologres/config.env"]
CheckFile --> FileFound{"HOLOGRES_DSN found?"}
FileFound --> |Yes| ReturnFile["Return file DSN"]
FileFound --> |No| RaiseErr["Raise DSNError with guidance"]
```

**Diagram sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)

**Section sources**
- [connection.py:39-117](file://hologres-cli/src/hologres_cli/connection.py#L39-L117)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [README.md:91-106](file://hologres-cli/README.md#L91-L106)

### DSN Parsing Details
- Scheme normalization: hologres:// becomes postgresql:// for internal parsing.
- Required components:
  - Hostname must be present.
  - Database path must be present and non-root.
- Defaults:
  - Port defaults to 80 if omitted.
  - Keepalives defaults applied (keepalives, keepalives_idle, keepalives_interval, keepalives_count).
- Query parameters:
  - connect_timeout and options are preserved as strings.
  - keepalive parameters are converted to integers if provided; invalid values raise an error.
  - Username and password are URL-decoded.

```mermaid
flowchart TD
ParseStart["parse_dsn(dsn)"] --> Normalize["Normalize scheme to postgresql:// if needed"]
Normalize --> UrlParse["urlparse()"]
UrlParse --> ValidateHost{"Has hostname?"}
ValidateHost --> |No| ErrHost["DSNError: missing hostname"]
ValidateHost --> |Yes| ValidateDB{"Has database path?"}
ValidateDB --> |No| ErrDB["DSNError: missing database"]
ValidateDB --> BuildParams["Build base params: host, port, dbname"]
BuildParams --> HasCreds{"Has user/password?"}
HasCreds --> |Yes| DecodeCreds["URL-decode user/password"]
HasCreds --> |No| ApplyDefaults["Apply keepalives defaults"]
DecodeCreds --> ApplyDefaults
ApplyDefaults --> QueryParams{"Has query params?"}
QueryParams --> |No| Done["Return params"]
QueryParams --> |Yes| MergeQP["Merge connect_timeout/options"]
MergeQP --> Keepalives{"Any keepalive keys?"}
Keepalives --> |Yes| ValidateInt["Validate integer; else DSNError"]
Keepalives --> |No| Done
ValidateInt --> Done
```

**Diagram sources**
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)

**Section sources**
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)

### Connection Wrapper and Lifecycle
- Lazy connection creation: connection is established on first access to the conn property or when a closed connection is detected.
- Autocommit: enabled by default; can be disabled via constructor parameter.
- Cursor factory: returns dict-row cursors for convenient result handling.
- Resource management: close() method ensures cleanup; context manager support (__enter__/__exit__) closes on exit.
- Reconnection: if the underlying connection is closed, accessing conn recreates it.

```mermaid
classDiagram
class HologresConnection {
+string raw_dsn
+string masked_dsn
+bool autocommit
-Connection _conn
-dict _params
+conn Connection
+cursor() Cursor
+execute(sql, params) list
+execute_many(sql, params_list) void
+close() void
+__enter__() HologresConnection
+__exit__(exc_type, exc_val, exc_tb) void
}
```

**Diagram sources**
- [connection.py:178-223](file://hologres-cli/src/hologres_cli/connection.py#L178-L223)

**Section sources**
- [connection.py:178-223](file://hologres-cli/src/hologres_cli/connection.py#L178-L223)

### Command Integration and Error Handling
- CLI entry point:
  - Declares --dsn option bound to HOLOGRES_DSN environment variable.
  - Catches DSNError globally and prints structured error output.
- Command usage:
  - SQL command obtains a connection via get_connection and executes queries safely (read-only enforcement, row limit checks).
  - Status command validates connectivity and reports server info.
- Error propagation:
  - DSN resolution failures raise DSNError.
  - SQL command blocks write operations and enforces row limits; logs operations with masked DSNs.

```mermaid
sequenceDiagram
participant User as "User"
participant CLI as "CLI (main.py)"
participant SQL as "Command : SQL (sql.py)"
participant Conn as "HologresConnection"
participant DB as "Database"
User->>CLI : hologres sql "... [--dsn ...]"
CLI->>SQL : invoke sql_cmd(...)
SQL->>Conn : get_connection(dsn)
Conn-->>SQL : HologresConnection
SQL->>Conn : execute(query)
Conn->>DB : connect + execute
DB-->>Conn : results
Conn-->>SQL : rows
SQL-->>CLI : success/error output
CLI-->>User : formatted response
```

**Diagram sources**
- [main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)
- [sql.py:66-135](file://hologres-cli/src/hologres_cli/commands/sql.py#L66-L135)
- [connection.py:225-229](file://hologres-cli/src/hologres_cli/connection.py#L225-L229)

**Section sources**
- [main.py:98-107](file://hologres-cli/src/hologres_cli/main.py#L98-L107)
- [sql.py:66-135](file://hologres-cli/src/hologres_cli/commands/sql.py#L66-L135)
- [status.py:22-61](file://hologres-cli/src/hologres_cli/commands/status.py#L22-L61)

### Security Features
- Password masking:
  - mask_dsn_password replaces the password portion with a placeholder for safe logging and reporting.
- Audit logging:
  - log_operation records operations with masked DSNs, durations, and outcomes to a JSONL log file under ~/.hologres.
- Sensitive data masking in outputs:
  - SQL command masks sensitive fields in query results unless disabled.

```mermaid
flowchart TD
StartSec["Connection acquired"] --> Mask["mask_dsn_password()"]
Mask --> Log["log_operation(..., dsn_masked=masked)"]
Log --> Output["print_output(...)"]
```

**Diagram sources**
- [connection.py:173-176](file://hologres-cli/src/hologres_cli/connection.py#L173-L176)
- [logger.py:36-74](file://hologres-cli/src/hologres_cli/logger.py#L36-L74)
- [sql.py:108-114](file://hologres-cli/src/hologres_cli/commands/sql.py#L108-L114)

**Section sources**
- [connection.py:173-176](file://hologres-cli/src/hologres_cli/connection.py#L173-L176)
- [logger.py:36-74](file://hologres-cli/src/hologres_cli/logger.py#L36-L74)
- [sql.py:108-114](file://hologres-cli/src/hologres_cli/commands/sql.py#L108-L114)

## Dependency Analysis
- External dependencies:
  - psycopg3 (binary variant) for PostgreSQL-compatible connections.
  - click for CLI argument parsing and command framework.
  - tabulate for table output formatting.
- Internal dependencies:
  - Commands depend on get_connection for database access.
  - Logger is used by commands to record operations.

```mermaid
graph LR
PyProj["pyproject.toml"] --> Psycopg["psycopg[binary]"]
PyProj --> Click["click"]
PyProj --> Tabulate["tabulate"]
Main["main.py"] --> Conn["connection.py"]
SQLCmd["commands/sql.py"] --> Conn
StatusCmd["commands/status.py"] --> Conn
SQLCmd --> Logger["logger.py"]
StatusCmd --> Logger
SQLCmd --> Output["output.py"]
```

**Diagram sources**
- [pyproject.toml:6-10](file://hologres-cli/pyproject.toml#L6-L10)
- [main.py:8-12](file://hologres-cli/src/hologres_cli/main.py#L8-L12)
- [sql.py:9-23](file://hologres-cli/src/hologres_cli/commands/sql.py#L9-L23)
- [status.py:7-11](file://hologres-cli/src/hologres_cli/commands/status.py#L7-L11)
- [logger.py:1-14](file://hologres-cli/src/hologres_cli/logger.py#L1-L14)
- [output.py:14-23](file://hologres-cli/src/hologres_cli/output.py#L14-L23)

**Section sources**
- [pyproject.toml:6-10](file://hologres-cli/pyproject.toml#L6-L10)
- [main.py:8-12](file://hologres-cli/src/hologres_cli/main.py#L8-L12)
- [sql.py:9-23](file://hologres-cli/src/hologres_cli/commands/sql.py#L9-L23)
- [status.py:7-11](file://hologres-cli/src/hologres_cli/commands/status.py#L7-L11)

## Performance Considerations
- Connection reuse:
  - HologresConnection caches a single connection and lazily creates it. This avoids repeated handshake overhead for multiple operations within a command invocation.
- Keepalives:
  - Default keepalive settings are applied to maintain connection health over long-running operations.
- Query planning:
  - SQL command probes with a bounded LIMIT to estimate row counts before full execution, reducing unnecessary work for large result sets.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- No DSN configured:
  - Symptom: DSNError indicating no DSN is configured.
  - Resolution: Provide DSN via --dsn flag, HOLOGRES_DSN environment variable, or ~/.hologres/config.env.
- Invalid DSN scheme:
  - Symptom: DSNError mentioning invalid scheme.
  - Resolution: Use hologres://, postgresql://, or postgres://.
- Missing hostname or database:
  - Symptom: DSNError stating missing hostname or database.
  - Resolution: Ensure DSN includes host and database path.
- Invalid keepalive integer:
  - Symptom: DSNError for invalid integer value in keepalive parameter.
  - Resolution: Provide numeric values for keepalive parameters.
- Connection failures:
  - Symptom: Exceptions when connecting to the database.
  - Resolution: Verify network reachability, credentials, and endpoint correctness.
- Authentication errors:
  - Symptom: Authentication failures during connection.
  - Resolution: Confirm user/password and database permissions.
- Network issues:
  - Symptom: Timeouts or connection drops.
  - Resolution: Adjust connect_timeout via DSN query parameter; review firewall and VPC settings.

Operational tips:
- Use masked DSNs in logs and outputs to avoid exposing secrets.
- Enable audit logging to track operations and diagnose issues.
- Prefer explicit DSN configuration in CI/CD environments via environment variables.

**Section sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [test_connection_live.py:96-118](file://hologres-cli/tests/integration/test_connection_live.py#L96-L118)
- [logger.py:36-74](file://hologres-cli/src/hologres_cli/logger.py#L36-L74)

## Conclusion
The Hologres CLI’s connection management API provides a robust, secure, and flexible way to configure and use database connections. By supporting multiple DSN sources, normalizing and validating DSNs, and offering a safe connection wrapper with masking and logging, it enables reliable automation and operational workflows. Following the best practices outlined here will help ensure stable connections and secure operations in production environments.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### A. DSN Configuration Examples
- CLI flag: hologres --dsn 'hologres://user:pass@host:port/db' ...
- Environment variable: export HOLOGRES_DSN='hologres://...'
- Config file (~/.hologres/config.env):
  - HOLOGRES_DSN='hologres://user:pass@host:port/db'

**Section sources**
- [README.md:91-106](file://hologres-cli/README.md#L91-L106)
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)

### B. Connection Behavior Reference
- Default port: 80
- Default keepalives: keepalives=1, keepalives_idle=130, keepalives_interval=10, keepalives_count=15
- Autocommit: enabled by default; can be disabled
- Lazy connection: created on first use or when reopened after closure

**Section sources**
- [connection.py:20-26](file://hologres-cli/src/hologres_cli/connection.py#L20-L26)
- [connection.py:178-223](file://hologres-cli/src/hologres_cli/connection.py#L178-L223)

### C. Test Coverage Highlights
- DSN parsing and normalization
- Config file reading and quoting/escaping
- DSN resolution priority
- Connection lifecycle and reconnection
- Error scenarios and masked outputs

**Section sources**
- [test_connection.py:22-119](file://hologres-cli/tests/test_connection.py#L22-L119)
- [test_connection.py:150-214](file://hologres-cli/tests/test_connection.py#L150-L214)
- [test_connection.py:216-262](file://hologres-cli/tests/test_connection.py#L216-L262)
- [test_connection.py:264-361](file://hologres-cli/tests/test_connection.py#L264-L361)
- [test_connection.py:363-385](file://hologres-cli/tests/test_connection.py#L363-L385)