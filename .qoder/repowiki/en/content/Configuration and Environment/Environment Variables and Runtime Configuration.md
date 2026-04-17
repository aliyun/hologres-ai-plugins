# Environment Variables and Runtime Configuration

<cite>
**Referenced Files in This Document**
- [connection.py](file://hologres-cli/src/hologres_cli/connection.py)
- [main.py](file://hologres-cli/src/hologres_cli/main.py)
- [instance.py](file://hologres-cli/src/hologres_cli/commands/instance.py)
- [logger.py](file://hologres-cli/src/hologres_cli/logger.py)
- [README.md](file://hologres-cli/README.md)
- [pyproject.toml](file://hologres-cli/pyproject.toml)
- [configuration.md](file://agent-skills/skills/hologres-slow-query-analysis/references/configuration.md)
- [SKILL.md](file://agent-skills/skills/hologres-cli/SKILL.md)
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
This document explains how the Hologres CLI manages environment variables and runtime configuration. It covers supported environment variables (including HOLOGRES_DSN and HOLOGRES_DSN_<instance_name>), the ~/.hologres/config.env file format and precedence, CLI-specific configuration, and practical guidance for development, staging, and production environments. It also includes security considerations, best practices, and troubleshooting tips.

## Project Structure
The configuration system spans a small set of focused modules:
- CLI entrypoint defines the --dsn option and environment variable binding
- Connection module resolves DSN from CLI flag, environment, or config file
- Instance command uses named instance DSNs
- Logger writes audit logs under ~/.hologres
- Skill and README documents provide user-facing configuration guidance

```mermaid
graph TB
CLI["CLI Entrypoint<br/>main.py"] --> Conn["Connection Resolver<br/>connection.py"]
Conn --> Env["Environment Variable<br/>HOLOGRES_DSN"]
Conn --> FileCfg["Config File<br/>~/.hologres/config.env"]
CLI --> InstCmd["Instance Command<br/>instance.py"]
InstCmd --> NamedDSN["Named Instance DSN<br/>HOLOGRES_DSN_<name>"]
CLI --> Logger["Audit Logging<br/>logger.py"]
```

**Diagram sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [connection.py:39-117](file://hologres-cli/src/hologres_cli/connection.py#L39-L117)
- [instance.py:14-32](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L32)
- [logger.py:11-12](file://hologres-cli/src/hologres_cli/logger.py#L11-L12)

**Section sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [connection.py:17-18](file://hologres-cli/src/hologres_cli/connection.py#L17-L18)
- [instance.py:14-32](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L32)
- [logger.py:11-12](file://hologres-cli/src/hologres_cli/logger.py#L11-L12)

## Core Components
- HOLOGRES_DSN: primary connection DSN resolved from CLI flag, environment variable, or config file
- HOLOGRES_DSN_<instance_name>: named instance DSN for the instance command
- ~/.hologres/config.env: flat key=value file supporting comments, quotes, and shell escapes
- CLI --dsn flag and HOLOGRES_DSN environment variable binding
- Audit logging directory ~/.hologres for sql-history.jsonl

**Section sources**
- [connection.py:39-117](file://hologres-cli/src/hologres_cli/connection.py#L39-L117)
- [connection.py:67-86](file://hologres-cli/src/hologres_cli/connection.py#L67-L86)
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [instance.py:14-32](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L32)
- [logger.py:11-12](file://hologres-cli/src/hologres_cli/logger.py#L11-L12)

## Architecture Overview
The CLI resolves the DSN in a strict precedence order. Named instance DSNs follow the same resolution pattern.

```mermaid
sequenceDiagram
participant User as "User"
participant CLI as "CLI (main.py)"
participant Conn as "Resolver (connection.py)"
participant Env as "Environment"
participant File as "~/.hologres/config.env"
User->>CLI : Run command with optional --dsn
CLI->>Conn : resolve_raw_dsn(explicit_dsn or None)
alt Explicit DSN provided
Conn-->>CLI : Use CLI flag value
else No explicit DSN
Conn->>Env : Read HOLOGRES_DSN
alt Found in environment
Env-->>Conn : DSN value
Conn-->>CLI : Use environment DSN
else Not found in environment
Conn->>File : Read config.env for HOLOGRES_DSN
alt Found in file
File-->>Conn : DSN value
Conn-->>CLI : Use file DSN
else Not found anywhere
Conn-->>CLI : Raise DSNError with guidance
end
end
end
```

**Diagram sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)

## Detailed Component Analysis

### DSN Resolution and Precedence
- Primary DSN resolution order:
  1) CLI --dsn flag
  2) Environment variable HOLOGRES_DSN
  3) ~/.hologres/config.env key HOLOGRES_DSN
  4) Error if none found
- Named instance DSN resolution order:
  1) Environment variable HOLOGRES_DSN_<instance_name>
  2) ~/.hologres/config.env key HOLOGRES_DSN_<instance_name>
  3) Error if none found

```mermaid
flowchart TD
Start(["resolve_raw_dsn"]) --> CheckFlag["CLI --dsn provided?"]
CheckFlag --> |Yes| UseFlag["Use CLI flag DSN"]
CheckFlag --> |No| CheckEnv["Read HOLOGRES_DSN from environment"]
CheckEnv --> FoundEnv{"Found?"}
FoundEnv --> |Yes| UseEnv["Use environment DSN"]
FoundEnv --> |No| CheckFile["Read ~/.hologres/config.env for HOLOGRES_DSN"]
CheckFile --> FoundFile{"Found?"}
FoundFile --> |Yes| UseFile["Use file DSN"]
FoundFile --> |No| RaiseErr["Raise DSNError with guidance"]
```

**Diagram sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)

**Section sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [connection.py:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)

### ~/.hologres/config.env Format and Syntax Rules
- Flat key=value format
- Supports comments starting with #
- Values can be unquoted or quoted with single or double quotes
- Shell escape sequences are handled during parsing:
  - \$ becomes $
  - \" becomes "
  - \\ becomes \
- Only the target key is extracted; other lines are ignored
- Empty or whitespace-only lines are ignored

Examples of valid entries:
- HOLOGRES_DSN=hologres://user:pass@host/db
- HOLOGRES_DSN="hologres://user:pass@host/db"
- HOLOGRES_DSN='hologres://user:pass@host/db'
- HOLOGRES_DSN="hologres://user:p\\$ss@host/db" → parsed as hologres://user:p$ss@host/db

**Section sources**
- [connection.py:67-86](file://hologres-cli/src/hologres_cli/connection.py#L67-L86)

### CLI-Specific Configuration
- The CLI binds the --dsn option to the HOLOGRES_DSN environment variable
- The --format option controls output format across commands
- The CLI prints a CONNECTION_ERROR response when DSN resolution fails

**Section sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [main.py:98-106](file://hologres-cli/src/hologres_cli/main.py#L98-L106)

### Named Instances and HOLOGRES_DSN_<instance_name>
- The instance command expects a matching HOLOGRES_DSN_<name> environment variable or config file entry
- Resolution follows the same precedence as the primary DSN

**Section sources**
- [instance.py:14-32](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L32)
- [connection.py:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)

### Audit Logging Directory
- Audit logs are written to ~/.hologres/sql-history.jsonl
- The directory is created on demand

**Section sources**
- [logger.py:11-12](file://hologres-cli/src/hologres_cli/logger.py#L11-L12)
- [logger.py:25-27](file://hologres-cli/src/hologres_cli/logger.py#L25-L27)

## Dependency Analysis
The configuration system has minimal external dependencies:
- Click for CLI argument parsing and environment variable binding
- psycopg for database connectivity
- Standard library modules for OS and file operations

```mermaid
graph TB
subgraph "CLI Layer"
M["main.py"]
O["output.py"]
end
subgraph "Runtime Config"
C["connection.py"]
L["logger.py"]
end
P["pyproject.toml"]
M --> C
M --> O
C --> L
P --> M
P --> C
```

**Diagram sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)
- [connection.py:17-18](file://hologres-cli/src/hologres_cli/connection.py#L17-L18)
- [logger.py:11-12](file://hologres-cli/src/hologres_cli/logger.py#L11-L12)
- [pyproject.toml:23-25](file://hologres-cli/pyproject.toml#L23-L25)

**Section sources**
- [pyproject.toml:6-10](file://hologres-cli/pyproject.toml#L6-L10)
- [pyproject.toml:23-25](file://hologres-cli/pyproject.toml#L23-L25)

## Performance Considerations
- DSN resolution is O(n) over the number of lines in config.env; keep the file concise
- Using environment variables avoids file I/O overhead
- Keep ~/.hologres directory on local disk for fast logging and config access

## Troubleshooting Guide
Common issues and resolutions:
- No DSN configured: The resolver raises a DSNError with guidance to use --dsn, HOLOGRES_DSN, or ~/.hologres/config.env
- Invalid DSN scheme: Only hologres://, postgresql://, or postgres:// are accepted
- Missing hostname or database path in DSN: Validation raises an error
- Named instance not found: The resolver raises a DSNError with guidance to add HOLOGRES_DSN_<name> to environment or config file
- Config file syntax errors: Only the target key is parsed; comments and quoting rules apply as documented

Operational checks:
- Verify ~/.hologres/config.env exists and contains the expected key
- Confirm environment variable HOLOGRES_DSN is exported
- Use the status command to validate connectivity

**Section sources**
- [connection.py:59-64](file://hologres-cli/src/hologres_cli/connection.py#L59-L64)
- [connection.py:125-144](file://hologres-cli/src/hologres_cli/connection.py#L125-L144)
- [connection.py:112-117](file://hologres-cli/src/hologres_cli/connection.py#L112-L117)
- [main.py:98-106](file://hologres-cli/src/hologres_cli/main.py#L98-L106)

## Conclusion
The Hologres CLI provides a clear, predictable configuration model with strong precedence rules and robust fallbacks. Environment variables and a simple config file cover most operational scenarios, while the instance command supports named DSNs for multi-cluster setups. The system emphasizes simplicity and safety, with explicit error messages guiding users to correct misconfigurations.

## Appendices

### Environment Variables Reference
- HOLOGRES_DSN: primary connection DSN; supports hologres://, postgresql://, or postgres://
- HOLOGRES_DSN_<instance_name>: DSN for a specific named instance used by the instance command

**Section sources**
- [connection.py:39-64](file://hologres-cli/src/hologres_cli/connection.py#L39-L64)
- [connection.py:89-117](file://hologres-cli/src/hologres_cli/connection.py#L89-L117)
- [instance.py:14-32](file://hologres-cli/src/hologres_cli/commands/instance.py#L14-L32)

### ~/.hologres/config.env Syntax Summary
- Keys and values separated by =
- Comments start with #
- Single or double quotes supported around values
- Shell escapes handled during parsing
- Only the requested key is extracted

**Section sources**
- [connection.py:67-86](file://hologres-cli/src/hologres_cli/connection.py#L67-L86)

### CLI Options and Binding
- --dsn: binds to HOLOGRES_DSN environment variable
- --format/-f: controls output format across commands

**Section sources**
- [main.py:15-40](file://hologres-cli/src/hologres_cli/main.py#L15-L40)

### Deployment Scenarios and Best Practices
- Development
  - Use HOLOGRES_DSN environment variable per developer shell profile
  - Optionally maintain a local ~/.hologres/config.env for team defaults
- Staging
  - Prefer environment variables injected by your platform (CI/CD secrets)
  - Keep config.env minimal and avoid committing secrets
- Production
  - Use environment variables from secure secret managers
  - Avoid storing credentials in config.env on shared machines
  - Use named instances (HOLOGRES_DSN_<name>) for multi-cluster management

### Security Considerations
- Avoid hardcoding credentials in scripts or config.env
- Prefer environment variables managed by your platform’s secret store
- Mask sensitive data in logs and outputs; the CLI masks passwords in DSNs and sensitive literals in SQL
- Restrict filesystem permissions on ~/.hologres to the user account

**Section sources**
- [logger.py:15-22](file://hologres-cli/src/hologres_cli/logger.py#L15-L22)
- [connection.py:173-176](file://hologres-cli/src/hologres_cli/connection.py#L173-L176)

### Related Operational Parameters (Hologres Database Settings)
While not environment variables, Hologres database settings influence slow query logging behavior and retention. These are documented separately and can be tuned via SQL.

- log_min_duration_statement
- log_min_duration_query_stats
- log_min_duration_query_plan
- hg_query_log_retention_time_sec

**Section sources**
- [configuration.md:5-31](file://agent-skills/skills/hologres-slow-query-analysis/references/configuration.md#L5-L31)
- [configuration.md:33-58](file://agent-skills/skills/hologres-slow-query-analysis/references/configuration.md#L33-L58)
- [configuration.md:60-84](file://agent-skills/skills/hologres-slow-query-analysis/references/configuration.md#L60-L84)
- [configuration.md:86-110](file://agent-skills/skills/hologres-slow-query-analysis/references/configuration.md#L86-L110)