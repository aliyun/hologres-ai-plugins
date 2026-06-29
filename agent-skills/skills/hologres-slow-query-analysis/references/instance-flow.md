# 实例整体慢 SQL 分析 — 6 步

当用户**未**提供 `query_id` 时，按序执行这 6 步。每步含 (a) 意图 (b) 要下发的 SQL (c) 逐步输出模板。各步输出相互独立，最终报告中全部呈现。

所有 SQL 经 `hologres sql run --no-limit-check "<SQL>"` 执行。连接层已自动路由到 serverless 池并标记来源，无需手写 `SET ...`（见 [preconditions.md §1](preconditions.md)）。所有 `query_start` 谓词用 `TIMESTAMPTZ '{start_time}'` / `TIMESTAMPTZ '{end_time}'`。

---

## Step 1 — 总体汇总

**意图**：统计窗口内总 / 成功 / 失败 SQL 数。

```bash
hologres sql run --no-limit-check "SELECT COUNT(*) AS total_sql_cnt, COUNT(*) FILTER (WHERE status = 'success') AS success_sql_cnt, COUNT(*) FILTER (WHERE status <> 'success') AS failed_sql_cnt FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}'"
```

**输出模板**

```
【总体汇总】
- 时间范围：{start_time} ~ {end_time}
- SQL 总量：{total_sql_cnt}
- 成功数量：{success_sql_cnt}
- 失败数量：{failed_sql_cnt}
- 成功率 / 失败率：{success_rate} / {failed_rate}
- 结论：{summary}
```

---

## Step 2 — 多维画像

**意图**：跨 digest / 用户 / 应用 / SQL 类型 / 表 / 资源 / 错误做慢 SQL 分布画像。

以下 SQL 并行下发（相互独立读）。每个维度用本节末尾的标准逐项模板呈现 Top-N。

### 2.1 按 digest 总耗时 Top（排除 FixedQE）

```bash
hologres sql run --no-limit-check "SELECT digest, (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id, command_tag, (array_agg(engine_type::text ORDER BY duration DESC))[1] AS sample_engine_type, COUNT(*) AS exec_cnt, AVG(duration)::bigint AS avg_duration, MAX(duration) AS max_duration, SUM(duration) AS total_duration, SUM(read_rows) AS total_read_rows, SUM(read_bytes) AS total_read_bytes, SUM(result_rows) AS total_result_rows, SUM(cpu_time_ms) AS total_cpu_time_ms, SUM(memory_bytes) AS total_memory_bytes, (array_agg(query ORDER BY duration DESC))[1] AS sample_query FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' AND digest IS NOT NULL AND (engine_type IS NULL OR engine_type::text NOT LIKE '%FixedQE%') GROUP BY digest, command_tag ORDER BY total_duration DESC LIMIT 20"
```

> 为何排除 FixedQE：Fixed-Plan SQL（点读 / 点写）是 Serving 负载 —— 频次高但单查询代价小，**不是**慢 SQL 瓶颈。若专门想查 FixedQE，去掉该谓词。

### 2.2 单条最慢 SQL（含 `engine_type`）

```bash
hologres sql run --no-limit-check "SELECT query_id, digest, usename, application_name, command_tag, engine_type, duration, read_rows, read_bytes, result_rows, result_bytes, cpu_time_ms, memory_bytes, physical_reads, query FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' ORDER BY duration DESC LIMIT 20"
```

### 2.3 按用户

```bash
hologres sql run --no-limit-check "SELECT usename, COUNT(*) AS slow_sql_cnt, SUM(duration) AS total_duration, AVG(duration) AS avg_duration, SUM(read_bytes) AS total_read_bytes, SUM(cpu_time_ms) AS total_cpu_time_ms, (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id, (array_agg(query ORDER BY duration DESC))[1] AS sample_query FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' GROUP BY usename ORDER BY total_duration DESC"
```

### 2.4 按应用

```bash
hologres sql run --no-limit-check "SELECT application_name, COUNT(*) AS slow_sql_cnt, SUM(duration) AS total_duration, AVG(duration) AS avg_duration, (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id, (array_agg(query ORDER BY duration DESC))[1] AS sample_query FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' GROUP BY application_name ORDER BY total_duration DESC"
```

