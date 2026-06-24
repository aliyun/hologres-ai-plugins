# 主线 A — Query 侧内存归因

从 `hologres.hg_query_log` 定位「内存杀手」Query。所有 SQL 经 `hologres sql run --no-limit-check`。**禁止** 对 `query` / `query_id` / `digest` 做 `left()` / `substr()` / `::char(N)` 截断。

## A1. Top-10 高内存 Query（按单次执行）

```bash
hologres sql run --no-limit-check "SELECT query_id, duration AS duration_ms, memory_bytes, shuffle_bytes, cpu_time_ms, query_start, status, usename, engine_type, query AS sql_full FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND memory_bytes IS NOT NULL AND usename <> 'system' ORDER BY memory_bytes DESC LIMIT 10"
```

输出字段：query_id、memory_bytes、shuffle_bytes、cpu_time_ms、warehouse、SQL 样本。

关键信号：
- `memory_bytes` 为各节点峰值的累加 → 仅供相对排序。
- `shuffle_bytes` > 1 GB 需重点关注。
- 与并发 QPS/RPS 交叉验证，区分「单条巨型查询」与「并发累积」。

## A2. 按 SQL 指纹聚合（digest）

```bash
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(memory_bytes)::numeric / 1048576, 2) AS avg_memory_mb, round(max(memory_bytes)::numeric / 1048576, 2) AS peak_memory_mb, round(avg(shuffle_bytes)::numeric / 1048576, 2) AS avg_shuffle_mb, round(sum(memory_bytes)::numeric / 1048576, 2) AS total_memory_mb, max(query_id) AS sample_query_id, max(query) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND digest IS NOT NULL AND memory_bytes IS NOT NULL AND usename <> 'system' GROUP BY digest ORDER BY sum(memory_bytes) DESC LIMIT 10"
```

> 若 `digest` 为空（实例 < V2.2），降级为按 `query` 文本聚合。

## A3. Plan 失真 / Broadcast 倾斜

当单条 Query 内存爆炸时：
- 疑似统计信息过期 → 大表被误 Broadcast → 单点内存爆炸。
- 诊断动作：建议用户执行 `EXPLAIN ANALYZE`（可用 `hologres sql explain "<sql>"` 查看计划）。本技能只标注疑点，不自动改写。

根因模式：统计信息过期 → 大表 Broadcast → 单节点 OOM。

## A4. Worker 倾斜下的 Query 访问模式

观察到 Worker 倾斜时，找出不成比例命中热点 Worker 的 Query：

```bash
hologres sql run --no-limit-check "SELECT query_id, usename, warehouse_name, memory_bytes, cpu_time_ms, duration AS duration_ms, query AS sql_full FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND memory_bytes > 1073741824 AND usename <> 'system' ORDER BY memory_bytes DESC LIMIT 20"
```

判定：热点 Dist Key 将读集中到单 Worker，或聚合算子落在少数 Worker。

## 输出

本技能 **仅做根因诊断** —— 输出 Query ID 与资源快照，不产出 SQL 改写或优化补丁。
