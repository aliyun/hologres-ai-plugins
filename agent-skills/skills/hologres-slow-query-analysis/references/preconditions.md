# Preconditions & Environment Setup

本 skill 慢查询分析的详细环境 / 版本 / 权限 / 字段参考。主流程只需 SKILL.md 的简版；环境准备或某步因缺上下文失败时查阅本文件。

本 skill 所有 SQL 通过 `hologres sql run --no-limit-check` 执行（默认 JDBC 直连，`connection_mode=auto` 时 JDBC 失败回退 OpenAPI ExecuteStatement）。

## 1. 安装与连接

```bash
pip install hologres-cli
hologres config                  # 配置 region_id / instance_id / database / 认证
hologres status                  # 验证连通
```

- 连接哪个实例 / 数据库由活跃 profile 的 `instance_id` / `database` 决定；换库用 `hologres config set database <db>` 或 `--profile <name>`。
- 连接层已自动 `SET hg_computing_resource = 'serverless'`；来源标记由 `export HOLOGRES_SKILL=hologres-slow-query-analysis` 注入 `application_name`，无需手写 `SET ...` 前缀。
- RAM 账号要求：实例内 Superuser 或 `pg_read_all_stats` 以读 `hologres.hg_query_log`（见 §3）。

## 2. Hologres 版本矩阵

| Hologres 版本 | 关键特性 |
| :--- | :--- |
| V0.10+ | 基础慢查询日志（`hologres.hg_query_log`） |
| V2.2+ | SQL 指纹 `digest` 字段；`engine_type` 区分 HQE / PQE / FixedQE / PG |
| V2.2.7+ | 默认慢日志阈值 `log_min_duration_statement = 100ms` |
| V3.0.2+ | <100ms 查询的聚合记录 |

低版本实例 `digest` 可能为空，按提示降级为按 `query` 文本聚合。

## 3. `hologres.hg_query_log` 权限

三选一（SQL 经 `hologres sql run --write` 执行授权语句）：

```sql
-- 选项 A：superuser（可读所有库日志）
ALTER USER "<your_cloud_account_id>" SUPERUSER;

-- 选项 B：pg_read_all_stats 角色（推荐，粒度更细）
GRANT pg_read_all_stats TO "<your_cloud_account_id>";

-- 选项 C：SPM 模型，仅当前库
CALL spm_grant('<db_name>_admin', '<your_cloud_account_id>');
```

三项均未授予时，所有针对 `hg_query_log` 的 SELECT 都会返回权限拒绝错误。

## 4. `hg_query_log` 字段参考

### 标识字段
- `query_id` — 唯一 SQL 标识
- `digest` — SQL 指纹（V2.2+，老版本可能为 NULL）
- `usename` — 执行用户
- `application_name` — 应用标签
- `client_addr` — 客户端 IP
- `datname` — 数据库名
- `command_tag` — SQL 类别（`SELECT` / `INSERT` / `UPDATE` / `DELETE` / `DDL` / ...）
- `status` — `SUCCESS` / `FAILED`
- `message` — 错误信息（用于提取 SQLSTATE）

### 时间字段
- `query_start` / `query_end` — 执行起止
- `duration` — 总耗时（ms）
- `query_date` — 分区日期

### SQL 文本
- `query` — 完整 SQL 文本（输出时**不可截断**）

### 资源与执行指标
- `result_rows` / `result_bytes` — 返回客户端
- `read_rows` / `read_bytes` — 从存储扫描
- `affected_rows` / `affected_bytes` — DML 影响
- `memory_bytes` — 峰值内存
- `shuffle_bytes` — shuffle 流量
- `cpu_time_ms` — CPU 时间
- `physical_reads` — 物理读

### 表字段
- `table_read` — 读取表数组
- `table_write` — 写入表

### 计划 / 诊断
- `plan`
- `statistics`
- `agg_stats`
- `visualization_info`
- `query_detail`
- `query_extinfo`
- `extended_info`
- `extended_cost`

## 5. 引擎类型语义（`engine_type`）

`engine_type` 是 Postgres 数组；聚合用 `engine_type::text`（如 `(array_agg(engine_type::text ORDER BY duration DESC))[1]`）。

### HQE — Hologres 原生引擎
- 多数分析查询。
- 效率最高。SQL 主要在 HQE 通常意味着执行路径健康。

### PQE — PostgreSQL 回退
- 部分算子 / 表达式 HQE 原生不支持。
- 出现 PQE 时考虑改写（函数/表达式）以推回 HQE。

### SDK / FixedQE — Fixed Plan
- 面向 Serving 负载优化：点读 / 点写 / 前缀扫描。
- V2.2 由 `SDK` 改名 `FixedQE`。
- Serving 场景正常。**慢 SQL 诊断中 FixedQE 通常不是瓶颈** —— 用 `(engine_type IS NULL OR engine_type::text NOT LIKE '%FixedQE%')` 排除，使分析聚焦 HQE / PG。

### PG — 前端本地
- 系统目录查询 / DDL。
- 资源占用极小。若*用户数据查询*落到此处，本身就是值得排查的红旗。

### 跨引擎分析规则
- **单条 SQL 流程**：`engine_type` 是必填分析项。
- **聚合流程**：呈现 `(array_agg(engine_type::text ORDER BY duration DESC))[1]` 以显示 digest 的代表引擎。
