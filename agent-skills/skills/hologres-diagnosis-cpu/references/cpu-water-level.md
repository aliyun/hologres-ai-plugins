# Stage 1 — CPU 水位采集与分级

确定 `{prefix}`（见 [preconditions.md §5](preconditions.md)）后，按 warehouse 粒度拉取 CPU 时序并分级。

## 1.1 CPU 时序（warehouse 粒度）

```bash
hologres metric query {prefix}cpu_usage \
    --instance-id {instance_id} \
    --start-time {start_time} --end-time {end_time} --period 60
```

数据点字段（JSON，顶层数组）：

```json
{"timestamp": 1747641600000, "userId": "xxx", "instanceId": "hgprecn-cn-xxx", "warehouseId": "wh_default", "Maximum": 95.2, "Average": 78.1, "Minimum": 60.4}
```

## 1.2 CPU 最新点（快速健康检查）

```bash
hologres metric latest {prefix}cpu_usage --instance-id {instance_id} --period 60
```

## 1.3 状态分级（per warehouse）

| 状态 | 判定条件 | 后续 |
|------|----------|------|
| 🔴 持续打满 | `Max(CPU) = 100%` 且持续 `> 5 min` | 进入 Stage 2 归因 |
| 🟠 持续高位 | `Max(CPU) > 80%` 且持续 `> 15 min` | 进入 Stage 2 归因 |
| 🟢 安全平稳 | `30% < Max(CPU) < 80%` | 跳过归因，出健康报告 |
| ⚪ 低水位 | `Max(CPU) < 30%` | 跳过归因，提示资源利用率偏低 |

> 判定按 **warehouse 粒度** 分别进行。任一 warehouse 命中 🔴 / 🟠 即进入 Stage 2。
