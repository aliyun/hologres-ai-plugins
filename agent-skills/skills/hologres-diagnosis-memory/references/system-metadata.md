# 主线 C & D — Write/后台 与 System/元数据归因

当 Q3 路由到非 Query 内存（cache/system/meta），或水位持续不回落时，走这两条主线。所有 SQL 经 `hologres sql run --no-limit-check`，指标经 `hologres metric query`。

## 主线 C — Write / 后台压力

### C1. DML RPS（云监控）

```bash
# DML 写入速率
hologres metric query {prefix}dml_rps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

# FixedQE DML RPS（存在时）
hologres metric query {prefix}fixedqe_dml_rps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60
```

根因模式：批次过大 / commit 间隔过长 → buffer 累积。

### C2. 内存构成（memType 拆分）

```bash
hologres metric query {prefix}memory_usage_detail \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60
```

判定：非 Query 内存（cache / system / meta）攀升且伴随 DML RPS 上升或大量小文件写入 → 后台任务内存膨胀。

## 主线 D — System / 元数据 与内部故障

### D1. 元数据膨胀（hg_table_info）

```bash
# 各 schema 表/分区数（单 schema > 10000 即异常）
hologres sql run --no-limit-check "SELECT schema_name, count(*) AS table_count FROM hologres.hg_table_info WHERE db_name = current_database() AND schema_name NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hologres_statistic') AND type IN ('TABLE', 'PARTITION TABLE', 'LOGICAL PARTITION TABLE') AND collect_time = (SELECT max(collect_time) FROM hologres.hg_table_info WHERE db_name = current_database()) GROUP BY schema_name ORDER BY table_count DESC LIMIT 20"

# 每个父表的分区数（Top 20）
hologres sql run --no-limit-check "SELECT schema_name, table_name, partition_count FROM hologres.hg_table_info WHERE db_name = current_database() AND schema_name NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hologres_statistic') AND type = 'PARTITION TABLE' AND partition_count > 0 AND collect_time = (SELECT max(collect_time) FROM hologres.hg_table_info WHERE db_name = current_database()) ORDER BY partition_count DESC LIMIT 20"
```

判定：任一 schema 表/分区数 > 10000 → Meta Cache 常驻内存过高。

### D2. 长事务

```bash
hologres sql run --no-limit-check "SELECT pid, usename, state, now() - query_start AS txn_duration, wait_event_type, wait_event, query AS sql_full FROM pg_stat_activity WHERE state = 'active' AND usename <> 'system' AND now() - query_start > interval '10 min' ORDER BY query_start ASC"
```

缓解：`SELECT pg_terminate_backend({txn_pid});`（仅在运维批准后执行，需 `hologres sql run --write`）。

### D3. 泄漏 / Coredump（内部工具）

当水位持续不回落、无大 Query、疑似泄漏时，转 [internal-tools.md](internal-tools.md)：通过 `holo oncall common oom {instance_id}` / `holo oncall common coredumps {instance_id}` 排查 OOM List / Jeprof / Coredump，确认是否为内存泄漏或底层 Crash。
