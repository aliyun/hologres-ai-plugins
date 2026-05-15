---
name: hologres-instance-health-analyse
depends: [hologres-cli]
description: >
  Hologres 实例健康诊断与巡检分析。当用户提到实例健康诊断、实例巡检、实例使用状况分析、慢查询分析、报错分析、Warehouse 资源分析、连接数分析、CPU 内存使用分析、查询失败排查等场景时使用。覆盖 Warehouse 资源巡检、FAILED 报错归类分析、CPU/内存粒度慢查询分析三大核心模块，输出结构化诊断报告和优化建议。
  所有 SQL 通过 hologres-cli 执行，享有安全护栏、结构化 JSON 输出和自动错误重试能力。
---

# Hologres 实例健康诊断与巡检

系统性诊断 Hologres 实例健康状态，输出 Warehouse 资源、报错分析、慢查询三大模块的结构化诊断报告。

## 核心诊断模块

```
Warehouse 资源 → 报错归类分析 → 慢查询分析（CPU/内存）→ 汇总诊断报告
```

| 模块 | 分析内容 | 数据来源 |
|------|----------|----------|
| Warehouse 资源 | CPU、内存、连接数使用情况 | `pg_stat_activity`、`hg_warehouse_metrics` |
| 报错分析 | FAILED Query 归类、次数统计、解决方案 | `hologres.hg_query_log` |
| 慢查询（CPU） | 按 SQL 指纹聚合，排查 CPU 热点 | `hologres.hg_query_log` |
| 慢查询（内存） | 按 SQL 指纹聚合，排查内存消耗 | `hologres.hg_query_log` |

## 前提条件

### 1. 安装 hologres-cli

```bash
pip install hologres-cli
```

### 2. 配置连接

```bash
hologres config          # 交互式配置向导
hologres status          # 验证连接
```

### 3. 确认权限

需要 Superuser 或 `pg_read_all_stats` 权限：

```bash
hologres sql run "SELECT current_user, usesuper FROM pg_user WHERE usename = current_user"
```

如权限不足，请 Superuser 执行授权：

```bash
hologres sql run --write "GRANT pg_read_all_stats TO \"云账号ID\""
```

### 4. 设置 SQL Tracking

所有诊断 SQL 执行前设置环境变量，确保查询可追踪：

```bash
export HOLOGRES_SKILL=hologres-instance-health-analyse
```

## 第一步：Warehouse 资源巡检

分析各 Warehouse 的 CPU、内存、连接数使用情况，判断是否存在资源瓶颈。

详细 SQL 见 [references/warehouse-metrics.md](references/warehouse-metrics.md)。

**执行命令**：

```bash
# 各 Warehouse 活跃连接分布
hologres sql run --no-limit-check "SELECT warehouse_name, state, count(1) AS conn_count, count(CASE WHEN wait_event IS NOT NULL THEN 1 END) AS waiting, count(CASE WHEN state = 'active' THEN 1 END) AS active, count(CASE WHEN state = 'idle' THEN 1 END) AS idle FROM pg_stat_activity WHERE usename != 'system' AND datname IS NOT NULL GROUP BY warehouse_name, state ORDER BY warehouse_name, count(1) DESC"

# 等待中的 Query
hologres sql run --no-limit-check "SELECT pid, usename, warehouse_name, state, wait_event_type, wait_event, now() - query_start AS wait_duration, left(query, 100) AS sql_snippet FROM pg_stat_activity WHERE wait_event IS NOT NULL AND state = 'active' AND usename != 'system' ORDER BY query_start ASC"
```

**关键指标**：
- 连接数是否过高（单 Warehouse > 200 告警）
- 是否有长时间等待锁/资源的 Query（`wait_event` 不为空）
- 各 Warehouse 的活跃 Query 分布

**输出格式示例**：

```
Warehouse 资源诊断：
- Warehouse 1：活跃连接 45，等待队列 3，CPU 使用率正常
- Warehouse 2：活跃连接 120（⚠️ 偏高），有 5 个 Query 等待锁
建议：检查是否存在长事务或高频短查询导致连接堆积
```

## 第二步：报错归类分析

查询 `hologres.hg_query_log` 中 `status = 'FAILED'` 的 Query，按报错信息归类统计，给出解决方案。

详细 SQL 及常见报错参考 [references/error-analysis.md](references/error-analysis.md)。

**执行命令**：

```bash
# 按报错类型归类统计（过去7天）
hologres sql run --no-limit-check "SELECT regexp_replace(message, E'\\n', ' ')::char(200) AS error_message, warehouse_name, count(1) AS error_count, min(query_start) AS first_seen, max(query_start) AS last_seen FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '7 days' AND message IS NOT NULL GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 50"
```

**输出格式**（必须按此格式输出）：

```
报错分析汇总：

报错 1：ERROR: 57014: canceling statement due to statement timeout
报错次数：N 次
Warehouse：Warehouse_2
发生时段：2024-09-27 11:17:46 ~ 2024-10-09 16:36:16
解决方案：查询超时通常由慢 SQL 以高 QPS 打入导致 CPU 满载。建议：
  1. 通过慢查询分析定位高频 CPU 消耗 SQL
  2. 优化 SQL 或增加 Warehouse 资源
  3. 考虑设置合理的 statement_timeout

报错 2：...
```

## 第三步：慢查询分析

