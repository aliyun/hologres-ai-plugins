# Hologres AI Plugins

一套面向 AI Agent 的 [阿里云 Hologres](https://www.alibabacloud.com/product/hologres) 数据库管理工具与技能集合。本项目提供了带安全防护的命令行工具（CLI）以及一组 AI Agent 技能，用于自动化数据库操作、查询优化和性能诊断。

## 项目结构

```
hologres-ai-plugins/
├── hologres-cli/          # Hologres 数据库操作的 Python CLI 工具
└── agent-skills/          # 用于 IDE / Copilot 集成的 AI Agent 技能
    ├── src/
    │   └── holo_plugin_installer/     # 交互式技能安装器
    ├── skills/
    │   ├── hologres-cli/                  # CLI 使用技能
    │   ├── hologres-query-optimizer/      # 查询执行计划分析技能
    │   └── hologres-slow-query-analysis/  # 慢查询诊断技能
    ├── pyproject.toml
    └── upload_to_pypi.py
```

## 核心组件

### 1. Hologres CLI

一个面向 AI Agent 的命令行工具，内置安全防护机制，支持结构化 JSON 输出。

**核心特性：**

- **结构化输出** — 所有命令默认返回 JSON 格式，便于 AI Agent 解析
- **安全防护** — 行数限制保护、写操作拦截、危险 SQL 检测
- **Dynamic Table 管理** — Dynamic Table 全生命周期管理（V3.1+ 新语法）
- **敏感数据脱敏** — 自动对手机号、邮箱、密码、身份证号、银行卡号等字段进行脱敏
- **多种输出格式** — 支持 JSON、表格（table）、CSV、JSON Lines（JSONL）
- **审计日志** — 所有操作记录到 `~/.hologres/sql-history.jsonl`

**可用命令：**

| 命令 | 说明 |
|------|------|
| `hologres status` | 检查连接状态 |
| `hologres instance <name>` | 查询实例版本和最大连接数 |
| `hologres warehouse [name]` | 列出或查询计算组（Warehouse） |
| `hologres schema tables` | 列出所有表 |
| `hologres schema describe <table>` | 查看表结构 |
| `hologres schema dump <schema.table>` | 导出 DDL |
| `hologres schema size <schema.table>` | 查看表存储大小 |
| `hologres table list [--schema S]` | 列出所有表 |
| `hologres table dump <schema.table>` | 导出表 DDL |
| `hologres table show <table>` | 查看表结构（列、类型、主键、注释等） |
| `hologres table size <schema.table>` | 查看表存储大小 |
| `hologres table properties <table>` | 查看表属性（存储格式、分布键、TTL 等） |
| `hologres view list [--schema S]` | 列出所有视图 |
| `hologres view show <view>` | 查看视图定义和结构 |
| `hologres sql run "<query>"` | 执行只读 SQL 查询 |
| `hologres sql explain "<query>"` | 查看 SQL 执行计划 |
| `hologres extension list` | 列出已安装扩展 |
| `hologres extension create <name>` | 创建（安装）扩展 |
| `hologres guc show <param>` | 查看 GUC 参数值 |
| `hologres guc set <param> <value>` | 设置 GUC 参数（数据库级别，持久化） |
| `hologres data export <table> -f out.csv` | 导出表数据到 CSV |
| `hologres data import <table> -f in.csv` | 从 CSV 导入数据到表 |
| `hologres data count <table>` | 统计行数 |
| `hologres dt create` | 创建 Dynamic Table（V3.1+ 新语法） |
| `hologres dt list` | 列出所有 Dynamic Table |
| `hologres dt show <table>` | 查看 Dynamic Table 属性 |
| `hologres dt ddl <table>` | 查看 Dynamic Table 建表语句（DDL） |
| `hologres dt lineage <table>` | 查看 Dynamic Table 血缘关系 |
| `hologres dt storage <table>` | 查看 Dynamic Table 存储明细 |
| `hologres dt state-size <table>` | 查看状态表（State）存储量 |
| `hologres dt refresh <table>` | 手动触发刷新 |
| `hologres dt alter <table>` | 修改 Dynamic Table 属性 |
| `hologres dt drop <table>` | 删除 Dynamic Table（默认安全模式） |
| `hologres dt convert [table]` | 从 V3.0 转换为 V3.1 语法 |
| `hologres history` | 查看最近的命令历史 |
| `hologres ai-guide` | 生成 AI Agent 使用指南 |

**快速开始：**

```bash
# 需要 Python 3.11+
cd hologres-cli
pip install -e .

# 设置连接 DSN
export HOLOGRES_DSN="hologres://user:password@endpoint:port/database"

# 检查连接
hologres status

# 列出所有表（表格格式）
hologres -f table schema tables

# 查询数据
hologres sql "SELECT * FROM orders LIMIT 10"

# 创建 Dynamic Table
hologres dt create -t my_dt --freshness "10 minutes" \
  -q "SELECT col1, SUM(col2) FROM src GROUP BY col1"

# 列出所有 Dynamic Table
hologres dt list

# 查看血缘关系
hologres dt lineage public.my_dt
```

完整文档请参考 [hologres-cli/README.md](hologres-cli/README.md)。

### 2. AI Agent 技能

预置的 AI 技能，可被 AI 编程助手（IDE Copilot）加载，为其提供 Hologres 相关的领域知识。

**快速安装：**

```bash
# 将技能安装到你的 AI 工具（Claude Code、Cursor、Codex 等）
uvx hologres-agent-skills
```

#### hologres-cli

教会 AI Agent 如何高效使用 Hologres CLI 工具，包括命令用法、安全特性、输出格式处理和最佳实践。

#### hologres-query-optimizer

使 AI Agent 能够分析和优化 Hologres SQL 查询执行计划：

- 解读 `EXPLAIN` 和 `EXPLAIN ANALYZE` 输出
- 理解查询算子（Seq Scan、Index Scan、Hash Join 等）
- 识别性能瓶颈和数据倾斜
- 推荐优化策略（索引、分布键、GUC 参数）

#### hologres-slow-query-analysis

使 AI Agent 能够通过 `hologres.hg_query_log` 系统表诊断慢查询和失败查询：

- 查找高资源消耗的查询（CPU、内存、I/O）
- 识别失败查询和错误模式
- 分析查询阶段瓶颈（优化 / 启动 / 执行）
- 跨时间段对比查询性能

## 环境要求

- Python 3.11+
- 阿里云 Hologres 实例访问权限

## 安装

```bash
git clone <repo-url>
cd hologres-ai-plugins/hologres-cli
pip install -e .

# 开发安装（包含测试依赖）
pip install -e ".[dev]"
```

### 安装 Agent 技能

```bash
# 方式一：一键安装（推荐）
uvx hologres-agent-skills

# 方式二：从源码安装
cd hologres-ai-plugins/agent-skills
uv sync
uv run hologres-agent-skills
```

## 配置

CLI 按以下优先级解析数据库连接 DSN：

1. **命令行参数**：`--dsn "hologres://user:pass@host:port/db"`
2. **环境变量**：`export HOLOGRES_DSN="hologres://..."`
3. **配置文件**：`~/.hologres/config.env`

## 测试

```bash
cd hologres-cli

# 单元测试（无需数据库）
pytest -m unit

# 集成测试（需要数据库连接）
export HOLOGRES_TEST_DSN="hologres://user:password@host:port/database"
pytest -m integration

# 全部测试并生成覆盖率报告
pytest --cov=src/hologres_cli --cov-report=term-missing
```

当前测试覆盖率：**95%+**。

## 许可证

[Apache License 2.0](LICENSE) — Copyright 2026 Alibaba Cloud
