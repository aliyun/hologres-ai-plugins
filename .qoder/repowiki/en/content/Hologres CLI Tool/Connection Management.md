# Connection Management

<cite>
**Referenced Files in This Document**
- [connection.py](file://hologres-cli/src/hologres_cli/connection.py)
- [main.py](file://hologres-cli/src/hologres_cli/main.py)
- [status.py](file://hologres-cli/src/hologres_cli/commands/status.py)
- [instance.py](file://hologres-cli/src/hologres_cli/commands/instance.py)
- [sql.py](file://hologres-cli/src/hologres_cli/commands/sql.py)
- [logger.py](file://hologres-cli/src/hologres_cli/logger.py)
- [output.py](file://hologres-cli/src/hologres_cli/output.py)
- [test_connection.py](file://hologres-cli/tests/test_connection.py)
- [test_connection_live.py](file://hologres-cli/tests/integration/test_connection_live.py)
- [README.md](file://hologres-cli/README.md)
- [pyproject.toml](file://hologres-cli/pyproject.toml)
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
This document explains the Hologres CLI connection management system. It covers DSN resolution order and format specifications, connection lifecycle, timeout and keepalive configuration, retry mechanisms, security features (SSL/TLS, credentials, connection validation), multi-environment setup patterns, troubleshooting, and performance optimization best practices. The goal is to help both developers and operators configure, operate, and troubleshoot reliable connections to Hologres databases.

## Project Structure
The connection management logic resides primarily in the connection module and is consumed by CLI commands. The main entry point wires DSN configuration into the command context, while commands use connection helpers to establish and manage connections.

```mermaid
graph TB
Main["Main CLI<br/>entry point"] --> Conn["Connection module<br/>DSN resolution & parsing"]
Conn --> Pg["psycopg3 driver<br/>Connection"]
Main --> CmdStatus["Status command"]
Main --> CmdInstance["Instance command"]
Main --> CmdSQL["SQL command"]
CmdStatus --> Conn
CmdInstance --> Conn
CmdSQL --> Conn
Conn --> Logger["Audit logging"]
Conn --> Output["Output formatting"]
```

**Diagram sources**
- [main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)
- [status.py:14-62](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L62)
- [instance.py:14-71](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L71)
- [sql.py:34-199](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L199)

**Section sources**
- [main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

## Core Components
- DSN resolution and parsing: Centralized logic to resolve a DSN from CLI flags, environment variables, or a config file, and to parse it into connection parameters.
- Connection wrapper: A thin wrapper around the underlying driver connection with lazy initialization, reconnection on closed connections, and convenience methods for SQL execution.
- Command integration: Commands obtain a connection via a helper that resolves DSN from context and execute queries safely.

Key responsibilities:
- DSN resolution order and fallbacks
- Parameter normalization and defaults (port, keepalives)
- Password masking for logging
- Lazy connection creation and closure
- Error propagation and logging

**Section sources**
- [connection.py:39-176](file://hologres-cli/src/hologres_cli/connection.py#L39-L176)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)
- [main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)

## Architecture Overview
The CLI exposes a single entry point that injects DSN and output format into the Click context. Commands then call connection helpers to obtain a connection, execute queries, and handle errors consistently.

```mermaid
sequenceDiagram
participant User as "User"
participant CLI as "Main CLI"
participant Ctx as "Click Context"
participant Cmd as "Command (e.g., status)"
participant Conn as "Connection Helper"
participant DB as "psycopg3 Connection"
User->>CLI : Run "hologres status"
CLI->>Ctx : Inject --dsn, --format
Cmd->>Conn : get_connection(dsn)
Conn->>Conn : resolve_raw_dsn()
Conn->>DB : psycopg.connect(**params)
Cmd->>DB : Execute queries
DB-->>Cmd : Results
Cmd-->>User : Formatted output
```

**Diagram sources**
- [main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)
- [status.py:14-62](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L62)
- [connection.py:225-229](file://hologres-cli/src/hologres_cli/connection.py#L225-L229)

## Detailed Component Analysis

### DSN Resolution Order and Format Specifications
- Resolution order:
  1. Explicit CLI flag (--dsn)
  2. Environment variable (HOLOGRES_DSN)
  3. Config file (~/.hologres/config.env) under key HOLOGRES_DSN
  4. Error if none found
- Named instance resolution:
  - Supports HOLOGRES_DSN_<instance_name> in environment or config file
- DSN format:
  - Supported schemes: hologres://, postgresql://, postgres://
  - Format: hologres://[user[:password]@]host[:port]/database[?options]
  - Defaults:
    - Port: 80 if not specified
    - Keepalives: enabled with default idle/interval/count values
  - Query parameters:
    - connect_timeout: passed through
    - options: passed through (e.g., search_path)
    - keepalives family: keepalives, keepalives_idle, keepalives_interval, keepalives_count (integers)

```mermaid
flowchart TD
Start(["resolve_raw_dsn(dsn)"]) --> CheckFlag{"Explicit DSN provided?"}
CheckFlag --> |Yes| ReturnFlag["Return flag DSN"]
CheckFlag --> |No| CheckEnv["Check HOLOGRES_DSN"]
CheckEnv --> EnvFound{"Found?"}
EnvFound --> |Yes| ReturnEnv["Return env DSN"]
EnvFound --> |No| CheckFile["Read ~/.hologres/config.env"]
CheckFile --> FileFound{"Found HOLOGRES_DSN?"}
FileFound --> |Yes| ReturnFile["Return file DSN"]
FileFound --> |No| RaiseErr["Raise DSNError with guidance"]
```

**Diagram sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)

**Section sources**
- [connection.py:39-117](file://hologres-cli/src/hologres_cli/connection.py#L39-L117)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [README.md:91-106](file://hologres-cli/README.md#L91-L106)

### Connection Wrapper and Lifecycle
- Lazy connection creation: The connection is established only when accessed via the conn property.
- Reconnection on closed: If the underlying connection is closed, accessing conn recreates it.
- Autocommit: Controlled by constructor parameter; defaults to True.
- Convenience methods:
  - cursor(): returns a dict-row cursor
  - execute(): executes a statement and returns rows as list of dicts
  - execute_many(): batch execution
  - close(): closes the connection and resets internal reference
- Context manager support: __enter__/__exit__ ensures cleanup.

```mermaid
classDiagram
class HologresConnection {
+string raw_dsn
+string masked_dsn
+bool autocommit
-psycopg.Connection _conn
-dict _params
+conn() psycopg.Connection
+cursor() psycopg.Cursor
+execute(sql, params) list
+execute_many(sql, params_list) void
+close() void
+__enter__() HologresConnection
+__exit__() void
}
```

**Diagram sources**
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

**Section sources**
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

### Timeout Handling and Keepalive Configuration
- Default keepalives are always applied to connection parameters:
  - keepalives: 1
  - keepalives_idle: 130
  - keepalives_interval: 10
  - keepalives_count: 15
- Query parameters:
  - connect_timeout: passed through to the driver
  - options: passed through (e.g., setting search_path)
  - keepalives_*: override defaults when provided

Notes:
- There is no explicit connection pool in the current implementation. Connections are created per-use and closed after commands finish.
- No retry mechanism is implemented in the connection layer.

**Section sources**
- [connection.py:21-26](file://hologres-cli/src/hologres_cli/connection.py#L21-L26)
- [connection.py:156-170](file://hologres-cli/src/hologres_cli/connection.py#L156-L170)

### Security Features
- Password masking:
  - mask_dsn_password replaces the password portion with a placeholder for safe logging and display.
- Credential handling:
  - Credentials are embedded in the DSN; ensure secure storage and permissions on config files.
- Connection validation:
  - Commands perform basic validation by executing lightweight queries (e.g., version, current_database, current_user).
- Audit logging:
  - All operations are logged to a JSONL file with sensitive literals redacted.

```mermaid
sequenceDiagram
participant Cmd as "Command"
participant Conn as "HologresConnection"
participant DB as "psycopg3"
Cmd->>Conn : execute("SELECT ...")
Conn->>DB : cursor.execute(...)
DB-->>Conn : Rows or error
Conn-->>Cmd : Results
Cmd->>Logger : log_operation(...)
Logger-->>Cmd : Done
```

**Diagram sources**
- [status.py:28-61](file://hologres-cli/src/hologres_cli/commands/status.py#L28-L61)
- [logger.py:36-74](file://hologres-cli/src/hologres_cli/logger.py#L36-L74)

**Section sources**
- [connection.py:173-176](file://hologres-cli/src/hologres_cli/connection.py#L173-L176)
- [status.py:28-61](file://hologres-cli/src/hologres_cli/commands/status.py#L28-L61)
- [logger.py:29-33](file://hologres-cli/src/hologres_cli/logger.py#L29-L33)

### Multi-Environment Setup Patterns
- Single environment:
  - Set HOLOGRES_DSN via CLI flag, environment variable, or config file.
- Multiple environments:
  - Use named instances via HOLOGRES_DSN_<name> in environment or config file.
  - Commands can resolve a specific instance and connect accordingly.
- Example patterns:
  - Cloud: hologres://user:pass@host:port/db?connect_timeout=30&options=-c%20search_path=public
  - On-premises: hologres://user:pass@internal-host:80/db

**Section sources**
- [connection.py:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)
- [instance.py:14-32](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L32)
- [README.md:91-106](file://hologres-cli/README.md#L91-L106)

### Retry Mechanisms
- No built-in retry logic exists in the connection layer.
- Recommendations:
  - Implement retries at the caller level for transient network errors.
  - Use exponential backoff and jitter.
  - Limit retries to avoid cascading failures.

[No sources needed since this section provides general guidance]

### Examples of DSN Configurations
- Basic:
  - hologres://user:pass@host:port/db
- With timeouts and options:
  - hologres://user:pass@host:port/db?connect_timeout=30&options=-c%20search_path=public
- Named instance:
  - HOLOGRES_DSN_myinstance=hologres://user:pass@host:port/db

**Section sources**
- [README.md:91-106](file://hologres-cli/README.md#L91-L106)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)

## Dependency Analysis
- External dependencies:
  - psycopg3: database driver
  - click: CLI framework
  - tabulate: table output formatting
- Internal dependencies:
  - Commands depend on connection helpers to obtain connections
  - Connection module depends on psycopg3 and urllib.parse
  - Logger and output modules are used by commands for audit and formatting

```mermaid
graph LR
PyProj["pyproject.toml"] --> Psycopg["psycopg[binary]"]
PyProj --> Click["click"]
PyProj --> Tabulate["tabulate"]
Main["main.py"] --> Conn["connection.py"]
Status["commands/status.py"] --> Conn
Instance["commands/instance.py"] --> Conn
SQL["commands/sql.py"] --> Conn
Conn --> Psycopg
Status --> Logger["logger.py"]
Status --> Output["output.py"]
SQL --> Logger
SQL --> Output
```

**Diagram sources**
- [pyproject.toml:6-10](file://hologres-cli/pyproject.toml#L6-L10)
- [main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)
- [status.py:14-62](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L62)
- [sql.py:34-199](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L199)

**Section sources**
- [pyproject.toml:6-10](file://hologres-cli/pyproject.toml#L6-L10)
- [connection.py:14-15](file://hologres-cli/src/hologres_cli/connection.py#L14-L15)

## Performance Considerations
- Connection reuse:
  - Current implementation creates a new connection per command invocation and closes it afterward. For frequent operations, consider reusing a single connection within a command session.
- Keepalives:
  - Default keepalives are enabled. Adjust keepalives_idle/interval/count if needed for long-running operations or specific network conditions.
- Query batching:
  - Use execute_many for bulk inserts to reduce round-trips.
- Output formatting:
  - Prefer JSONL for streaming large datasets to reduce memory overhead.
- Network locality:
  - Place clients close to the database to minimize latency.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common issues and resolutions:
- No DSN configured:
  - Ensure one of the following is set: --dsn flag, HOLOGRES_DSN env var, or ~/.hologres/config.env with HOLOGRES_DSN.
- Invalid DSN scheme:
  - Use hologres://, postgresql://, or postgres://.
- Missing hostname or database:
  - DSN must include host and database path.
- Connection errors:
  - Verify endpoint reachability, credentials, and firewall rules.
  - Use status command to validate connectivity and inspect server address/port.
- Password visibility:
  - Passwords are masked in logs and outputs; confirm masking is working.
- Audit logs:
  - Check ~/.hologres/sql-history.jsonl for operation history and redacted SQL.

Validation and tests:
- Unit tests cover DSN parsing, masking, config file reading, and connection lifecycle.
- Integration tests validate real connections and error handling.

**Section sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [test_connection.py:22-119](file://hologres-cli/tests/test_connection.py#L22-L119)
- [test_connection_live.py:96-118](file://hologres-cli/tests/integration/test_connection_live.py#L96-L118)
- [status.py:28-61](file://hologres-cli/src/hologres_cli/commands/status.py#L28-L61)

## Conclusion
The Hologres CLI provides a robust, layered connection management system with clear DSN resolution, safe credential handling, and consistent error reporting. While there is no built-in connection pool or retry logic, the design supports straightforward extension for advanced scenarios. By following the documented DSN formats, environment patterns, and security practices, teams can deploy reliable connections across cloud and on-premises environments.

## Appendices

### Appendix A: DSN Format Reference
- Scheme: hologres://, postgresql://, postgres://
- Format: hologres://[user[:password]@]host[:port]/database[?options]
- Defaults:
  - Port: 80
  - Keepalives: enabled with default values
- Query parameters:
  - connect_timeout: integer seconds
  - options: string (e.g., -c search_path=public)
  - keepalives family: integers for keepalives, keepalives_idle, keepalives_interval, keepalives_count

**Section sources**
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [README.md:91-106](file://hologres-cli/README.md#L91-L106)

### Appendix B: Environment and Config Setup
- CLI flag: --dsn "hologres://user:pass@host:port/db"
- Environment variable: export HOLOGRES_DSN="hologres://..."
- Config file: ~/.hologres/config.env with HOLOGRES_DSN="hologres://..."

**Section sources**
- [main.py:15-39](file://hologres-cli/src/hologres_cli/main.py#L15-L39)
- [README.md:97-106](file://hologres-cli/README.md#L97-L106)

### Appendix C: Command Integration Examples
- Status: Validates connection and prints server info
- Instance: Resolves named instance DSN and queries version/max connections
- SQL: Executes read-only queries with safety checks and masking

**Section sources**
- [status.py:14-62](file://hologres-cli/src/hologres_cli/commands/status.py#L14-L62)
- [instance.py:14-71](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L71)
- [sql.py:34-199](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L199)