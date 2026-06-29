# Stage 2 — 四象限归因

四个象限。象限内相互独立的命令应在同一轮并行下发。所有 SQL 经 `hologres sql run --no-limit-check`，指标经 `hologres metric query`。**禁止** 对 `query` / `query_id` / `digest` 做 `left()` / `substr()` / `::char(N)` 截断。

## Q1 — 宏观定性：业务增长 vs 异常瓶颈

目标：先判断 CPU 上涨是否由业务自然增长引起。

数据：CMS `{prefix}query_qps`、`{prefix}dml_rps`、`{prefix}query_latency`。

```bash
hologres metric query {prefix}query_qps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

hologres metric query {prefix}dml_rps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

hologres metric query {prefix}query_latency \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60
```

| 现象 | 结论 | 后续 |
|------|------|------|
| CPU↑ + QPS/RPS 同比例↑ + 延迟无恶化 | 正常业务增长 | 评估扩容，可中止 |
| CPU↑ 但 QPS/RPS 平稳 / 下降 | 异常瓶颈 | 继续 Q2 / Q3 / Q4 |
| CPU↑ + QPS 平稳 + 延迟显著恶化 | 拥塞 | 重点排查 Q3（大 Query / 锁） |

## Q2 — 分布定位：全局高 vs 局部高

目标：判断 CPU 高位是「全局高」（资源不足）还是「局部高」（Worker / Shard 倾斜）。

数据：CMS `{prefix}cpu_usage_by_worker`；PG `hologres.hg_worker_info`。

```bash
# 各 Worker CPU 分布
hologres metric query {prefix}cpu_usage_by_worker \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

# Worker / Shard 均衡性
hologres sql run --no-limit-check "SELECT worker_id, count(shard_id) AS shard_count, array_agg(shard_id) AS shards FROM hologres.hg_worker_info GROUP BY worker_id ORDER BY shard_count DESC"

# 各 Worker 当前活跃 / 等待 Query
hologres sql run --no-limit-check "SELECT pid, usename, state, wait_event_type, wait_event, now() - query_start AS wait_duration, query AS sql_full FROM pg_stat_activity WHERE wait_event IS NOT NULL AND state = 'active' AND usename != 'system' ORDER BY query_start ASC"
```

倾斜判定：
- Worker `shard_count` 与均值差值 **> 1**（绝对）或比例偏差 **> 20%** → **物理倾斜**。
- 单 Worker CPU > 均值 1.5 倍且 > 70%（绝对） → **局部热点**。

## Q3 — 查询归因：谁是资源杀手

### 3.1 Top-N CPU 消费大 Query

```bash
hologres sql run --no-limit-check "SELECT query_id, duration AS duration_ms, cpu_time_ms, query_start, status, usename, warehouse_name, engine_type, query AS sql_full FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND cpu_time_ms IS NOT NULL AND usename != 'system' ORDER BY cpu_time_ms DESC LIMIT 10"
```

### 3.2 长 Query 与锁竞争

Long Query 阈值：
- 长周期：`Max Duration` 波动 > 10 小时。
- 短周期：`Max Duration > 1 小时`。
- 通用：`Max Duration > 历史最大值 × 50%` 且 `> 10 min`。

```bash
# 当前在执行的长 Query
hologres sql run --no-limit-check "SELECT pid, usename, state, now() - query_start AS run_duration, wait_event_type, wait_event, query AS sql_full FROM pg_stat_activity WHERE state = 'active' AND usename != 'system' AND now() - query_start > interval '10 min' ORDER BY query_start ASC"

# 历史长 Query Top 10
hologres sql run --no-limit-check "SELECT query_id, duration AS duration_ms, cpu_time_ms, query_start, status, usename, warehouse_name, query AS sql_full FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND duration > 600000 AND usename != 'system' ORDER BY duration DESC LIMIT 10"

# 锁竞争链（pg_locks + pg_stat_activity）
hologres sql run --no-limit-check "SELECT blocked.pid AS blocked_pid, blocked.usename AS blocked_user, blocked.query AS blocked_query, blocking.pid AS blocking_pid, blocking.usename AS blocking_user, blocking.query AS blocking_query, now() - blocked.query_start AS wait_duration FROM pg_stat_activity blocked JOIN pg_locks blk_lock ON blocked.pid = blk_lock.pid AND NOT blk_lock.granted JOIN pg_locks bg_lock ON blk_lock.transactionid = bg_lock.transactionid AND bg_lock.granted JOIN pg_stat_activity blocking ON bg_lock.pid = blocking.pid WHERE blocked.usename != 'system' ORDER BY wait_duration DESC LIMIT 50"
```

> 也可结合 FixedQE 后端的「拿锁耗时」指标，定位阻塞源 PID 与 SQL。

### 3.3 高频小 Query（digest 聚合）

```bash
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(cpu_time_ms)::numeric, 2) AS avg_cpu_ms, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec, warehouse_name, max(query) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND digest IS NOT NULL AND usename != 'system' GROUP BY digest, warehouse_name ORDER BY sum(cpu_time_ms) DESC LIMIT 10"
```

## Q4 — 后台任务干扰

目标：判断 CPU 上涨是否由 Compaction 写放大或 DDL 变更引起。

数据：CMS SE 指标（`{prefix}compaction_duration`、`{prefix}compaction_num`、`{prefix}se_cpu_usage`）；`hologres.hg_query_log` DDL 审计。

```bash
hologres metric query {prefix}compaction_duration \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

hologres metric query {prefix}compaction_num \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

# DDL 审计
hologres sql run --no-limit-check "SELECT query_start, usename, query_id, status, query AS ddl_sql FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND command_tag IN ('ALTER TABLE','CREATE TABLE','CALL') AND (query ILIKE '%bitmap_columns%' OR query ILIKE '%dictionary_encoding_columns%' OR query ILIKE '%clustering_key%' OR query ILIKE '%segment_key%' OR query ILIKE '%set_table_property%') ORDER BY query_start DESC LIMIT 50"
```

满足以下任一即判定 **Compaction 写放大干扰**：
- `compaction_duration` 或 `compaction_num` 曲线相对基线激增 > 50%。
- 激增时间点附近（±10 min）有 `bitmap_columns` / `dictionary_encoding_columns` / `clustering_key` 等表属性 DDL 变更。
