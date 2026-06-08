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
    │   ├── hologres-slow-query-analysis/  # 慢查询诊断技能
    │   ├── hologres-schema-generator/     # DDL 建表专家技能
    │   ├── hologres-privileges/           # 权限管理技能
    │   ├── hologres-uv-compute/           # UV/PV 去重计算技能
    │   ├── hologres-bsi-profile-analysis/ # BSI 画像分析技能
    │   ├── hologres-ad-campaign/          # 广告素材生成与投放分析技能
    │   ├── hologres-instance-health-analyse/ # 实例健康诊断与巡检技能
    │   ├── hologres-diagnosis-cpu/        # CPU 异常诊断技能
    │   ├── hologres-diagnosis-memory/     # 内存异常诊断技能（OOM / 泄漏 / 倾斜）
    │   ├── hologres-daily-report/         # 运维诊断日报技能
    │   └── hologres-knowledge-base/       # 检索与 RAG 知识库技能（HGraph 向量 + 全文倒排）
    ├── pyproject.toml
    └── upload_to_pypi.py
```

## 核心组件

### 1. Hologres CLI

一个面向 AI Agent 的命令行工具，内置安全防护机制，支持结构化 JSON 输出。

**核心特性：**

- **Profile 多环境管理** — 通过 `~/.hologres/config.json` 管理多个连接配置，支持交互式配置向导
- **结构化输出** — 所有命令默认返回 JSON 格式，便于 AI Agent 解析
- **安全防护** — 行数限制保护、写操作拦截、危险 SQL 检测
- **双连接模式** — JDBC（psycopg）连接优先，JDBC 不可用时自动回退到 OpenAPI `ExecuteStatement` 方式
- **Dynamic Table 管理** — Dynamic Table 全生命周期管理（V3.1+ 新语法）
- **敏感数据脱敏** — 自动对手机号、邮箱、密码、身份证号、银行卡号等字段进行脱敏
- **多种输出格式** — 支持 JSON、表格（table）、CSV、JSON Lines（JSONL）
- **审计日志** — 所有操作记录到 `~/.hologres/sql-history.jsonl`

**可用命令：**

| 命令 | 说明 |
|------|------|
| `hologres config` | 交互式配置向导 |
| `hologres config list` | 列出所有 Profile |
| `hologres config show` | 查看当前 Profile 详情 |
| `hologres config switch <name>` | 切换当前 Profile |
| `hologres config set <key> <value>` | 设置配置项 |
| `hologres status` | 检查连接状态 |
| `hologres instance <name>` | 查询实例版本和最大连接数 |
| `hologres warehouse [name]` | 列出或查询计算组（Warehouse） |
| `hologres schema tables` | 列出所有表 |
| `hologres schema describe <table>` | 查看表结构 |
| `hologres schema dump <schema.table>` | 导出 DDL |
| `hologres schema size <schema.table>` | 查看表存储大小 |
| `hologres table list [--schema S]` | 列出所有表 |
| `hologres table create --name TABLE --columns COLS [选项] [--dry-run]` | 创建表（支持逻辑分区表 V3.1+） |
| `hologres table dump <schema.table>` | 导出表 DDL |
| `hologres table show <table>` | 查看表结构（列、类型、主键、注释等） |
| `hologres table size <schema.table>` | 查看表存储大小 |
| `hologres table properties <table>` | 查看表属性（存储格式、分布键、TTL 等） |
| `hologres table drop <table> [--if-exists] [--cascade] --confirm` | 删除表（默认安全模式） |
| `hologres table truncate <table> --confirm` | 清空表数据（默认安全模式） |
| `hologres table alter TABLE [选项] [--dry-run]` | 修改表属性（添加列、重命名、TTL 等；逻辑分区表支持 SET 语法设置分区属性） |
| `hologres partition list <table>` | 列出逻辑分区表的分区列表 |
| `hologres partition alter --table <table> --partition <value> --set <key=value> [--dry-run]` | 修改逻辑分区表的分区属性（keep_alive/storage_mode/generate_binlog） |
| `hologres view list [--schema S]` | 列出所有视图 |
| `hologres view show <view>` | 查看视图定义和结构 |
| `hologres sql run "<query>"` | 执行只读 SQL 查询 |
| `hologres sql explain "<query>"` | 查看 SQL 执行计划 |
| `hologres extension list` | 列出已安装扩展 |
| `hologres extension create <name>` | 创建（安装）扩展 |
| `hologres guc show <param>` | 查看 GUC 参数值 |
| `hologres guc set <param> <value>` | 设置 GUC 参数（数据库级别，持久化） |
| `hologres guc reset <param>` | 重置 GUC 参数为默认值 |
| `hologres guc list [--filter keyword]` | 列出常用 GUC 参数及当前值 |
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
| `hologres ai gen "<prompt>" [--model]` | 使用 AI 函数生成文本 |
| `hologres ai image-gen "<prompt>" -o volume://vol/path [选项]` | 使用 AI 函数生成图片到 OSS Volume |
| `hologres ai t2v "<prompt>" -o volume://vol/path [选项]` | 文生视频（text-to-video） |
| `hologres ai i2v "<prompt>" --img-url <url\|本地文件> -o volume://vol/path [选项]` | 图生视频（image-to-video） |
| `hologres ai r2v "<prompt>" --reference-url <url\|本地文件> -o volume://vol/path [选项]` | 参考生视频（reference-to-video） |
| `hologres ai video-edit "<prompt>" --video <url\|本地文件> -o volume://vol/path [选项]` | 视频编辑 |
| `hologres volume create <name> --endpoint <ep> --root <root> --rolearn <arn> --access-key <ak> --access-secret <sk>` | 创建本地 Volume 配置（同时在 OSS 上创建目录占位文件） |
| `hologres volume list` | 列出当前 Profile 下所有 Volume |
| `hologres volume delete <name>` | 删除 Volume 配置 |
| `hologres volume list-files --volume <name> [--prefix P] [--max-count N] [--net internet\|intranet]` | 列出 Volume 下的文件 |
| `hologres volume delete-file --volume <name> --file <path> [--confirm] [--net internet\|intranet]` | 删除 Volume 中的文件 |
| `hologres volume download-file --volume <name> --file <path> -d <dir> [--net internet\|intranet]` | 从 Volume 下载文件 |
| `hologres volume upload-file --volume <name> --local-file <path> --target-file <path> [--net internet\|intranet]` | 上传文件到 Volume |
| `hologres volume view volume://<name>/path/file [--net internet\|intranet]` | 下载文件到临时目录并用系统默认程序打开 |
| `hologres model list [--task T] [--model-type T] [--search S]` | 列出已注册的外部 AI 模型 |
| `hologres model delete <model_name> [--confirm]` | 删除已注册的外部 AI 模型(默认 dry-run) |
| `hologres instance-manage list` | 列出所有 Hologres 实例 |
| `hologres instance-manage get` | 查看实例详情 |
| `hologres instance-manage stop / resume / restart` | 实例生命周期操作 |
| `hologres instance-manage enable-execute-statement` | 开启 ExecuteStatement API（API 模式连接前置条件） |
| `hologres instance-manage disable-execute-statement` | 关闭 ExecuteStatement API |
| `hologres instance-manage get-execute-statement-enabled` | 查询 ExecuteStatement 是否已开启 |

