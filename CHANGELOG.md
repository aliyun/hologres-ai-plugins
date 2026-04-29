# Changelog

## v0.2.0 — 2026-04-17

Hologres AI Plugins v0.2.0 发布。包含面向 AI Agent 的 Hologres CLI 工具和 8 个 AI Agent 技能。

---

### Hologres CLI (`hologres-cli`)

面向 AI Agent 的 Hologres 数据库命令行工具，内置多层安全防护，所有命令默认输出结构化 JSON。

#### 命令体系（14 个资源组，50+ 子命令）

| 资源组 | 子命令 | 说明 |
|--------|--------|------|
| `config` | `config`, `list`, `show`, `switch`, `set` | Profile 多环境管理（交互式配置向导） |
| `status` | `status` | 连接状态检查 |
| `instance` | `instance` | 实例版本与连接数查询 |
| `warehouse` | `warehouse` | 计算组（Warehouse）管理 |
| `schema` | `tables`, `describe`, `dump`, `size` | Schema 级元数据查看 |
| `table` | `list`, `create`, `show`, `dump`, `size`, `properties`, `drop`, `truncate`, `alter` | 表全生命周期管理（含逻辑分区表 V3.1+） |
| `view` | `list`, `show` | 视图管理 |
| `partition` | `list`, `create`, `drop`, `alter` | 逻辑分区表分区管理 |
| `sql` | `run`, `explain` | SQL 执行与执行计划查看 |
| `data` | `export`, `import`, `count` | 数据导入导出（CSV） |
| `extension` | `list`, `create` | 扩展管理 |
| `guc` | `show`, `set`, `reset`, `list` | GUC 参数管理（27 个预置参数分类展示） |
| `dt` | `create`, `list`, `show`, `ddl`, `lineage`, `storage`, `state-size`, `refresh`, `alter`, `drop`, `convert` | Dynamic Table 全生命周期管理（V3.1+ 新语法） |
| 全局 | `history`, `ai-guide` | 命令历史、AI Agent 使用指南 |

#### 安全防护体系

- **连接级只读保护** — 默认 `SET default_transaction_read_only = ON`，所有连接只读，写操作需显式传入 `read_only=False`
- **CLI 写操作拦截** — `sql run` 默认只读，写操作需 `--write` 标志；`table drop/truncate` 需 `--confirm`；`table create/alter` 支持 `--dry-run`
- **危险 SQL 阻断** — 拦截无 WHERE 的 DELETE/UPDATE、DROP DATABASE 等高危操作
- **行数限制保护** — 查询超过 100 行自动触发 `LIMIT` 防护
- **敏感数据脱敏** — 自动对手机号、邮箱、身份证号、银行卡号、密码等进行脱敏
- **审计日志** — 所有操作记录到 `~/.hologres/sql-history.jsonl`，SQL 中的敏感信息自动脱敏

#### 输出格式

- 支持 4 种格式：`json`（默认）、`table`、`csv`、`jsonl`
- 统一响应结构：`{"ok": true/false, "data": ..., "error": ...}`
- 通过 `--format` / `-f` 全局切换

#### 连接管理

- Profile 多环境管理，配置存储在 `~/.hologres/config.json`
- 交互式配置向导 `hologres config`
- `--profile` 参数随时切换环境
- 支持 Hologres 实例 endpoint 自动构建（region_id + instance_id + nettype）

#### 测试覆盖

- 30 个测试文件（13 个单元测试 + 8 个集成测试 + 9 个子命令测试）
- 覆盖率要求 ≥ 95%

---

### Hologres Agent Skills (`hologres-agent-skills`)

8 个 AI Agent 技能，可通过交互式安装器一键安装到各类 AI 编程工具。

#### 支持的 AI 工具

Claude Code、OpenClaw、Cursor、Codex、OpenCode、GitHub Copilot、Qoder、Trae

#### 技能列表

| 技能 | 依赖 | 说明 |
|------|------|------|
| `hologres-cli` | — | CLI 工具使用指南 — 命令用法、安全特性、输出格式、最佳实践 |
| `hologres-query-optimizer` | `hologres-cli` | SQL 查询执行计划分析与优化 — EXPLAIN 解读、算子分析、GUC 调优 |
| `hologres-slow-query-analysis` | `hologres-cli` | 慢查询诊断 — hg_query_log 分析、性能瓶颈定位、跨时段对比 |
| `hologres-schema-generator` | `hologres-cli` | DDL 建表专家 — 存储格式选择、索引配置、分区表设计、数据类型推荐 |
| `hologres-privileges` | `hologres-cli` | 权限管理 — PostgreSQL 标准 GRANT/REVOKE、细粒度授权、默认权限配置 |
| `hologres-uv-compute` | `hologres-cli` | UV/PV 去重计算 — Dynamic Table + RoaringBitmap 实时去重流水线 |
| `hologres-bsi-profile-analysis` | `hologres-cli` | BSI 画像分析 — 位切片索引、标签计算、人群圈选、GMV 分析 |
| `hologres-ad-campaign` | `hologres-cli` | 广告素材生成与投放分析 — AI Function 视频合成、虚拟投放、实时 ROI |

#### 安装方式

```bash
# 推荐
uvx hologres-agent-skills

# 或通过 pip
pip install hologres-agent-skills
```

#### 发布渠道

- PyPI: `pip install hologres-agent-skills`
- Aone (contextlab): `python publish_to_aone.py`

---

### 环境要求

- Python 3.11+（CLI）/ Python 3.10+（Agent Skills）
- 阿里云 Hologres 实例访问权限
