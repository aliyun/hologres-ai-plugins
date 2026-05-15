# Warehouse 资源监控

所有 SQL 通过 `hologres sql run` 执行，返回结构化 JSON：`{"ok": true, "data": {"rows": [...], "count": N}}`

执行前设置 SQL tracking：

```bash
export HOLOGRES_SKILL=hologres-instance-health-analyse
```

## 连接数分析

### 查看各 Warehouse 的活跃连接数

```bash
hologres sql run --no-limit-check "SELECT warehouse_name, state, count(1) AS conn_count, count(CASE WHEN wait_event IS NOT NULL THEN 1 END) AS waiting, count(CASE WHEN state = 'active' THEN 1 END) AS active, count(CASE WHEN state = 'idle' THEN 1 END) AS idle FROM pg_stat_activity WHERE usename != 'system' AND datname IS NOT NULL GROUP BY warehouse_name, state ORDER BY warehouse_name, count(1) DESC"
```

输出解读：
- `conn_count`：该 Warehouse + state 下的连接总数
- `waiting`：有 wait_event 的连接（可能等待锁/资源）
- `active`：正在执行 SQL 的连接
- `idle`：空闲连接

### 查看等待中的 Query（等待锁或资源）

```bash
hologres sql run --no-limit-check "SELECT pid, usename, warehouse_name, state, wait_event_type, wait_event, now() - query_start AS wait_duration, left(query, 100) AS sql_snippet FROM pg_stat_activity WHERE wait_event IS NOT NULL AND state = 'active' AND usename != 'system' ORDER BY query_start ASC"
```

输出解读：
- `wait_event_type`：等待类型（Lock / IO / Client 等）
- `wait_duration`：已等待时长，超过 5 分钟需关注

### 查看长时间运行的 Query（超过5分钟）

```bash
hologres sql run --no-limit-check "SELECT pid, usename, warehouse_name, now() - query_start AS run_duration, state, wait_event, left(query, 150) AS sql_snippet, query_start FROM pg_stat_activity WHERE state = 'active' AND query_start < now() - interval '5 min' AND usename != 'system' ORDER BY query_start ASC"
```

输出解读：
- 结果为空表示无长时间 Query，状态正常
- 有结果时关注 `run_duration` 和 SQL 内容，评估是否需要终止

### 查看各用户连接数分布

```bash
hologres sql run "SELECT usename AS username, warehouse_name, count(1) AS conn_count, count(CASE WHEN state = 'active' THEN 1 END) AS active FROM pg_stat_activity WHERE usename != 'system' GROUP BY usename, warehouse_name ORDER BY count(1) DESC LIMIT 30"
```

### 查看各应用连接数分布

```bash
hologres sql run "SELECT application_name, warehouse_name, count(1) AS conn_count, count(CASE WHEN state = 'active' THEN 1 END) AS active FROM pg_stat_activity WHERE usename != 'system' GROUP BY application_name, warehouse_name ORDER BY count(1) DESC LIMIT 30"
```

## 实时 Query 负载分析

### 查看当前正在执行的 Query

```bash
hologres sql run --no-limit-check "SELECT pid, usename, warehouse_name, application_name, now() - query_start AS running_time, state, left(query, 200) AS sql_snippet FROM pg_stat_activity WHERE state = 'active' AND usename != 'system' ORDER BY query_start ASC"
```

### 过去1小时 Query 量趋势（按10分钟统计）

```bash
hologres sql run --no-limit-check "SELECT date_trunc('hour', query_start) + floor(extract(minute FROM query_start) / 10) * interval '10 min' AS time_bucket, warehouse_name, count(1) AS query_count, round(avg(duration)::numeric / 1000, 2) AS avg_duration_sec, sum(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) AS failed_count FROM hologres.hg_query_log WHERE query_start >= now() - interval '1 hour' GROUP BY 1, 2 ORDER BY 1, 2"
```

输出解读：
- `failed_count > 10`：触发报错分析流程
- `avg_duration_sec` 持续升高：可能存在资源瓶颈

### 过去3小时每小时 Query 访问量

```bash
hologres sql run --no-limit-check "SELECT date_trunc('hour', query_start) AS hour, count(1) AS query_count, round(sum(read_bytes)::numeric / 1073741824, 2) AS read_gb, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec FROM hologres.hg_query_log WHERE query_start >= now() - interval '3 h' GROUP BY 1 ORDER BY 1"
```

### 与昨天同时段对比（判断流量异常）

```bash
hologres sql run --no-limit-check "SELECT query_date, count(1) AS query_count, round(sum(read_bytes)::numeric / 1073741824, 2) AS read_gb, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec FROM hologres.hg_query_log WHERE query_start >= now() - interval '3 h' GROUP BY query_date UNION ALL SELECT query_date, count(1) AS query_count, round(sum(read_bytes)::numeric / 1073741824, 2) AS read_gb, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec FROM hologres.hg_query_log WHERE query_start >= now() - interval '1d 3h' AND query_start <= now() - interval '1d' GROUP BY query_date ORDER BY 1"
```

输出解读：
- 对比两天同时段数据，若今日 `query_count` 或 `total_cpu_sec` 显著高于昨日，说明流量异常

## 诊断结论参考

| 指标 | 正常范围 | 告警阈值 | 处理建议 |
|------|----------|----------|----------|
| 单 Warehouse 活跃连接 | < 100 | > 200 | 检查连接池配置，排查长连接 |
| 等待中 Query 数 | 0 | > 10 | 检查锁等待、资源争抢 |
| 单 Query 运行时长 | < 30s | > 5min | 终止并优化该 SQL |
| 每小时 FAILED 数 | 0 | > 10 | 触发报错分析流程 |