### 2.5 按 SQL 类型（`command_tag`）

```bash
hologres sql run --no-limit-check "SELECT command_tag, COUNT(*) AS cnt, SUM(duration) AS total_duration, AVG(duration) AS avg_duration, SUM(read_bytes) AS total_read_bytes, SUM(cpu_time_ms) AS total_cpu_time_ms, (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id, (array_agg(query ORDER BY duration DESC))[1] AS sample_query FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' GROUP BY command_tag ORDER BY total_duration DESC"
```

### 2.6 按读取表（热点表）

```bash
hologres sql run --no-limit-check "SELECT t.table_name, COUNT(*) AS slow_sql_cnt, SUM(l.duration) AS total_duration, AVG(l.duration) AS avg_duration, SUM(l.read_bytes) AS total_read_bytes, SUM(l.cpu_time_ms) AS total_cpu_time_ms, (array_agg(l.query_id ORDER BY l.duration DESC))[1] AS sample_query_id, (array_agg(l.query ORDER BY l.duration DESC))[1] AS sample_query FROM hologres.hg_query_log l CROSS JOIN LATERAL unnest(l.table_read) AS t(table_name) WHERE l.query_start >= TIMESTAMPTZ '{start_time}' AND l.query_start < TIMESTAMPTZ '{end_time}' GROUP BY t.table_name ORDER BY total_duration DESC LIMIT 20"
```

### 2.7 按写入表

```bash
hologres sql run --no-limit-check "SELECT table_write, COUNT(*) AS slow_sql_cnt, SUM(duration) AS total_duration, AVG(duration) AS avg_duration, SUM(affected_rows) AS total_affected_rows, SUM(affected_bytes) AS total_affected_bytes, (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id, (array_agg(query ORDER BY duration DESC))[1] AS sample_query FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' AND table_write IS NOT NULL GROUP BY table_write ORDER BY total_duration DESC"
```

### 2.8 最大扫描

```bash
hologres sql run --no-limit-check "SELECT query_id, digest, duration, read_rows, read_bytes, result_rows, result_bytes, query FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' ORDER BY read_bytes DESC LIMIT 20"
```

### 2.9 最高内存

```bash
hologres sql run --no-limit-check "SELECT query_id, digest, duration, memory_bytes, cpu_time_ms, query FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' ORDER BY memory_bytes DESC, duration DESC LIMIT 20"
```

### 2.x 逐维度输出模板

```
【{诊断项名称}】
- 指标口径：{统计口径说明}
- 关键结果：{核心数值或 Top 对象，每条须含 query_id 示例}
- 典型完整 SQL（含 query_id）：query_id={sample_query_id}，SQL={完整 query 原文，不可截断}
- 现象总结：{现象描述}
- 原因判断：{原因分析}
- 建议：{优化建议}
- 结论：{一句话总结}
```

---

## Step 3 — 选出最该优先优化的 SQL

**意图**：按 [diagnosis-rules.md](diagnosis-rules.md) 规则排序候选：

1. 单次执行重 —— 高 `duration` 且高 `read_bytes` / `memory_bytes` / `cpu_time_ms` / `physical_reads`
2. 聚合重 —— 每 `digest` 高 `SUM(duration)`
3. 坏扫描比 —— `read_rows / result_rows` 很高
4. `table_read` 热点表

**输出模板**

```
【优先优化对象】
- 优先级：P0 / P1 / P2
- SQL 标识：{query_id}
- 对应 digest：{digest}
- SQL 原文：{完整 query 原文}
- 耗时：{duration}
- 资源特征：read_bytes={...} / memory_bytes={...} / cpu_time_ms={...} / physical_reads={...}
- 入选原因：{为什么优先}
- 优化建议：{建议}
```

---

## Step 4 — 重点 SQL 深挖

**意图**：对 Step 3 选出的每条 SQL 拉取完整记录（含 `plan`、`statistics`、`agg_stats`、`query_detail`、`query_extinfo`、`extended_info`、`table_read`、`table_write`）。

