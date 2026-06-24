---
name: hologres-diagnosis-cpu
depends: [hologres-cli]
description: >
  Hologres 实例 CPU 使用率异常诊断技能。当用户提到 CPU 打满、CPU 持续高位、Worker CPU 不均、负载诊断、CPU 归因分析、后台 Compaction 干扰等场景时使用。
  以 instance_id + 时间窗口为输入，自动完成 CPU 状态分级（持续打满 / 持续高位 / 安全平稳）、四象限归因诊断（宏观定性 / 分布定位 / 查询归因 / 后台任务干扰），并输出结构化的 Markdown 诊断报告与治理行动清单。
  云监控数据通过 `hologres metric query` / `hologres metric latest` 获取；元仓与 PG 系统表数据通过 `hologres sql run` 获取，全程享有 hologres-cli 的安全护栏、JSON 结构化输出与自动错误重试能力。
---

> ⚠️ **执行前就绪检查（所有诊断步骤之前完成）**：
> 1. 已 `pip install hologres-cli`，且 `hologres status` 能连通目标实例（连接哪个实例 / 库由当前 profile 决定，可用 `--profile <name>` 切换）。
> 2. 云监控 AK/SK 已就绪（`hologres metric config` 专用配置，或 profile 通用 AK/SK，或默认凭证链）。
> 3. `export HOLOGRES_SKILL=hologres-diagnosis-cpu`，便于事后审计。
>
> 完整就绪细节（安装 / 凭证优先级 / RAM 权限 / 前缀判定 / 时间格式）见 [references/preconditions.md](references/preconditions.md)。

# Hologres CPU 使用率诊断

按「云监控水位 → 宏观定性 → 分布定位 → 查询归因 → 后台干扰」自动化归因 CPU 异常（打满 / 持续高位），输出结构化 Markdown 诊断报告。

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `instance_id` | 是 | Hologres 实例 ID，例如 `hgprecn-cn-xxx`（传给 `hologres metric` 的 `--instance-id`） |
| `start_time` | 是 | 诊断开始时间，ISO-8601（如 `2025-05-19T10:00:00`）或 epoch 毫秒 |
| `end_time` | 是 | 诊断结束时间，格式同 `start_time` |
| `region` | 否 | 云监控 Region，默认从 profile 的 `region_id` 自动读取；可用 `--region` 覆盖 |

> 数据库由当前 profile 的 `database` 决定，无需也无法在命令上指定 `--db-name`；如需换库用 `hologres config set database <db>` 或 `--profile <name>`。

### 时间窗口约束

CPU 诊断只分析 **最近 30 天内、且跨度不超过 7 天** 的数据。校验规则（按顺序执行）：

1. **30 天有效期**：`start_time` 必须满足 `start_time >= current_time - 30d`（`hg_query_log` 默认保留 30 天）。若早于 30 天前，**拒绝执行**并提示：
   > ⚠️ 诊断时间范围超出 hg_query_log 保留期（30 天），请重新指定 start_time >= {30天前日期}。
2. **7 天跨度上限**：若 `end_time - start_time > 7天`，使用 `AskUserQuestion` 工具引导用户收窄：

   ```
   AskUserQuestion:
     question: "当前时间跨度超过 7 天，CPU 诊断只能分析最近 30 天内的 7 天范围数据。请选择要分析的时间窗口："
     options:
       - label: "最近 7 天"
         description: "分析 end_time 前 7 天的数据"
       - label: "最近 3 天"
         description: "分析 end_time 前 3 天的数据"
       - label: "最近 1 天"
         description: "分析 end_time 前 1 天的数据"
   ```

   按用户选择重设 `start_time = end_time - N天`；若用户用 "Other" 自填，校验跨度 ≤ 7 天且 ≥ 30 天前。

> 时间窗口长度决定「短周期 / 长周期」分支：`<24h` 短周期，`>24h` 长周期。

## hologres-cli 约定

- 元仓 / PG 系统表查询统一用 `hologres sql run --no-limit-check "<SQL>"`（聚合诊断无需 LIMIT 保护）。
- 云监控指标用 `hologres metric query <metric> --instance-id <id> --start-time <s> --end-time <e> --period <p>`（区间）/ `hologres metric latest <metric> --instance-id <id> --period <p>`（最新点）；`instanceId` 由 CLI 自动注入，无需手填 `--dimensions`。
- 指标名前缀（`standard_` / `warehouse_` / ...）不会被 CLI 自动添加，需由「前置：实例类型判定」结果拼进 metric 名（见 preconditions §5）。
- 连接层已自动 `SET hg_computing_resource = 'serverless'`；来源标记由 `export HOLOGRES_SKILL` 注入 `application_name`，**无需** 在 SQL 里手写 `SET ...` 前缀。
- 输出 `digest` / `query_id` / `query` 时必须保留完整内容，**禁止** 使用 `left()` / `substr()` / `::char(N)` / `...` 截断；长 SQL 换行展示。
- 独立的指标 / SQL 命令可在同一轮并行下发以加速。

## 诊断主流程

```
前置：实例类型自动判断
  └── hologres instance-manage get → data.Instance.InstanceType → {prefix}（见 preconditions §5）

Stage 1 — CPU 水位采集 + 状态分级（per warehouse）
  ├── 🔴 持续打满 / 🟠 持续高位 → Stage 2
  └── 🟢 安全平稳 / ⚪ 低水位   → 直接出健康报告

Stage 2 — 四象限归因（独立命令并行）
  ├── Q1 宏观定性：业务增长 vs 异常瓶颈
  ├── Q2 分布定位：全局高 vs 局部高
  ├── Q3 查询归因：大 Query / 长 Query / 锁竞争 / 高频小 Query
  └── Q4 后台干扰：Compaction 写放大 / DDL 变更

Stage 3 — 综合输出 Markdown 诊断报告
```

