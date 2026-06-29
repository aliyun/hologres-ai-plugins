# 内存诊断阈值 & 数据源映射

## 1. 异常阈值

| 维度 | 窗口 | 指标 | 异常阈值 |
|------|------|------|----------|
| 内存使用率 | 实时 | Worker 内存使用率 | > 85% |
| 内存使用率 | 长期 | 低峰基线 | 环比涨 > 10% |
| Worker 倾斜 | 实时 | `Max Worker - Avg Worker` | > 20% |
| Query 内存 | 单查询 | `memory_bytes`（Top N） | > 实例内存 5% |
| Shuffle | 单查询 | `shuffle_bytes` | > 1 GB |
| 元数据 | 长期 | 单 TG 表/分区数 | > 10000 |
| 内部故障 | 事件 | OOM 次数（`hg_query_log` `message ILIKE '%OOM%'`） | > 0 |

## 2. 数据源映射

| 诊断项 | 数据来源 | hologres-cli 命令 |
|--------|----------|-------------------|
| 内存水位 | 云监控 | `hologres metric query {prefix}memory_usage` |
| 各 Worker 内存 | 云监控 | `hologres metric query {prefix}memory_usage_by_worker` |
| QPS / DML RPS | 云监控 | `hologres metric query {prefix}query_qps` / `{prefix}dml_rps` |
| 内存构成 | 云监控 | `hologres metric query {prefix}memory_usage_detail`（memType）+ `{prefix}qe_memory_used_percentage` |
| Query 级内存 | 元仓 | `hologres sql run`（`hologres.hg_query_log` 的 `memory_bytes` / `shuffle_bytes`） |
| Shard / 数据分布 | PG 系统表 | `hologres sql run`（`hologres.hg_worker_info`） |
| 元数据 / 表布局 | 元仓 | `hologres sql run`（`hologres.hg_table_info`、`hologres.hg_worker_info`） |
| 长事务 | PG 系统表 | `hologres sql run`（`pg_stat_activity`） |
| 后台内存占比 | 云监控 | `hologres metric query {prefix}memory_usage_detail`（cache/system/meta） |
| OOM 事件 | 元仓 | `hologres sql run`（`hologres.hg_query_log` 的 `message ILIKE '%OOM%'`） |
| 泄漏 / Coredump | 内部工具 | `holo oncall common oom/coredumps {instance_id}`（见 internal-tools.md） |
