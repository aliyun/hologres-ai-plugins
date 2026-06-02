# Shard 分布与 Worker 倾斜排查参考

当内存形态判定为"局部倾斜"时，需要排查 Shard 分配均匀度及 Query 访问热点。

## Shard 物理分布检查

### 命令

```bash
hologres sql run --no-limit-check "SELECT worker_id, count(shard_id) AS shard_count, array_agg(shard_id) AS shards FROM hologres.hg_worker_info GROUP BY worker_id ORDER BY shard_count DESC"
```

### 物理不均判定

- Worker 之间 `shard_count` 与平均值偏差 > 20% → 判定 **物理不均**
- 单 Worker shard 数显著高于/低于平均值 → Shard 迁移不均衡

## Worker 内存热点检查

### 命令

```bash
# 各 Worker 内存使用率（云监控）
hologres metric query {prefix}_memory_usage_by_worker \
    --instance-id {instance_id} \
    --start-time {start_time} --end-time {end_time} --period 60
```

### 逻辑倾斜判定

- 物理均衡但特定 Worker CPU/Mem 极高 → 逻辑倾斜
- 可能原因：热点 Dist Key 导致 Broadcast 或 Aggregate 倾斜

## Query 访问热点分析

### 命令

```bash
# 高频访问特定 Worker 的 Query（结合 hg_query_log + hg_worker_info）
hologres sql run --no-limit-check "SELECT query_id, usename, warehouse_name, memory_bytes, cpu_time_ms, duration AS duration_ms, query::char(200) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND memory_bytes > 1073741824 AND usename != 'system' ORDER BY memory_bytes DESC LIMIT 20"
```

### 热点 Key 检测

若发现 Worker 倾斜，检查：
1. 是否存在热点 Dist Key（如 `user_id` 倾斜）
2. 是否有大量 Broadcast 导致单点内存爆炸
3. 是否有特定表的 Aggregate 操作集中在少数 Worker

## 输出格式示例

```
Worker 内存分布：
- worker_0: shards=10, 内存 avg=45%
- worker_1: shards=10, 内存 avg=92% ⚠️ 局部热点
- worker_2: shards=12, 内存 avg=48%（Shard 数偏差 +20%）

热点分析：
- worker_1 内存异常高的可能原因：Dist Key 'user_id' 存在热点值
- 关联高内存 Query Top 3：Query ID xxx, yyy, zzz
```
