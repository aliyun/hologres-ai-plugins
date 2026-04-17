# DSN Configuration and Connection Management

<cite>
**Referenced Files in This Document**
- [connection.py](file://hologres-cli/src/hologres_cli/connection.py)
- [main.py](file://hologres-cli/src/hologres_cli/main.py)
- [README.md](file://hologres-cli/README.md)
- [test_connection.py](file://hologres-cli/tests/test_connection.py)
- [conftest.py](file://hologres-cli/tests/conftest.py)
- [sql.py](file://hologres-cli/src/hologres_cli/commands/sql.py)
- [schema.py](file://hologres-cli/src/hologres_cli/commands/schema.py)
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
This document explains how the Hologres CLI resolves and uses Data Source Names (DSNs) to establish database connections. It covers the DSN format, resolution priority order, configuration file semantics, DSN parsing logic, parameter extraction, query parameter handling, connection lifecycle, and troubleshooting guidance. Practical examples are included for cloud instances, local development, and custom configurations.

## Project Structure
The DSN configuration and connection management logic resides primarily in the connection module and integrates with the CLI entry point and command modules.

```mermaid
graph TB
CLI["CLI Entry Point<br/>main.py"] --> ConnMod["Connection Module<br/>connection.py"]
ConnMod --> HologresConn["HologresConnection<br/>class"]
ConnMod --> Resolve["resolve_raw_dsn()<br/>resolve_instance_dsn()"]
ConnMod --> Parse["parse_dsn()"]
ConnMod --> Mask["mask_dsn_password()"]
CmdSQL["Command: sql.py"] --> ConnMod
CmdSchema["Command: schema.py"] --> ConnMod
```

**Diagram sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)
- [sql.py:66-135](file://hologres-cli/src/hologres_cli/commands/sql.py#L66-L135)
- [schema.py:42-81](file://hologres-cli/src/hologres_cli/commands/schema.py#L42-L81)

**Section sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

## Core Components
- DSN resolution: Priority order is CLI flag, environment variable, config file.
- DSN parsing: Supports hologres://, postgresql://, and postgres:// schemes; extracts host, port, dbname, user, password; applies defaults and query parameters.
- Connection lifecycle: Lazy connection creation, reconnection on closed connections, context manager support, and explicit close.
- Named instance DSNs: Per-instance DSNs via HOLOGRES_DSN_<instance_name> in environment or config file.

**Section sources**
- [connection.py:39-117](file://hologres-cli/src/hologres_cli/connection.py#L39-L117)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

## Architecture Overview
The CLI resolves the DSN from the highest-priority source available, parses it into connection parameters, and creates a connection lazily when needed. Commands use the connection for queries and ensure it is closed after completion.

```mermaid
sequenceDiagram
participant User as "User"
participant CLI as "CLI (main.py)"
participant Conn as "Connection Module (connection.py)"
participant DB as "PostgreSQL/Hologres"
User->>CLI : Run command with optional --dsn
CLI->>Conn : get_connection(dsn)
alt DSN provided
Conn-->>CLI : HologresConnection
else No DSN provided
Conn->>Conn : resolve_raw_dsn(None)
alt CLI flag present
Conn-->>CLI : HologresConnection
else Env var HOLOGRES_DSN present
Conn-->>CLI : HologresConnection
else Config file ~/.hologres/config.env present
Conn-->>CLI : HologresConnection
else No source
Conn-->>CLI : DSNError
end
end
CLI->>Conn : conn.execute(sql)
Conn->>DB : Connect with parsed params
DB-->>Conn : Connection ready
Conn-->>CLI : Results
CLI->>Conn : conn.close()
```

**Diagram sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [connection.py:225-229](file://hologres-cli/src/hologres_cli/connection.py#L225-L229)
- [connection.py:39-117](file://hologres-cli/src/hologres_cli/connection.py#L39-L117)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

## Detailed Component Analysis

### DSN Resolution and Configuration Sources
- Priority order:
  1) CLI --dsn flag
  2) Environment variable HOLOGRES_DSN
  3) ~/.hologres/config.env file containing HOLOGRES_DSN=
- Named instance DSNs:
  - Look up HOLOGRES_DSN_<instance_name> in environment or ~/.hologres/config.env.
  - Raise a helpful error if not found.

```mermaid
flowchart TD
Start(["resolve_raw_dsn(dsn)"]) --> CheckFlag{"Explicit DSN provided?"}
CheckFlag --> |Yes| ReturnFlag["Return CLI flag DSN"]
CheckFlag --> |No| CheckEnv["Read HOLOGRES_DSN from env"]
CheckEnv --> FoundEnv{"Env var set?"}
FoundEnv --> |Yes| ReturnEnv["Return env DSN"]
FoundEnv --> |No| CheckFile["Check ~/.hologres/config.env"]
CheckFile --> Exists{"File exists?"}
Exists --> |Yes| ReadFile["Read HOLOGRES_DSN from file"]
ReadFile --> FoundFile{"Key found?"}
FoundFile --> |Yes| ReturnFile["Return file DSN"]
FoundFile --> |No| RaiseErr["Raise DSNError"]
Exists --> |No| RaiseErr
```

**Diagram sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)

**Section sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [connection.py:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)
- [README.md:89-106](file://hologres-cli/README.md#L89-L106)

### DSN Parsing and Parameter Extraction
- Supported schemes: hologres://, postgresql://, postgres://
- Normalization: hologres:// is normalized to postgresql:// for downstream parsing.
- Extracted parameters:
  - host, port (default 80 if absent), dbname (path without leading slash)
  - user, password (URL-decoded)
- Default keepalive parameters applied:
  - keepalives, keepalives_idle, keepalives_interval, keepalives_count
- Query parameters handled:
  - keepalives, keepalives_idle, keepalives_interval, keepalives_count (integers)
  - connect_timeout, options (strings)

```mermaid
flowchart TD
PStart(["parse_dsn(dsn)"]) --> Scheme{"Scheme valid?"}
Scheme --> |No| ErrScheme["Raise DSNError: invalid scheme"]
Scheme --> |Yes| Normalize["Normalize hologres:// -> postgresql://"]
Normalize --> UrlParse["urlparse(normalized)"]
UrlParse --> HostCheck{"Has hostname?"}
HostCheck --> |No| ErrHost["Raise DSNError: missing hostname"]
HostCheck --> |Yes| DbCheck{"Has database?"}
DbCheck --> |No| ErrDb["Raise DSNError: missing database"]
DbCheck --> |Yes| BuildParams["Build base params: host, port, dbname"]
BuildParams --> Creds{"Has user/password?"}
Creds --> |Yes| Decode["Unquote user/password"]
Creds --> |No| Defaults["Apply default keepalives"]
Decode --> Defaults
Defaults --> Query{"Has query params?"}
Query --> |No| ReturnParams["Return params"]
Query --> |Yes| ParseQS["parse_qs(query)"]
ParseQS --> ApplyQP["Apply keepalives/connect_timeout/options"]
ApplyQP --> ReturnParams
```

**Diagram sources**
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)

**Section sources**
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [test_connection.py:22-119](file://hologres-cli/tests/test_connection.py#L22-L119)

### Connection Lifecycle and Pooling Behavior
- Lazy connection creation: The underlying connection is created when first accessed via the conn property.
- Reconnection: If the underlying connection is closed, accessing conn recreates it.
- Autocommit: Controlled by constructor argument; passed to the underlying connection.
- Context manager: __enter__/__exit__ ensures cleanup.
- Cursor factory: Uses dict_row for convenient row access.

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
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

**Section sources**
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)
- [test_connection.py:264-324](file://hologres-cli/tests/test_connection.py#L264-L324)

### Password Masking for Logging
- Masks passwords in DSNs for safe logging and display.

**Section sources**
- [connection.py:173-176](file://hologres-cli/src/hologres_cli/connection.py#L173-L176)
- [test_connection.py:121-148](file://hologres-cli/tests/test_connection.py#L121-L148)

### CLI Integration and Error Handling
- The CLI exposes a --dsn option and passes it to subcommands.
- Top-level error handling catches DSN-related errors and prints structured output.

**Section sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [main.py:98-107](file://hologres-cli/src/hologres_cli/main.py#L98-L107)

### Command Usage Patterns
- Commands obtain a connection via get_connection(dsn) and ensure it is closed in a finally block or context manager.
- Example commands include status, schema inspection, and SQL execution.

**Section sources**
- [sql.py:66-135](file://hologres-cli/src/hologres_cli/commands/sql.py#L66-L135)
- [schema.py:42-81](file://hologres-cli/src/hologres_cli/commands/schema.py#L42-L81)

## Dependency Analysis
- The CLI depends on the connection module for DSN resolution and connection creation.
- Commands depend on get_connection to obtain a connection and perform queries.
- The connection module depends on:
  - Standard library modules for path handling, URL parsing, and regex.
  - The psycopg3 driver for database connectivity.

```mermaid
graph LR
CLI["CLI (main.py)"] --> ConnMod["Connection Module (connection.py)"]
ConnMod --> Psycopg["psycopg.connect()"]
CmdSQL["Command: sql.py"] --> ConnMod
CmdSchema["Command: schema.py"] --> ConnMod
```

**Diagram sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)
- [sql.py:66-135](file://hologres-cli/src/hologres_cli/commands/sql.py#L66-L135)
- [schema.py:42-81](file://hologres-cli/src/hologres_cli/commands/schema.py#L42-L81)

**Section sources**
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)

## Performance Considerations
- Keepalive defaults are applied to reduce idle connection timeouts and improve reliability over long-running sessions.
- Lazy connection creation avoids unnecessary overhead when commands do not require a connection.
- Query parameter handling allows tuning of connect_timeout and passing PostgreSQL options.

[No sources needed since this section provides general guidance]

## Troubleshooting Guide
Common DSN-related issues and resolutions:
- No DSN configured:
  - Symptom: DSNError indicating no DSN configured.
  - Resolution: Provide DSN via --dsn flag, HOLOGRES_DSN environment variable, or ~/.hologres/config.env.
- Invalid DSN scheme:
  - Symptom: DSNError stating invalid scheme; expected hologres:// or postgresql://.
  - Resolution: Use a supported scheme.
- Missing hostname:
  - Symptom: DSNError stating DSN must include a hostname.
  - Resolution: Include host in the DSN.
- Missing database:
  - Symptom: DSNError stating DSN must include a database name.
  - Resolution: Include database path in the DSN.
- Invalid integer for keepalive parameter:
  - Symptom: DSNError stating invalid integer value for keepalives_*.
  - Resolution: Provide numeric values for keepalive parameters.
- Authentication failures:
  - Symptom: Connection fails during psycopg.connect.
  - Resolution: Verify credentials, network access, and endpoint correctness; check masked DSN for visibility.

**Section sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)
- [main.py:98-107](file://hologres-cli/src/hologres_cli/main.py#L98-L107)

## Conclusion
The Hologres CLI provides a robust, layered approach to DSN configuration and connection management. By supporting multiple configuration sources, strict DSN parsing, and a resilient connection lifecycle, it enables reliable database operations across diverse environments. The documented priority order, configuration semantics, and troubleshooting steps should facilitate smooth setup and maintenance.

[No sources needed since this section summarizes without analyzing specific files]

## Appendices

### DSN Format and Examples
- Format: hologres://[user[:password]@]host[:port]/database[?options]
- Examples:
  - Cloud instance: hologres://user:pass@your-instance.hologres.aliyuncs.com:80/mydb
  - Local development: hologres://user:pass@localhost:80/mydb
  - With query parameters: hologres://user:pass@host:80/db?connect_timeout=30&keepalives_idle=60

**Section sources**
- [README.md:89-106](file://hologres-cli/README.md#L89-L106)
- [connection.py:120-170](file://hologres-cli/src/hologres_cli/connection.py#L120-L170)

### Configuration File Semantics
- Location: ~/.hologres/config.env
- Supported keys:
  - HOLOGRES_DSN: primary DSN
  - HOLOGRES_DSN_<instance_name>: per-instance DSN
- File format:
  - Plain key=value lines
  - Comments start with #
  - Values may be quoted (single or double) and support shell escapes

**Section sources**
- [connection.py:17-18](file://hologres-cli/src/hologres_cli/connection.py#L17-L18)
- [connection.py:67-86](file://hologres-cli/src/hologres_cli/connection.py#L67-L86)
- [connection.py:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)
- [test_connection.py:150-214](file://hologres-cli/tests/test_connection.py#L150-L214)

### Query Parameter Handling
- Supported parameters:
  - keepalives, keepalives_idle, keepalives_interval, keepalives_count (integers)
  - connect_timeout, options (strings)
- Defaults applied if not specified:
  - keepalives=1, keepalives_idle=130, keepalives_interval=10, keepalives_count=15

**Section sources**
- [connection.py:20-26](file://hologres-cli/src/hologres_cli/connection.py#L20-L26)
- [connection.py:156-170](file://hologres-cli/src/hologres_cli/connection.py#L156-L170)
- [test_connection.py:81-119](file://hologres-cli/tests/test_connection.py#L81-L119)

### Connection Lifecycle Details
- Lazy creation: Connection created on first access to conn property.
- Reconnection: If the underlying connection is closed, accessing conn recreates it.
- Autocommit: Passed through to the underlying connection.
- Context manager: Ensures cleanup via __exit__.
- Cursor factory: Uses dict_row for convenient row access.

**Section sources**
- [connection.py:178-229](file://hologres-cli/src/hologres_cli/connection.py#L178-L229)
- [test_connection.py:284-324](file://hologres-cli/tests/test_connection.py#L284-L324)