### 3.1 CPU 粒度慢查询

按 SQL 指纹（digest）归类，找出 CPU 消耗最高的 Query 模式。

```bash
# CPU 粒度慢查询 Top 10（过去1天，按指纹聚合）
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(cpu_time_ms)::numeric / 1000, 2) AS avg_cpu_sec, round(max(cpu_time_ms)::numeric / 1000, 2) AS max_cpu_sec, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec, round(avg(duration)::numeric / 1000, 2) AS avg_duration_sec, warehouse_name, max(query_id) AS sample_query_id, max(query)::char(100) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= now() - interval '1 day' AND digest IS NOT NULL AND usename != 'system' AND cpu_time_ms IS NOT NULL GROUP BY digest, warehouse_name ORDER BY sum(cpu_time_ms) DESC LIMIT 10"
```

### 3.2 内存粒度慢查询

按 SQL 指纹归类，找出内存消耗最高的 Query 模式。

```bash
# 内存粒度慢查询 Top 10（过去7天，按指纹聚合）
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(memory_bytes)::numeric / 1048576, 2) AS avg_memory_mb, round(max(memory_bytes)::numeric / 1048576, 2) AS peak_memory_mb, round(avg(duration)::numeric / 1000, 2) AS avg_duration_sec, warehouse_name, max(query_id) AS sample_query_id, max(query)::char(100) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= now() - interval '7 days' AND digest IS NOT NULL AND memory_bytes IS NOT NULL GROUP BY digest, warehouse_name ORDER BY avg(memory_bytes) DESC LIMIT 10"
```

详细分析 SQL 见 [references/slow-query-analysis.md](references/slow-query-analysis.md)。

**输出格式**（必须按此格式输出）：

```
慢 SQL 1：
QueryID：xxxxx（示例）
SQL 指纹：md5xxxxxx
执行次数：N 次 / 天
平均 CPU：X 秒  |  累计 CPU：Y 秒
原因：该 SQL 扫描量大，缺乏分区过滤，导致全表扫描
优化建议：
  1. 添加分区裁剪条件
  2. 检查是否缺少 bitmap/clustering key 索引
  3. 使用 EXPLAIN ANALYZE 查看执行计划

慢 SQL 2：
...
```

## 第四步：汇总输出诊断报告

完成前三步分析后，综合输出以下结构化报告：

```
========== Hologres 实例健康诊断报告 ==========
诊断时间：{当前时间}
诊断范围：过去 7 天

【1. Warehouse 资源】
状态：正常 / 异常
...

【2. 报错分析】
FAILED Query 总数：N 条
主要报错类型：
  - 超时（statement timeout）：X 次 → [解决方案]
  - OOM（memory exceeded）：Y 次 → [解决方案]
  - ...

【3. 慢查询分析】
CPU 热点 SQL Top 3：
  1. [指纹] 累计 CPU X 秒，N 次/天 → [优化建议]
内存热点 SQL Top 3：
  1. [指纹] 峰值内存 X MB，N 次/天 → [优化建议]

【综合建议】
优先级高：...
优先级中：...
=============================================
```

## 执行指导

**环境准备**：

```bash
export HOLOGRES_SKILL=hologres-instance-health-analyse
```

**逐步执行，每步汇报结果**：

1. `hologres sql run --no-limit-check`：Warehouse 资源查询（pg_stat_activity）
2. `hologres sql run --no-limit-check`：报错归类统计（hg_query_log WHERE status='FAILED'）
3. `hologres sql run --no-limit-check`：CPU 慢查询分析（按 digest 聚合）
4. `hologres sql run --no-limit-check`：内存慢查询分析（按 digest 聚合）
5. 综合以上结果，输出结构化诊断报告

**错误处理**：

CLI 返回结构化错误时，根据 `retryable` 字段决定是否重试：

```json
{"ok": false, "error": {"code": "QUERY_TIMEOUT", "message": "...", "retryable": true, "hint": "Query exceeded time limit. Simplify query or add filters."}}
```

- `retryable: true` → 等待 3 秒后重试一次
- `retryable: false` → 根据 `hint` 调整参数后重试

常见可重试错误：`CONNECTION_ERROR`、`CONNECTION_TIMEOUT`、`QUERY_TIMEOUT`、`QUERY_ERROR`

## 参考文档

| 文档 | 内容 |
|------|------|
| [warehouse-metrics.md](references/warehouse-metrics.md) | Warehouse 资源监控 SQL |
| [error-analysis.md](references/error-analysis.md) | 报错归类分析 + 常见报错解决方案 |
| [slow-query-analysis.md](references/slow-query-analysis.md) | 慢查询诊断 SQL 全集 |

## 注意事项

1. `hologres.hg_query_log` 默认保留一个月数据，单次最多返回 10000 条
2. 查询时**必须带 `query_start` 时间范围条件**，避免全表扫描
3. `query_start` 条件不要嵌套表达式（避免 `to_char(query_start, ...)` 方式）
4. 需要 Superuser 或 `pg_read_all_stats` 权限才能查看全实例日志
5. `digest` 字段从 V2.2 版本起支持，低版本实例该字段为空
6. 所有命令返回 JSON 格式输出，`data.rows` 为结果行数组
7. 使用 `--no-limit-check` 跳过 LIMIT 检查（诊断聚合查询无需 LIMIT）