```bash
hologres sql run --no-limit-check "SELECT query_id, digest, usename, application_name, client_addr, status, command_tag, duration, query_start, query_end, read_rows, read_bytes, result_rows, result_bytes, cpu_time_ms, memory_bytes, shuffle_bytes, physical_reads, table_read, table_write, query, plan, statistics, agg_stats, query_detail, query_extinfo, extended_info, visualization_info, extended_cost FROM hologres.hg_query_log WHERE query_id = '{query_id}'"
```

**输出模板**

```
【重点 SQL 诊断】
- SQL 标识：{query_id}
- SQL 原文：{完整 query 原文}
- 主要现象：{慢的表现}
- 执行计划特征：{plan / diagnostic 摘要}
- 资源特征：{扫描 / CPU / 内存 / IO}
- 慢因判断：{原因，对照 diagnosis-rules.md 的「慢因判断规则」}
- 优化建议：{建议}
```

---

## Step 5 — 错误 SQL 分类

**意图**：按 SQLSTATE 聚合 `status <> 'SUCCESS'` 记录，每类取一条完整 SQL 样本。完整 SQLSTATE → 错误类型映射见 [error-codes.md](error-codes.md)。

### 5.1 分类汇总

```bash
hologres sql run --no-limit-check "SELECT ltrim(split_part(message, ': ', 2), ' ') AS error_code, count(*) AS error_count, min(query_start) AS first_seen, max(query_start) AS last_seen, count(DISTINCT usename) AS affected_users FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' AND status = 'FAILED' GROUP BY 1 ORDER BY 2 DESC LIMIT 20"
```

### 5.2 逐类明细

```bash
hologres sql run --no-limit-check "SELECT query_id, digest, ltrim(split_part(message, ': ', 2), ' ') AS error_code, duration, status, message, query FROM hologres.hg_query_log WHERE query_start >= TIMESTAMPTZ '{start_time}' AND query_start < TIMESTAMPTZ '{end_time}' AND status <> 'success' ORDER BY query_start DESC"
```

**输出模板**

```
【错误 SQL 按错误类型分类】
- 指标口径：按 SQLSTATE 错误码归类，统计每类失败数量、涉及用户、首次/末次出现时间
- 关键结果：
  | 错误类型 (SQLSTATE) | 失败数 | 涉及用户 | 首次出现 | 末次出现 | 典型报错 |
  | :--- | :--- | :--- | :--- | :--- | :--- |
  | {error_type} ({sqlstate}) | {cnt} | {affected_users} | {first_seen} | {last_seen} | {sample_error} |
- 典型完整 SQL（含 query_id）：query_id={sample_query_id}，SQL={完整 query 原文，不可截断}
- 现象总结：{各类错误占比与集中度}
- 原因判断：{错误根因，参考 error-codes.md}
- 建议：{针对性修复建议}
- 结论：{一句话总结}
```

---

## Step 6 — 最终结论 + 合并优化清单

**意图**：把 Step 3 选出的候选 + Step 5 的错误分析合并成一条可执行清单。每条**必须**含 `query_id` 与完整 SQL 文本（不截断）。

**输出模板**

```
【最终结论与优化建议】
- 时间范围：{start_time} ~ {end_time}
- 总体情况：{summary}
- 主要瓶颈：{bottleneck}

### 需要整改的 SQL 清单

#### P0 — 立即处理
**{表名 / SQL 标识}**（{错误类型简述}）
- query_id：{query_id}
- 完整 SQL：{完整 query 原文，不可截断}
- 报错信息：{message}
- 错误类型：{语法 / 权限 / 资源 / 超时 / 对象不存在 / 其他}
- 整改动作：{具体处理建议}

#### P1 — 观察监控
**{表名 / SQL 标识}**（{现象简述}）
- query_id：{query_id}
- 完整 SQL：{完整 query 原文}
- 状态：{SUCCESS / FAILED}，耗时 {duration}
- 整改动作：{监控 / 优化建议}

### DROP / 修复命令参考（如适用）

```sql
{可直接执行的 DDL / DML 命令}
```

### 总体建议
1. **立即处理**：{优先级最高动作}
2. **监控观察**：{需要持续关注的对象}
3. **例行维护**：{长期优化建议}
```

完整输出要求（标题 / 分析人 / 引擎类型规则 / 必含输出项）见 [output-spec.md](output-spec.md)。
