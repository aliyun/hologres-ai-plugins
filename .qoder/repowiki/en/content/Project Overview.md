# Project Overview

<cite>
**Referenced Files in This Document**
- [README.md](file://README.md)
- [hologres-cli/README.md](file://hologres-cli/README.md)
- [hologres-cli/pyproject.toml](file://hologres-cli/pyproject.toml)
- [hologres-cli/src/hologres_cli/main.py](file://hologres-cli/src/hologres_cli/main.py)
- [hologres-cli/src/hologres_cli/commands/sql.py](file://hologres-cli/src/hologres_cli/commands/sql.py)
- [hologres-cli/src/hologres_cli/output.py](file://hologres-cli/src/hologres_cli/output.py)
- [hologres-cli/src/hologres_cli/masking.py](file://hologres-cli/src/hologres_cli/masking.py)
- [hologres-cli/src/hologres_cli/logger.py](file://hologres-cli/src/hologres_cli/logger.py)
- [agent-skills/skills/hologres-cli/SKILL.md](file://agent-skills/skills/hologres-cli/SKILL.md)
- [agent-skills/skills/hologres-cli/references/commands.md](file://agent-skills/skills/hologres-cli/references/commands.md)
- [agent-skills/skills/hologres-cli/references/safety-features.md](file://agent-skills/skills/hologres-cli/references/safety-features.md)
- [agent-skills/skills/hologres-query-optimizer/SKILL.md](file://agent-skills/skills/hologres-query-optimizer/SKILL.md)
- [agent-skills/skills/hologres-slow-query-analysis/SKILL.md](file://agent-skills/skills/hologres-slow-query-analysis/SKILL.md)
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

## Introduction
Hologres AI Plugins is a comprehensive toolkit designed to make Alibaba Cloud Hologres database management more accessible and safer for both beginners and experienced developers. The project combines two complementary parts:
- An AI-agent-friendly Hologres CLI tool with built-in safety guardrails and structured output
- A collection of AI agent skills that provide domain-specific knowledge for IDE integration

The primary goal is to enable seamless automation of database operations while maintaining strict safety controls and providing clear, machine-readable output formats that AI agents can consume reliably.

## Project Structure
The project follows a clean separation of concerns with two main components:

```mermaid
graph TB
subgraph "Hologres AI Plugins"
subgraph "hologres-cli/"
CLI[CLI Tool]
SRC[src/]
TESTS[tests/]
MAIN[main.py]
COMMANDS[commands/]
OUTPUT[output.py]
MASKING[masking.py]
LOGGER[logger.py]
CONNECTION[connection.py]
end
subgraph "agent-skills/"
SKILLS[skills/]
CLI_SKILL[hologres-cli/SKILL.md]
OPT_SKILL[hologres-query-optimizer/SKILL.md]
SLOW_SKILL[hologres-slow-query-analysis/SKILL.md]
end
end
CLI --> SRC
CLI --> SKILLS
SRC --> MAIN
SRC --> COMMANDS
SRC --> OUTPUT
SRC --> MASKING
SRC --> LOGGER
SKILLS --> CLI_SKILL
SKILLS --> OPT_SKILL
SKILLS --> SLOW_SKILL
```

**Diagram sources**
- [README.md:5-15](file://README.md#L5-L15)
- [hologres-cli/src/hologres_cli/main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)

The structure provides:
- **CLI Tool**: A Python-based command-line interface with comprehensive database operations
- **AI Agent Skills**: Domain-specific knowledge packages for IDE integration and Copilot assistance
- **Modular Architecture**: Clear separation between CLI functionality and AI agent capabilities

**Section sources**
- [README.md:5-15](file://README.md#L5-L15)
- [hologres-cli/pyproject.toml:1-68](file://hologres-cli/pyproject.toml#L1-L68)

## Core Components
The project consists of two primary components that work together to provide comprehensive Hologres management capabilities:

### Hologres CLI Tool
The CLI tool serves as the foundation for database operations with AI-agent-friendly features:

**Key Features:**
- **Structured Output**: All commands return standardized JSON by default for easy AI parsing
- **Safety Guardrails**: Built-in protections against dangerous operations
- **Multiple Output Formats**: JSON, table, CSV, and JSON Lines support
- **Sensitive Data Masking**: Automatic protection of personal information
- **Audit Logging**: Comprehensive operation tracking

**Available Commands:**
- `hologres status`: Connection health check
- `hologres instance <name>`: Instance information
- `hologres warehouse [name]`: Compute resource management
- `hologres schema`: Table structure inspection
- `hologres sql "<query>"`: Safe SQL execution
- `hologres data`: Import/export operations
- `hologres history`: Operation audit trail

### AI Agent Skills Collection
The skills collection provides specialized knowledge for AI coding assistants:

**Skills Included:**
- **hologres-cli**: CLI usage guidance and best practices
- **hologres-query-optimizer**: SQL execution plan analysis and optimization
- **hologres-slow-query-analysis**: Performance diagnosis using system logs

**Section sources**
- [README.md:19-96](file://README.md#L19-L96)
- [hologres-cli/README.md:1-314](file://hologres-cli/README.md#L1-L314)

## Architecture Overview
The system employs a dual-layer architecture that separates operational capabilities from AI agent intelligence:

```mermaid
graph TB
subgraph "User Layer"
USER[Developer/User]
AI_AGENT[AI Coding Assistant]
end
subgraph "Hologres AI Plugins"
subgraph "CLI Layer"
CLI_MAIN[CLI Main]
SQL_CMD[SQL Command]
DATA_CMD[Data Commands]
SCHEMA_CMD[Schema Commands]
STATUS_CMD[Status Commands]
end
subgraph "Safety & Utility Layer"
SAFETY[Guardrails]
MASKING[Data Masking]
OUTPUT[Output Formatting]
LOGGER[Audit Logging]
end
subgraph "AI Agent Skills"
CLI_SKILL[CLI Usage Skill]
OPT_SKILL[Query Optimizer Skill]
SLOW_SKILL[Slow Query Analysis Skill]
end
end
subgraph "Database Layer"
HOLOGRES[Hologres Database]
end
USER --> CLI_MAIN
AI_AGENT --> CLI_SKILL
CLI_MAIN --> SQL_CMD
CLI_MAIN --> DATA_CMD
CLI_MAIN --> SCHEMA_CMD
CLI_MAIN --> STATUS_CMD
SQL_CMD --> SAFETY
SQL_CMD --> MASKING
SQL_CMD --> OUTPUT
SQL_CMD --> LOGGER
DATA_CMD --> SAFETY
DATA_CMD --> OUTPUT
DATA_CMD --> LOGGER
SCHEMA_CMD --> OUTPUT
SCHEMA_CMD --> LOGGER
STATUS_CMD --> OUTPUT
CLI_SKILL --> CLI_MAIN
OPT_SKILL --> HOLOGRES
SLOW_SKILL --> HOLOGRES
SAFETY --> HOLOGRES
OUTPUT --> HOLOGRES
LOGGER --> HOLOGRES
```

**Diagram sources**
- [hologres-cli/src/hologres_cli/main.py:15-50](file://hologres-cli/src/hologres_cli/main.py#L15-L50)
- [hologres-cli/src/hologres_cli/commands/sql.py:34-64](file://hologres-cli/src/hologres_cli/commands/sql.py#L34-L64)
- [agent-skills/skills/hologres-cli/SKILL.md:1-155](file://agent-skills/skills/hologres-cli/SKILL.md#L1-L155)

The architecture ensures:
- **Separation of Concerns**: CLI handles operations, skills handle knowledge
- **Safety First**: All operations pass through guardrails
- **AI Integration Ready**: Structured output enables seamless AI assistance
- **Extensible Design**: New skills can be added without affecting core functionality

## Detailed Component Analysis

### CLI Command Processing Flow
The CLI implements a robust command processing pipeline with comprehensive safety checks:

```mermaid
sequenceDiagram
participant User as User
participant CLI as CLI Main
participant Cmd as Command Handler
participant Guard as Safety Guardrails
participant DB as Hologres DB
participant Logger as Audit Logger
User->>CLI : hologres sql "SELECT * FROM users"
CLI->>Cmd : Parse command and arguments
Cmd->>Guard : Validate operation safety
Guard->>Guard : Check row limits
Guard->>Guard : Verify write permissions
Guard->>Guard : Detect dangerous operations
Guard-->>Cmd : Validation result
alt Valid Operation
Cmd->>DB : Execute SQL query
DB-->>Cmd : Query results
Cmd->>Logger : Log operation
Logger-->>Cmd : Confirmation
Cmd-->>CLI : Structured JSON response
CLI-->>User : Formatted output
else Invalid Operation
Guard-->>Cmd : Error details
Cmd->>Logger : Log error
Logger-->>Cmd : Confirmation
Cmd-->>CLI : Error response
CLI-->>User : Error message
end
```

**Diagram sources**
- [hologres-cli/src/hologres_cli/commands/sql.py:66-135](file://hologres-cli/src/hologres_cli/commands/sql.py#L66-L135)
- [hologres-cli/src/hologres_cli/main.py:98-111](file://hologres-cli/src/hologres_cli/main.py#L98-L111)

### Safety Guardrails Implementation
The safety system implements multiple layers of protection:

```mermaid
flowchart TD
START[SQL Command Received] --> CHECK_WRITE{Write Operation?}
CHECK_WRITE --> |Yes| CHECK_FLAG{Has --write flag?}
CHECK_WRITE --> |No| CHECK_LIMIT{Has LIMIT clause?}
CHECK_FLAG --> |No| BLOCK_WRITE[Block Write Operation]
CHECK_FLAG --> |Yes| CHECK_DANGEROUS{Dangerous Write?}
CHECK_DANGEROUS --> |DELETE/UPDATE without WHERE| BLOCK_DANGEROUS[Block Dangerous Write]
CHECK_DANGEROUS --> |Safe write| ALLOW_WRITE[Allow Write]
CHECK_LIMIT --> |No| PROBE_QUERY[Probe with LIMIT]
CHECK_LIMIT --> |Yes| EXECUTE_SQL[Execute SQL]
PROBE_QUERY --> ROW_COUNT{Rows > 100?}
ROW_COUNT --> |Yes| BLOCK_LIMIT[Require LIMIT]
ROW_COUNT --> |No| EXECUTE_SQL
ALLOW_WRITE --> EXECUTE_SQL
EXECUTE_SQL --> MASK_SENSITIVE[Apply Data Masking]
BLOCK_WRITE --> LOG_ERROR[Log Error]
BLOCK_DANGEROUS --> LOG_ERROR
BLOCK_LIMIT --> LOG_ERROR
MASK_SENSITIVE --> LOG_OPERATION[Log Operation]
LOG_OPERATION --> END[Return Response]
LOG_ERROR --> END
```

**Diagram sources**
- [hologres-cli/src/hologres_cli/commands/sql.py:78-104](file://hologres-cli/src/hologres_cli/commands/sql.py#L78-L104)
- [hologres-cli/src/hologres_cli/masking.py:73-93](file://hologres-cli/src/hologres_cli/masking.py#L73-L93)

### AI Agent Integration Patterns
The skills collection provides structured knowledge for AI assistants:

```mermaid
classDiagram
class AISkill {
+string name
+string description
+string[] triggers
+loadKnowledge() void
+processQuery(query) Response
+getBestPractices() string[]
}
class CLISkill {
+string name = "hologres-cli"
+string description = "CLI usage guidance"
+string[] triggers = ["hologres cli", "hologres command"]
+validateDSN() boolean
+suggestCommand() string
+explainSafety() string
}
class QueryOptimizerSkill {
+string name = "hologres-query-optimizer"
+string description = "SQL execution plan analysis"
+string[] triggers = ["hologres explain", "query plan"]
+interpretPlan(plan) Analysis
+optimizeQuery(sql) Recommendations
+explainOperators() string
}
class SlowQuerySkill {
+string name = "hologres-slow-query-analysis"
+string description = "Performance diagnosis"
+string[] triggers = ["hologres slow query"]
+findBottlenecks(logs) Bottlenecks
+analyzeLogs() Analysis
+suggestFixes() Recommendations
}
AISkill <|-- CLISkill
AISkill <|-- QueryOptimizerSkill
AISkill <|-- SlowQuerySkill
```

**Diagram sources**
- [agent-skills/skills/hologres-cli/SKILL.md:1-155](file://agent-skills/skills/hologres-cli/SKILL.md#L1-L155)
- [agent-skills/skills/hologres-query-optimizer/SKILL.md:1-187](file://agent-skills/skills/hologres-query-optimizer/SKILL.md#L1-L187)
- [agent-skills/skills/hologres-slow-query-analysis/SKILL.md:1-160](file://agent-skills/skills/hologres-slow-query-analysis/SKILL.md#L1-L160)

**Section sources**
- [hologres-cli/src/hologres_cli/commands/sql.py:1-199](file://hologres-cli/src/hologres_cli/commands/sql.py#L1-L199)
- [hologres-cli/src/hologres_cli/masking.py:1-93](file://hologres-cli/src/hologres_cli/masking.py#L1-L93)
- [hologres-cli/src/hologres_cli/logger.py:1-105](file://hologres-cli/src/hologres_cli/logger.py#L1-L105)

## Dependency Analysis
The project maintains clean dependencies between components:

```mermaid
graph LR
subgraph "CLI Dependencies"
CLICK[click >= 8.1.0]
PSYCOPG[psycopg[binary] >= 3.1.0]
TABULATE[tabulate >= 0.9.0]
end
subgraph "Development Dependencies"
PYTEST[pytest >= 8.0.0]
COV[pytest-cov >= 4.1.0]
MOCK[pytest-mock >= 3.12.0]
end
subgraph "Runtime Dependencies"
HOLOGRES_CLI[hologres_cli package]
MAIN[main.py]
COMMANDS[commands/]
UTILS[utilities/]
end
CLICK --> HOLOGRES_CLI
PSYCOPG --> HOLOGRES_CLI
TABULATE --> HOLOGRES_CLI
PYTEST --> HOLOGRES_CLI
COV --> HOLOGRES_CLI
MOCK --> HOLOGRES_CLI
HOLOGRES_CLI --> MAIN
MAIN --> COMMANDS
COMMANDS --> UTILS
```

**Diagram sources**
- [hologres-cli/pyproject.toml:6-21](file://hologres-cli/pyproject.toml#L6-L21)

Key dependency characteristics:
- **Minimal Runtime**: Only essential libraries for CLI functionality
- **Development Flexibility**: Comprehensive testing framework
- **Python 3.11+ Requirement**: Modern Python features for better performance
- **Database Connectivity**: Direct PostgreSQL-compatible driver for Hologres

**Section sources**
- [hologres-cli/pyproject.toml:1-68](file://hologres-cli/pyproject.toml#L1-L68)

## Performance Considerations
The system is designed with performance and safety in mind:

### Safety vs Performance Trade-offs
- **Row Limit Protection**: Prevents accidental large result set retrieval
- **Connection Pooling**: Efficient database connection management
- **Output Streaming**: JSON Lines format for large result sets
- **Query Probing**: Smart LIMIT insertion to prevent timeouts

### Optimization Strategies
- **Structured Output**: Enables efficient AI parsing and processing
- **Audit Logging**: Minimal overhead with automatic rotation
- **Data Masking**: Column-based filtering reduces sensitive data exposure
- **Multiple Formats**: Choose optimal output format for specific use cases

## Troubleshooting Guide

### Common Issues and Solutions
**Connection Problems:**
- Verify DSN format: `hologres://user:pass@host:port/database`
- Check environment variables: `HOLOGRES_DSN` must be set
- Validate network connectivity to Hologres endpoint

**Safety Guardrail Errors:**
- **LIMIT_REQUIRED**: Add `LIMIT` clause or use `--no-limit-check`
- **WRITE_GUARD_ERROR**: Include `--write` flag for mutations
- **DANGEROUS_WRITE_BLOCKED**: Add `WHERE` clause to DELETE/UPDATE

**Output Format Issues:**
- Use `-f json|table|csv|jsonl` for different formats
- JSON is recommended for AI agent consumption
- Table format for human readability

**Section sources**
- [hologres-cli/src/hologres_cli/commands/sql.py:25-31](file://hologres-cli/src/hologres_cli/commands/sql.py#L25-L31)
- [hologres-cli/src/hologres_cli/output.py:16-20](file://hologres-cli/src/hologres_cli/output.py#L16-L20)
- [hologres-cli/src/hologres_cli/logger.py:11-13](file://hologres-cli/src/hologres_cli/logger.py#L11-L13)

## Conclusion
Hologres AI Plugins provides a comprehensive solution for AI-assisted Hologres database management. The dual-component architecture successfully balances operational power with safety, making it suitable for both beginners learning Hologres and experienced developers automating complex database tasks.

The combination of AI-agent-friendly CLI tools and specialized AI agent skills creates a powerful ecosystem where:
- **Beginners** benefit from guided operations and safety protections
- **Experienced developers** gain automated tools for routine tasks
- **AI assistants** receive structured, reliable data for intelligent assistance
- **Organizations** maintain security compliance through automatic data masking

This approach represents a forward-looking integration of AI capabilities with database management, positioning teams to leverage both human expertise and artificial intelligence effectively.