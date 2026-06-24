# 数据源映射 & 异常阈值

## 数据源映射

| 诊断项 | 数据来源 | hologres-cli 命令 |
|--------|----------|-------------------|
| CPU 水位 | 云监控 | `hologres metric query {prefix}cpu_usage` / `hologres metric latest {prefix}cpu_usage` |
| QPS / RPS | 云监控 | `hologres metric query {prefix}query_qps` / `{prefix}dml_rps` |
| SQL 延迟 | 云监控 | `hologres metric query {prefix}query_latency` |
| Worker CPU | 云监控 | `hologres metric query {prefix}cpu_usage_by_worker` |
| 锁等待 | PG 系统表 | `hologres sql run`（`pg_locks` + `pg_stat_activity`） |
| 慢 / 长 Query | 元仓 | `hologres sql run`（`hologres.hg_query_log`） |
| Shard 分布 | PG 系统表 | `hologres sql run`（`hologres.hg_worker_info`） |
| Compaction | 云监控 + 元数据 | `hologres metric query {prefix}compaction_*` + `hg_query_log` DDL 审计 |

## 异常阈值

| 维度 | 时间窗口 | 异常阈值 |
|------|----------|----------|
| CPU | 长周期（>24h） | 日均值波动 > 10% |
| CPU | 短周期（<24h） | 小时均值波动 > 30% |
| SQL Latency | 长周期 | 日均延迟波动 > 10% |
| SQL Latency | 短周期 | 小时延迟波动 > 20% |
| Long Query | 长周期 | Max Duration 波动 > 10 小时 |
| Long Query | 短周期 | Max Duration > 1 小时 |
| Shard | 实时 | `shard_count` 偏差 > 1（绝对）或 > 20%（比例） |
| Compaction | 实时 | `duration` / `num` 相对基线激增 > 50% |