### 前置 — 实例类型自动判断

```bash
hologres instance-manage get
```

从返回 JSON 的 `data.Instance.InstanceType` 映射出 `{prefix}`（`Warehouse`→`warehouse_`、`Standard`→`standard_`、`Follower`→`follower_`、`Serverless`→`serverless_`、`Shared`→`shared_`）。后续所有指标名的 `{prefix}` 均由此确定。

### Stage 1 — 水位采集与分级

详见 [references/cpu-water-level.md](references/cpu-water-level.md)。

下发 `hologres metric query {prefix}cpu_usage --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60`，按 warehouse 粒度对照 🔴/🟠/🟢/⚪ 分级表。任一 warehouse 命中 🔴/🟠 进入 Stage 2。

### Stage 2 — 四象限归因

详见 [references/quadrant-attribution.md](references/quadrant-attribution.md)。每个象限内的独立命令并行下发：

- **Q1**：CMS 取 `{prefix}query_qps`、`{prefix}dml_rps`、`{prefix}query_latency`，判定 *正常增长* / *异常瓶颈* / *拥塞*。
- **Q2**：CMS 取 `{prefix}cpu_usage_by_worker` + `hg_worker_info` SQL + `pg_stat_activity` SQL，判定 *物理倾斜*（shard 数偏差）或 *局部热点*（单 worker CPU）。
- **Q3**：`hg_query_log` 按 `cpu_time_ms` Top-10；`pg_stat_activity` 长查询；`pg_locks` 锁链；`digest` 高频小查询。
- **Q4**：CMS 取 `{prefix}compaction_duration` / `{prefix}compaction_num` + `hg_query_log` DDL 审计（过滤 `bitmap_columns` / `dictionary_encoding_columns` / `clustering_key`）。基线激增 > 50% 且邻近属性 DDL → **写放大**。

### Stage 3 — 输出报告

套用 [references/report-template.md](references/report-template.md) 的 Markdown 骨架，所有占位符必须用真实查询结果填充，不得编造。

## 执行指导

执行顺序：

0. `hologres instance-manage get` —— 取一次，确定 `{prefix}`。
1. Stage 1 —— `{prefix}cpu_usage` 时序 → 状态分级。
2.（若 🔴/🟠）Stage 2 —— 在同一轮内并行下发 Q1 + Q2 + Q3 + Q4 中相互独立的命令。
3. Stage 3 —— 汇总出报告。

错误处理（CLI 返回结构化错误，按 `retryable` 字段决定）：

| 场景 | 动作 |
|------|------|
| 网络超时 / 连接错误（`retryable: true`） | 等 3 秒重试一次 |
| 权限不足 | 提示用户核对 PG 权限 / 云监控 RAM 策略 |
| 参数错误 | 核对时间格式、`--instance-id`、metric 名前缀 |
| 云监控限流（`API_ERROR`） | 等 5 秒重试 |
| 依赖缺失（`DEPENDENCY_MISSING`） | `pip install 'hologres-cli[cms]'` |
| 凭证错误（`CREDENTIAL_ERROR`） | `hologres metric config` 配置专用 AK/SK，或 profile 通用 AK/SK |
| **CLI 返回空结果（无数据）** | **禁止自行改参重试或变通获取；直接跳过该步骤，在输出中标注「无数据」** |

## References

| File | Content |
|------|---------|
| [references/preconditions.md](references/preconditions.md) | 安装 / 凭证优先级 / RAM 权限 / 前缀判定 / 时间格式 |
| [references/cpu-water-level.md](references/cpu-water-level.md) | Stage 1 指标采集 + 状态分级表 |
| [references/quadrant-attribution.md](references/quadrant-attribution.md) | Stage 2 Q1–Q4 SQL 与判定规则 |
| [references/report-template.md](references/report-template.md) | Stage 3 Markdown 报告骨架 |
| [references/thresholds.md](references/thresholds.md) | 数据源映射 + 异常阈值 |

## 注意事项

1. `hologres.hg_query_log` 默认保留 30 天、单次最多返回 10000 条；查询必须带 `query_start` 范围条件，避免全表扫描。
2. 元仓 SQL 不要对 `query_start` 套 `to_char(...)` 等表达式条件（无法走索引）。
3. 云监控 `period` 推荐 `60`（细粒度）或 `300`（长周期）；跨度大时用 `300` 减少数据点。
4. 时间格式建议 ISO-8601（`2025-05-19T10:00:00`）；`hologres metric` 对无时区 ISO 串按 UTC 解析，北京时间可显式带 epoch 毫秒或注意时区换算。
5. `digest` 字段自 V2.2 起支持，低版本实例为空，需降级为按 `query` 文本聚合。
6. `cpu_usage_by_worker` 等 Worker 粒度指标在多 Warehouse 场景下需结合 `warehouse` dimension 过滤。
7. 所有 `hologres metric` / `hologres sql run` 返回 JSON：SQL 结果在 `data.rows`，云监控数据点在顶层数组（datapoint 含 `timestamp` / `Average` / `Maximum` / `Minimum` 等）。
8. 健康评分与状态仅供参考，根因以四象限累积证据为准。
