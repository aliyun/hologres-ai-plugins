# Q3 计算资源诊断 — 详细指标查询

本文档包含日报中 Q3（计算资源是否紧张）诊断所需的详细指标查询命令和判断逻辑。

> **前置准备**：
>
> ```bash
> export HOLOGRES_SKILL=hologres-daily-report
> ```
>
> 需要已配置云监控凭证：`hologres metric config --access-key-id <AK> --access-key-secret <SK>`

---

## 指标名称前缀约定

> 引用 **hologres-diagnosis-cpu** skill 的前缀规则。

先获取实例类型以确定指标前缀：

```bash
hologres instance-manage get
```

根据返回的实例类型确定前缀 `{prefix}`：

| 实例类型（instanceType） | 前缀 |
|--------------------------|------|
| Standard / 通用型 | `standard_` |
| Warehouse / 计算组型 | `warehouse_` |
| Follower / 只读从实例 | `follower_` |
| Serverless | `serverless_` |
| Shared / 共享型 | `shared_` |

以下命令中 `{prefix}` 替换为实际前缀，`{report_date}` 替换为报告日期（如 `2026-04-27`）。

---

## 1. CPU 使用率

### 1.1 时序查询（24h，60s 粒度）

```bash
hologres metric query {prefix}cpu_usage \
  --start "{report_date}T00:00:00" \
  --end "{report_date}T23:59:59" \
  --period 60
```

### 1.2 最新值快照

```bash
hologres metric latest {prefix}cpu_usage
```

### 1.3 按 Worker 节点查询

```bash
hologres metric query {prefix}cpu_usage_by_worker \
  --start "{report_date}T00:00:00" \
  --end "{report_date}T23:59:59" \
  --period 60
```

**输出解读**：
- 时序数据为 JSON 数组，每个数据点包含 `timestamp` 和 `value`
- 从时序数据中计算：avg（平均值）、P95、max（峰值）
- 识别 CPU 峰值出现的时间段

**诊断逻辑**：
1. 计算每个 60s 窗口的 CPU 值
2. 按小时聚合，找出是否有连续 1 小时 P95 > 90% 的情况
3. 如果有，判定为"CPU 紧张"
4. 如果 Worker 级别数据显示某节点 CPU 远高于其他节点（> 1.5 倍均值），标记为"CPU 热点"

---

## 2. 内存使用率

```bash
hologres metric query {prefix}memory_usage \
  --start "{report_date}T00:00:00" \
  --end "{report_date}T23:59:59" \
  --period 60
```

**诊断逻辑**：
1. 同 CPU，计算 avg / P95 / max
2. 连续 1 小时 P95 > 90% → 内存紧张
3. 结合 Q4（SQL 诊断）中的 OOM 事件判断是否存在内存溢出

**OOM 事件检测**（通过 hg_query_log 补充）：

```bash
hologres sql run --no-limit-check "SELECT count(*) as oom_count FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'FAILED' AND (message ILIKE '%out of memory%' OR message ILIKE '%OOM%')"
```

---

## 3. 连接数

```bash
hologres metric query {prefix}connections \
  --start "{report_date}T00:00:00" \
  --end "{report_date}T23:59:59" \
  --period 60
```

**诊断逻辑**：
1. 获取最大连接数上限：`hologres sql run "SHOW max_connections"`
2. 计算连接使用率 = 连接数 / max_connections
3. 连续 10 分钟使用率 > 90% → 连接紧张
4. 连接数瞬时跌至 0 → 严重异常

---

## 4. 查询延迟

### 4.1 云监控查询延迟

```bash
hologres metric query {prefix}query_latency \
  --start "{report_date}T00:00:00" \
  --end "{report_date}T23:59:59" \
  --period 60
```

### 4.2 通过 hg_query_log 计算 P99

