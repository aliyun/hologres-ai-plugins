# 慢查询日志查询（`hologres.hg_query_log`）

当用户提供 `query_id` 时使用。慢查询日志记录每条已完成 SQL 的计划、统计、阶段耗时与资源指标。所有查询经 `hologres sql run --no-limit-check`。

## Lookup SQL

若用户给了大致执行时间，加 `query_start` 范围谓词（已建索引，避免全表扫描）。`query` / `plan` / `query_id` 完整输出，**禁止** 截断。

```bash
hologres sql run --no-limit-check "SELECT query_id, status, datname, command_tag, query_start, duration, optimization_cost, start_query_cost, get_next_cost, duration - COALESCE(optimization_cost, 0) - COALESCE(start_query_cost, 0) - COALESCE(get_next_cost, 0) AS other_cost, extended_cost, read_rows, read_bytes, shuffle_bytes, memory_bytes, cpu_time_ms, physical_reads, result_rows, result_bytes, engine_type, table_read, table_write, application_name, message, query, plan, statistics, visualization_info, query_detail, query_extinfo FROM hologres.hg_query_log WHERE query_id = '<query_id>' ORDER BY query_start DESC LIMIT 5"
```

## 结果处理矩阵

| 结果 | 动作 |
|------|------|
| 无行 | 告知用户该 query 不在 `hologres.hg_query_log`。请用户放宽 `query_start` 范围或提供 SQL / EXPLAIN ANALYZE 文本。慢日志只含已完成 SQL，且保留期可能已过。 |
| 多行 | 优先取 `query_start` 匹配用户上下文的行；不明则分析最新行并声明假设。 |
| `status = FAILED` | 诊断 `message`、启动/优化阶段、锁/资源、SQL 形态；除非用户明确想重跑失败查询，否则不跑 `EXPLAIN ANALYZE`。 |
| `plan` 非空 | 连同同记录的阶段/资源指标一起分析记录的计划。 |
| `plan` 为空但 `query` 存在 | 跑 `hologres sql explain "<query>"` 取估算结构；确认重跑安全后才跑 `EXPLAIN ANALYZE`。 |
| `plan` 被截断 | 说明慢日志计划可能被截断，依赖可见瓶颈 + 指标；必要时对原查询重跑 `EXPLAIN` / `EXPLAIN ANALYZE`。 |

## 阶段症状 → 可能方向

| 症状 | 重点 |
|------|------|
| `optimization_cost` 高 | SQL 极复杂、多 join/子查询、统计过期影响 QO 搜索。 |
| `start_query_cost` 高 | 锁等待、资源排队、schema 同步、serverless 分配、`extended_cost` 中的启动开销。 |
| `get_next_cost` 高 | 算子执行瓶颈；查计划 time、扫描量、join、shuffle、聚合、sort。 |
| `read_bytes` / `physical_reads` 高 | 全表扫描、缺 clustering/bitmap 索引、分区/过滤裁剪差。 |
| `shuffle_bytes` 高 | distribution_key 不匹配、重分区多的 join 或聚合。 |
| `engine_type` 含 `PQE` | 不支持的 HQE 算子/表达式/函数；尽量改写为 HQE 支持的 SQL。 |

## 分析 `query_id` 时组合使用

1. 慢日志阶段耗时：`optimization_cost`、`start_query_cost`、`get_next_cost`、`extended_cost`、`other_cost`。
2. 资源指标：`read_bytes`、`shuffle_bytes`、`memory_bytes`、`cpu_time_ms`、`physical_reads`。
3. 引擎与表元数据：`engine_type`、`table_read`、`table_write`。
4. 记录的计划/统计文本：`plan`、`statistics`、`visualization_info`。
5. 原 SQL：`query`。
