# Stage 1 — 内存水位采集与形态分级

云监控拉取内存时序并归入四种形态之一。`{prefix}` 由实例类型判定（见 [preconditions.md §4](preconditions.md)）。

## 1.1 实例整体内存时序

```bash
hologres metric query {prefix}memory_usage \
    --instance-id {instance_id} \
    --start-time {start_time} --end-time {end_time} --period 60
```

## 1.2 最新快照（快速健康检查）

```bash
hologres metric latest {prefix}memory_usage --instance-id {instance_id} --period 60
```

## 1.3 各 Worker 内存分布

```bash
hologres metric query {prefix}memory_usage_by_worker \
    --instance-id {instance_id} \
    --start-time {start_time} --end-time {end_time} --period 60
```

## 1.4 OOM 事件检测（通过 hg_query_log 补充）

```bash
hologres sql run --no-limit-check "SELECT count(*) AS oom_count FROM hologres.hg_query_log WHERE query_start >= '{start_time}'::timestamptz AND query_start < '{end_time}'::timestamptz AND status = 'FAILED' AND (message ILIKE '%out of memory%' OR message ILIKE '%OOM%')"
```

## 1.5 形态分级

| 状态 | 触发条件 | 后续 |
|------|----------|------|
| 🔴 全局高 | 所有 Worker 内存 P95 > 85% | 第二阶段分类 |
| 🟠 局部倾斜 | `Max Worker - Avg Worker > 20%` 或绝对差值大 | 主线 B（倾斜） |
| 🟡 持续不回落 | 低峰基线环比涨 > 10% 且不恢复 | 主线 D（泄漏 / 缓存滞留） |
| 🟢 健康 | 平稳，30%–50% 余量 | 跳过归因，出健康报告 |

### 形态信号

- **Spike**：< 1h 突刺后回落 → 突发查询 / 写入。
- **Plateau**：> 4h 持续高位不恢复 → 疑似泄漏或配置不当。

### 基线校准

- 空闲期 30%–50% 正常；长期 > 80% 异常。