```bash
# 当日查询延迟分布
hologres sql run --no-limit-check "SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY duration) as p50, percentile_cont(0.95) WITHIN GROUP (ORDER BY duration) as p95, percentile_cont(0.99) WITHIN GROUP (ORDER BY duration) as p99, avg(duration) as avg_duration, max(duration) as max_duration, count(*) as total_queries FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'SUCCESS' AND usename <> 'system' AND duration > 0"
```

### 4.3 与前一日同期对比

```bash
# 前一日查询延迟 P99
hologres sql run --no-limit-check "SELECT percentile_cont(0.99) WITHIN GROUP (ORDER BY duration) as p99_yesterday FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz - interval '1 day' AND query_start < '{report_date} 00:00:00'::timestamptz AND status = 'SUCCESS' AND usename <> 'system' AND duration > 0"
```

**诊断逻辑**：
1. 计算当日 P99 和前一日 P99
2. 涨幅 = (当日 P99 - 前日 P99) / 前日 P99 × 100%
3. 涨幅 > 50% → "查询延迟明显波动"

---

## 5. 查询 QPS

```bash
hologres metric query {prefix}query_qps \
  --start "{report_date}T00:00:00" \
  --end "{report_date}T23:59:59" \
  --period 60
```

**输出解读**：
- 用于了解业务负载水平
- 结合 CPU 使用率判断：QPS 增长但 CPU 不涨 = 查询轻量化；QPS 不变但 CPU 涨 = 查询变重

---

## 6. Query Queue（排队）

### 6.1 云监控查询

> 使用 **coordinator-query-queue-analyzer** skill 的指标（如可用）。

```bash
# 搜索可用的 Queue 相关指标
hologres metric list --search queue
```

### 6.2 通过 pg_stat_activity 检测排队

```bash
# 当前等待中的查询
hologres sql run --no-limit-check "SELECT count(*) as queued_queries, max(now() - query_start) as max_queue_time FROM pg_stat_activity WHERE state = 'active' AND wait_event_type = 'Lock' AND backend_type = 'client backend'"
```

**诊断逻辑**：
- 队列长度 > 0 且平均排队时间 > 500ms → Query Queue 紧张
- 排队时间 > 5s → 严重

---

## 诊断阈值汇总

| 检查项 | 关键指标 | 正常 | 关注 | 紧张/异常 |
|--------|---------|------|------|----------|
| CPU | avg / P95 / max | avg < 50% | avg 50-70%, P95 < 90% | 连续 1h P95 > 90% |
| 内存 | avg / P95 / max + OOM | avg < 60% | avg 60-80%, P95 < 90% | 连续 1h P95 > 90% 或有 OOM |
| 连接数 | 使用率 | < 70% | 70-90% | 连续 10min > 90% |
| 查询延迟 | P99 环比 | 波动 < 20% | 波动 20-50% | 上涨 > 50% |
| Query Queue | 队列长度 + 排队时间 | 无排队 | 有排队 < 500ms | 排队 > 500ms |

## 诊断输出模板

```
### 结论
{一句话判定，如：计算资源处于"轻度紧张"状态，高峰期 CPU 和 Query Queue 同时承压}

### 关键事实
| 维度 | 指标 | 平均值 | P95 | 峰值 | 诊断阈值 | 状态 |
|------|------|--------|-----|------|----------|------|
| CPU | 利用率 | XX% | XX% | XX% | 连续1h > 90% | {状态} |
| 内存 | 利用率 | XX% | XX% | XX% | 连续1h > 90% | {状态} |
| 连接 | 使用率 | XX% | XX% | XX% | 连续10min > 90% | {状态} |
| 查询延迟 | P99 耗时 | XXms | XXms | XXms | 较前日上涨 > 50% | {状态} |
| Query Queue | 队列长度/排队时间 | XX/XXms | XX/XXms | XX/XXms | 有排队且 > 500ms | {状态} |

### 分析
{逐项分析，解释异常原因、关联因素、影响范围}

### 建议
- {具体可执行建议，含优先级和时间要求}
```