**快速开始：**

```bash
# 从 PyPI 安装
pip install hologres-cli

# 运行交互式配置向导
hologres config

# 检查连接
hologres status

# 列出所有表（表格格式）
hologres -f table schema tables

# 查询数据
hologres sql "SELECT * FROM orders LIMIT 10"

# 使用指定 Profile
hologres --profile prod status

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

#### hologres-schema-generator

Hologres DDL 建表专家，生成优化的建表语句：

- 存储格式选择（列存 / 行存 / 行列共存）
- 索引配置（distribution_key、clustering_key、bitmap_columns、event_time_column）
- 分区表设计（物理分区 / 逻辑分区）
- 数据类型推荐和 Schema 优化

#### hologres-privileges

Hologres 权限管理技能，基于 PostgreSQL 标准授权模型（专家权限模型）：

- 用户创建与角色管理
- Schema / 表 / 列 / 视图级别细粒度授权
- 默认权限配置（ALTER DEFAULT PRIVILEGES）
- 权限问题诊断与排查

#### hologres-uv-compute

基于 Dynamic Table + RoaringBitmap 的实时 UV/PV 去重计算方案：

- RoaringBitmap 位图去重（亿级用户秒级响应）
- Dynamic Table 增量刷新流水线
- 灵活时间范围 UV 聚合（`RB_OR_AGG` 跨天合并）
- UID 字典编码（文本转整数）

#### hologres-bsi-profile-analysis

基于 BSI（位切片索引）的用户画像分析方案：

- 属性标签 + 行为标签联合人群圈选
- GMV 分析、标签分布统计、Top K 查询
- 分桶并行计算
- BSI 函数使用（bsi_build、bsi_sum、bsi_filter、bsi_stat、bsi_topk）

#### hologres-ad-campaign

基于 Hologres AI Function 的广告素材生成与投放分析方案：

- 全 SQL 链路：素材管理 → 主题图片生成 → 分镜脚本 → 视频合成
- 多渠道虚拟投放模拟（微信、抖音、小红书、B站）
- 基于 Dynamic Table 的实时 ROI 分析
- AI 策略建议（预算分配、止损建议、潜力股分析）

#### hologres-instance-health-analyse

Hologres 实例健康诊断与巡检，所有 SQL 通过 `hologres-cli` 执行：

- Warehouse 资源巡检（CPU、内存、连接数，基于 `pg_stat_activity`）
- FAILED Query 报错归类与错误模式分析（`hg_query_log`）
- CPU/内存粒度慢查询分析（按 SQL 指纹聚合）
- 输出结构化诊断报告与优化建议

#### hologres-diagnosis-cpu

Hologres 实例 CPU 使用率异常诊断技能 —— 当 CPU 打满 / 持续高位 / Worker CPU 不均 / 后台 Compaction 干扰时使用：

- CPU 状态分级（持续打满 / 持续高位 / 安全平稳）
- 四象限归因分析（宏观定性 / Worker-Shard 分布定位 / 查询归因 / 后台任务干扰）
- 输出结构化的 Markdown 诊断报告与治理行动清单
- 输入 `instance_id` + 时间窗口，所有 SQL 通过 `hologres-cli` 执行

#### hologres-diagnosis-memory

Hologres 实例内存使用率异常诊断技能 —— 当用户提到内存打满、OOM、内存持续高位、Worker 内存不均、内存泄漏、内存倾斜、内存归因分析等场景时使用：

- 输入 `instance_id` + 时间窗口
- 自动完成内存水位形态判定（全局高 / 局部倾斜 / 持续不回落）
- 业务指标对齐、内存分类初筛（Query vs System/Cache）
- 沿 Query 主线、倾斜主线、Write/后台主线、System/元数据主线四大维度自动下钻
- 云监控数据通过 `hologres metric query`，元仓与 PG 系统表通过 `hologres sql run`，OOM/Jeprof/Coredump 通过 `holo oncall common` 获取
- 输出结构化 Markdown 诊断报告与治理行动清单
- 仅限根因诊断 —— 对问题 Query 只输出 ID + 资源指标快照，不包含 SQL 优化或改写指导

#### hologres-daily-report

Hologres 运维诊断日报 —— 不是监控面板的数据搬运，而是由 AI 助手生成的
**"诊断结论 + 根因解释 + 行动建议"型每日巡检报告**。

- 入参：`instance_id` + `report_date`（默认昨天）+ `region`
- 六大维度：实例健康、可用性、计算资源、SQL 性能、成本治理、容量预测
- 所有指标通过 `hologres-cli` 查询，报告以结构化 Markdown 输出

#### hologres-knowledge-base

基于 Hologres 原生能力搭建企业检索与 RAG 知识库（无需外接向量数据库）：

- **全文倒排索引**（Tantivy + BM25），支持 jieba / IK / ngram / pinyin 等多种中英文分词器
- **HGraph 向量索引** 高性能 KNN 检索（rabitq 量化、内存/磁盘混合存储可选）
- **混合检索** —— 向量 + 全文 + 标量过滤在单条 SQL 内完成（RRF 融合）
- **holo-search-sdk** Python 客户端，提供易用的导入与检索 API
- RAG 模式：服务端 `ai_gen()` 生成 embedding，或客户端 SDK 自定义 embedding 模型
- 覆盖全生命周期：`CREATE TABLE WITH (...)` 一体式建表 → 文档切片导入 → 向量 / BM25 / 混合检索 → LLM Q&A

## 环境要求

- Python 3.11+
- 阿里云 Hologres 实例访问权限

## 安装

### Hologres CLI

```bash
# 从 PyPI 安装
pip install hologres-cli

# 或安装指定版本
pip install hologres-cli==0.1.0

# 初始化配置
hologres config
```

### 开发安装（从源码）

```bash
git clone https://github.com/aliyun/hologres-ai-plugins.git
cd hologres-ai-plugins/hologres-cli
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

CLI 使用基于 **Profile** 的配置方式，配置文件存储在 `~/.hologres/config.json`：

```bash
# 交互式配置向导
hologres config

# 或直接设置配置项
hologres config set region_id cn-hangzhou
hologres config set instance_id hgprecn-cn-xxx
hologres config set database mydb
```

连接解析优先级：
1. **命令行参数**：`hologres --profile <name> status`
2. **当前 Profile**：`config.json` 中的活跃 Profile
3. **报错提示**：引导运行 `hologres config`

## 测试

```bash
cd hologres-cli

# 单元测试（无需数据库连接）
pytest tests/ --ignore=tests/integration

# 集成测试（需要已配置的 Profile）
pytest tests/integration/

# 全部测试并生成覆盖率报告
pytest --cov=src/hologres_cli --cov-report=term-missing
```

## 许可证

[Apache License 2.0](LICENSE) — Copyright 2026 Alibaba Cloud
