# 慢查询诊断分析

所有 SQL 通过 `hologres sql run` 执行，返回结构化 JSON：`{"ok": true, "data": {"rows": [...], "count": N}}`

执行前设置 SQL tracking：

```bash
export HOLOGRES_SKILL=hologres-instance-health-analyse
```

## CPU 粒度慢查询

### CPU 消耗 Top 10（过去1天，按指纹聚合）

```bash
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(cpu_time_ms)::numeric / 1000, 2) AS avg_cpu_sec, round(max(cpu_time_ms)::numeric / 1000, 2) AS max_cpu_sec, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec, round(avg(duration)::numeric / 1000, 2) AS avg_duration_sec, warehouse_name, max(query_id) AS sample_query_id, max(query)::char(100) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= now() - interval '1 day' AND digest IS NOT NULL AND usename != 'system' AND cpu_time_ms IS NOT NULL GROUP BY digest, warehouse_name ORDER BY sum(cpu_time_ms) DESC LIMIT 10"
```

输出解读：
- `total_cpu_sec`：累计 CPU 时间，越高表示该类 SQL 整体资源消耗越大
- `exec_count`：执行次数，高频 SQL 即使单次消耗低，累计也可能很高
- `avg_cpu_sec` vs `avg_duration_sec`：如果 CPU >> Duration，说明并行度高

### CPU 消耗 Top 10（过去7天，长周期分析）

```bash
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(cpu_time_ms)::numeric / 1000, 2) AS avg_cpu_sec, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec, round(avg(duration)::numeric / 1000, 2) AS avg_duration_sec, warehouse_name, max(query_id) AS sample_query_id FROM hologres.hg_query_log WHERE query_start >= now() - interval '7 days' AND digest IS NOT NULL AND usename != 'system' AND cpu_time_ms IS NOT NULL GROUP BY digest, warehouse_name ORDER BY sum(cpu_time_ms) DESC LIMIT 10"
```

### 某个 digest 的执行趋势（按小时）

```bash
# 替换 {DIGEST} 为具体 digest 值
hologres sql run --no-limit-check "SELECT date_trunc('hour', query_start) AS hour, count(1) AS exec_count, round(avg(cpu_time_ms)::numeric / 1000, 2) AS avg_cpu_sec, round(avg(duration)::numeric / 1000, 2) AS avg_duration_sec FROM hologres.hg_query_log WHERE query_start >= now() - interval '1 day' AND digest = '{DIGEST}' GROUP BY 1 ORDER BY 1"
```

## 内存粒度慢查询

### 内存消耗 Top 10（过去7天，按指纹聚合）

```bash
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(memory_bytes)::numeric / 1048576, 2) AS avg_memory_mb, round(max(memory_bytes)::numeric / 1048576, 2) AS peak_memory_mb, round(avg(duration)::numeric / 1000, 2) AS avg_duration_sec, warehouse_name, max(query_id) AS sample_query_id, max(query)::char(100) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= now() - interval '7 days' AND digest IS NOT NULL AND memory_bytes IS NOT NULL GROUP BY digest, warehouse_name ORDER BY avg(memory_bytes) DESC LIMIT 10"
```

输出解读：
- `peak_memory_mb`：峰值内存，如果接近 Warehouse 内存上限则有 OOM 风险
- `avg_memory_mb` vs `peak_memory_mb`：差距大说明内存使用波动，可能与数据量有关

### 内存消耗 Top 10（过去1天，短周期）

```bash
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(memory_bytes)::numeric / 1048576, 2) AS avg_memory_mb, round(max(memory_bytes)::numeric / 1048576, 2) AS peak_memory_mb, round(avg(duration)::numeric / 1000, 2) AS avg_duration_sec, warehouse_name, max(query_id) AS sample_query_id FROM hologres.hg_query_log WHERE query_start >= now() - interval '1 day' AND digest IS NOT NULL AND memory_bytes IS NOT NULL GROUP BY digest, warehouse_name ORDER BY max(memory_bytes) DESC LIMIT 10"
```

## 按应用维度分析

### 各应用 CPU 消耗排名

```bash
hologres sql run --no-limit-check "SELECT application_name, count(1) AS query_count, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec, round(avg(cpu_time_ms)::numeric / 1000, 2) AS avg_cpu_sec, round(sum(memory_bytes)::numeric / 1073741824, 2) AS total_memory_gb FROM hologres.hg_query_log WHERE query_start >= now() - interval '1 day' AND usename != 'system' AND cpu_time_ms IS NOT NULL GROUP BY application_name ORDER BY sum(cpu_time_ms) DESC LIMIT 20"
```

输出解读：
- 识别资源消耗最大的应用，针对性优化
- `hologres-cli/*` 前缀的为 CLI 技能触发的查询

### 各用户 CPU 消耗排名

```bash
hologres sql run --no-limit-check "SELECT usename, warehouse_name, count(1) AS query_count, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec, round(avg(cpu_time_ms)::numeric / 1000, 2) AS avg_cpu_sec, round(max(memory_bytes)::numeric / 1048576, 2) AS peak_memory_mb FROM hologres.hg_query_log WHERE query_start >= now() - interval '1 day' AND usename != 'system' AND cpu_time_ms IS NOT NULL GROUP BY usename, warehouse_name ORDER BY sum(cpu_time_ms) DESC LIMIT 20"
```

## 耗时分布分析

### Query 耗时分布（过去1天）

```bash
hologres sql run --no-limit-check "SELECT CASE WHEN duration < 1000 THEN '< 1s' WHEN duration < 5000 THEN '1-5s' WHEN duration < 30000 THEN '5-30s' WHEN duration < 60000 THEN '30s-1min' WHEN duration < 300000 THEN '1-5min' ELSE '> 5min' END AS duration_bucket, count(1) AS query_count, round(avg(cpu_time_ms)::numeric / 1000, 2) AS avg_cpu_sec FROM hologres.hg_query_log WHERE query_start >= now() - interval '1 day' AND usename != 'system' GROUP BY 1 ORDER BY min(duration)"
```

输出解读：
- 大量 Query 集中在 `> 5min` 表示存在严重慢查询
- 关注 `5-30s` 和 `30s-1min` 区间，优化空间最大

## 查看具体慢 SQL 执行计划

找到目标 SQL 后，使用 `hologres sql explain` 分析执行计划：

```bash
# 查看执行计划
hologres sql explain "SELECT ... FROM ... WHERE ..."
```

## 诊断输出模板

```
慢 SQL 1：
QueryID：{sample_query_id}（示例）
SQL 指纹：{sql_digest}
执行次数：{exec_count} 次 / 天
平均 CPU：{avg_cpu_sec} 秒  |  累计 CPU：{total_cpu_sec} 秒
平均内存：{avg_memory_mb} MB  |  峰值内存：{peak_memory_mb} MB
原因：{基于 SQL 内容分析原因}
优化建议：
  1. 添加分区裁剪条件（减少扫描量）
  2. 检查是否缺少 bitmap/clustering key 索引
  3. 使用 hologres sql explain 查看执行计划
  4. 考虑降低执行频率或合并查询

慢 SQL 2：
...
```
