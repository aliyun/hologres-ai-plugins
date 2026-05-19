---
name: hologres-diagnosis-cpu
depends: [hologres-cli]
description: >
  Hologres 实例 CPU 使用率异常诊断技能。当用户提到 CPU 打满、CPU 持续高位、Worker CPU 不均、负载诊断、CPU 归因分析、后台 Compaction 干扰等场景时使用。
  以 instance_id + 时间窗口为输入，自动完成 CPU 状态分级（持续打满 / 持续高位 / 安全平稳）、四象限归因诊断（宏观定性 / 分布定位 / 查询归因 / 后台任务干扰），并输出结构化的 Markdown 诊断报告与治理行动清单。
  云监控数据通过 `hologres metric query` / `hologres metric latest` 获取；元仓与 PG 系统表数据通过 `hologres sql run` 获取，全程享有 hologres-cli 的安全护栏、JSON 结构化输出与自动错误重试能力。
---

# Hologres CPU 使用率诊断

系统性诊断 Hologres 实例 CPU 异常（打满 / 持续高位），按照「云监控水位 → 宏观定性 → 分布定位 → 查询归因 → 后台干扰」的链路自动化归因，并输出结构化诊断报告。

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `instance_id` | 是 | Hologres 实例 ID，例如 `hgprecn-cn-xxx` |
| `start_time` | 是 | 诊断开始时间，ISO-8601 格式（如 `2025-05-19T10:00:00`）或 epoch 毫秒 |
| `end_time` | 是 | 诊断结束时间，ISO-8601 格式或 epoch 毫秒 |
| `region` | 否 | 云监控 Region，自动从 config profile 的 `region_id` 读取，无需手动指定；也可通过 `--region` 显式覆盖 |

> 时间窗口长度决定了「短周期 / 长周期」分支阈值：`<24h` 为短周期，`>24h` 为长周期。

## 指标名称前缀约定

Hologres 云监控指标名称包含 **产品类型前缀**，使用时必须根据实例类型添加对应前缀：

| 实例类型 | 前缀 | 示例 |
|----------|------|------|
| 计算组（Warehouse） | `warehouse_` | `warehouse_cpu_usage` |
| 通用型（Standard） | `standard_` | `standard_cpu_usage` |
| 从实例（Follower） | `follower_` | `follower_cpu_usage` |
| Serverless 型 | `serverless_` | `serverless_cpu_usage` |
| 湖仓加速型（Shared） | `shared_` | `shared_cpu_usage` |

## 诊断主流程

```
第一阶段：CPU 水位采集 + 状态分级
   ├── 持续打满 / 持续高位 → 第二阶段（归因）
   └── 安全平稳         → 直接出具「健康」报告

第二阶段：四象限归因
   ├── Q1 宏观定性：业务增长 vs 异常瓶颈
   ├── Q2 分布定位：全局高 vs 局部高（Worker / Shard）
   ├── Q3 查询归因：大 Query / 锁竞争 / 长 Query
   └── Q4 后台干扰：Compaction 写放大 / DDL 变更

第三阶段：综合输出诊断报告（Markdown）
```

## 前提条件

### 1. 安装 hologres-cli

```bash
pip install hologres-cli
```

### 2. 配置 Hologres 连接

```bash
hologres config          # 交互式向导
hologres status          # 验证连接
```

### 3. 配置阿里云凭证（用于云监控）

云监控 API 的 AK/SK 支持 **metric 专用配置**，推荐使用 `hologres metric config` 单独配置，与 Hologres 连接凭证互不影响：

```bash
# 推荐：为 metric 命令单独配置 AK/SK
hologres metric config --access-key-id <your_ak> --access-key-secret <your_sk>

# 或交互式配置
hologres metric config
```

若未配置 metric 专用凭证，则**回退读取 `hologres config` 配置的通用 AK/SK**（即 `~/.hologres/config.json` 中当前 profile 的 `access_key_id` / `access_key_secret`，敏感字段加密存储）：

```bash
hologres config         # 交互式向导，会引导填入 AK/SK
```

若 profile 中均未配置 AK/SK，则回退到阿里云默认凭证链，可通过环境变量等方式提供：

```bash
# 仅在 profile 未配置 AK/SK 时作为回退方式
export ALIBABA_CLOUD_ACCESS_KEY_ID=<your_ak>
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=<your_sk>
# 也支持 STS / RAM 角色等 alibabacloud-credentials 默认凭证链方式
```

> 凭证解析优先级：`hologres metric config` 专用 AK/SK > `hologres config` 通用 AK/SK > 环境变量 > SDK 凭证文件 > ECS RAM 角色。

### 4. 权限要求

- Hologres 侧：Superuser 或 `pg_read_all_stats` 权限（读取 `hg_query_log`、`hg_worker_info` 等系统表）
- 云监控侧：账号具备 `cms:DescribeMetricList` / `cms:DescribeMetricLast` 调用权限

```bash
hologres sql run "SELECT current_user, usesuper FROM pg_user WHERE usename = current_user"
```

### 5. 设置 SQL Tracking

```bash
export HOLOGRES_SKILL=hologres-diagnosis-cpu
```

所有诊断 SQL 会带上 `application_name = "hologres-cli/hologres-diagnosis-cpu"`，便于事后审计。

---

## 第一阶段：CPU 水位采集与状态分级

调用云监控获取 `instance_id` 下各 Warehouse 粒度的 CPU 使用率时间序列，并据此对实例 CPU 状态进行分类。

### 1.1 获取 CPU 时间序列（按 Warehouse 粒度）

```bash
# 时间窗口内的 CPU 使用率曲线（建议 period=60 秒）
# 注意：指标名需加产品类型前缀，如通用型为 standard_cpu_usage，计算组为 warehouse_cpu_usage
hologres metric query {prefix}_cpu_usage \
    --instance-id {instance_id} \
    --start-time {start_time} \
    --end-time {end_time} \
    --period 60
```

返回数据点字段（JSON）：

```json
{"timestamp": 1747641600000, "userId": "xxx", "instanceId": "hgprecn-cn-xxx", "warehouseId": "wh_default", "Maximum": 95.2, "Average": 78.1, "Minimum": 60.4}
```

### 1.2 获取 CPU 最新点（快速健康检查）

```bash
hologres metric latest {prefix}_cpu_usage --instance-id {instance_id} --period 60
```

### 1.3 CPU 状态分级（按 Warehouse 分别判定）

| 状态 | 判定条件 | 后续动作 |
|------|----------|----------|
| 🔴 持续打满 | `Max(CPU) = 100%` 且持续时间 `> 5 min` | 进入第二阶段全量归因 |
| 🟠 持续高位 | `Max(CPU) > 80%` 且持续时间 `> 15 min` | 进入第二阶段全量归因 |
| 🟢 安全平稳 | `30% < Max(CPU) < 80%` | 跳过归因，输出健康报告 |
| ⚪ 低水位 | `Max(CPU) < 30%` | 跳过归因，提示资源利用率偏低 |

> **判定要点**：必须基于 Warehouse 粒度分别判定。任一 Warehouse 命中 🔴/🟠 都需进入归因。

---

## 第二阶段：四象限归因诊断

### Q1：宏观定性 —— 业务增长 vs 异常瓶颈

**目标**：先判断 CPU 上涨是否由业务自然增长引起。若 QPS/RPS 同比增长且延迟无恶化，则属于「正常增长」；若业务平稳但 CPU 异常上涨，则属于「异常瓶颈」，需进一步归因。

#### 数据源

- 云监控指标：`{prefix}_query_qps`（QPS）、`{prefix}_dml_rps`（DML RPS）、`{prefix}_query_latency`（SQL 延迟）

#### 执行命令

```bash
# QPS 时间序列（以通用型为例，计算组前缀为 warehouse_）
hologres metric query {prefix}_query_qps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

# DML RPS 时间序列
hologres metric query {prefix}_dml_rps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

# 延迟时间序列
hologres metric query {prefix}_query_latency \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60
```

#### 判断逻辑

| 现象 | 结论 | 后续动作 |
|------|------|----------|
| CPU↑ + QPS/RPS 同比例↑ + 延迟无恶化 | **正常业务增长** | 评估扩容；可中止归因 |
| CPU↑ 但 QPS/RPS 平稳 / 下降 | **异常瓶颈** | 继续 Q2 / Q3 / Q4 |
| CPU↑ + QPS 平稳 + 延迟显著恶化 | **存在拥塞** | 重点排查 Q3（大 Query / 锁） |

#### 异常阈值

| 时间窗口 | 维度 | 异常阈值 |
|----------|------|----------|
| 短周期（<24h） | CPU 小时均值波动 | `> 30%` |
| 长周期（>24h） | CPU 日均值波动 | `> 10%` |
| 短周期 | SQL Latency 小时波动 | `> 20%` |
| 长周期 | SQL Latency 日均波动 | `> 10%` |

---

### Q2：分布定位 —— 负载分布是否均匀

**目标**：判断 CPU 高位是「全局高」还是「局部高」。
- **全局高** → 整体资源不足，进入通用排查（Q3）
- **局部高** → 排查 Worker / Shard 均衡性

#### 数据源

- 云监控：`{prefix}_cpu_usage_by_worker`（按 Worker 维度的 CPU 使用率，如 `standard_cpu_usage_by_worker`）
- PG 系统表：`hologres.hg_worker_info`（Worker → Shard 映射）

#### 执行命令

```bash
# 各 Worker CPU 分布（云监控按 worker dimension 拆分）
hologres metric query {prefix}_cpu_usage_by_worker \
    --instance-id {instance_id} \
    --start-time {start_time} --end-time {end_time} --period 60
```

```bash
# Worker / Shard 均衡性查询
hologres sql run --no-limit-check "SELECT worker_id, count(shard_id) AS shard_count, array_agg(shard_id) AS shards FROM hologres.hg_worker_info GROUP BY worker_id ORDER BY shard_count DESC"
```

```bash
# 各 Worker 当前活跃 Query 数（结合 pg_stat_activity）
hologres sql run --no-limit-check "SELECT backend_id, warehouse_name, count(1) AS active_queries FROM pg_stat_activity WHERE state = 'active' AND usename != 'system' GROUP BY backend_id, warehouse_name ORDER BY active_queries DESC LIMIT 50"
```

#### 物理不均判定

- Worker 之间 `shard_count` 与平均值差值 **> 1**，或比例偏差 **> 20%** → 判定 **物理不均**
- 单 Worker CPU 显著高于均值（> 平均值 1.5 倍且 > 70%） → 判定 **局部热点**

#### 输出示例

```
Worker CPU 分布：
- worker_0: shards=10, CPU avg=45%
- worker_1: shards=10, CPU avg=92% ⚠️ 局部热点
- worker_2: shards=12, CPU avg=48%（Shard 数偏差 +20%）
```

---

### Q3：查询归因 —— 谁是资源杀手

#### 3.1 大 Query 排查（Top CPU Consumers）

**数据源**：元仓 `hologres.hg_query_log`

```bash
hologres sql run --no-limit-check "SELECT query_id, duration AS duration_ms, cpu_time_ms, query_start, status, usename, warehouse_name, CASE WHEN engine_type IN ('HQE','SDK') AND optimization_cost < 5 THEN 'Fixed Plan' ELSE 'Adaptive' END AS plan_type, query::char(120) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND cpu_time_ms IS NOT NULL AND usename != 'system' ORDER BY cpu_time_ms DESC LIMIT 10"
```

**展示字段**：Query ID、耗时（ms）、CPU 时间（ms）、是否 Fixed Plan、Warehouse、SQL 样本。

#### 3.2 长 Query 与锁竞争排查

**Long Query 判定**：
- 长周期：`Max Duration` 波动 > 10 Hour
- 短周期：`Max Duration > 1 Hour`
- 通用：`Max Duration > 历史最大值 50%` 且 `> 10 min`

```bash
# 当前在执行的长 Query
hologres sql run --no-limit-check "SELECT pid, usename, warehouse_name, state, now() - query_start AS run_duration, wait_event_type, wait_event, left(query, 200) AS sql_snippet FROM pg_stat_activity WHERE state = 'active' AND usename != 'system' AND now() - query_start > interval '10 min' ORDER BY query_start ASC"
```

```bash
# 历史长 Query Top 10
hologres sql run --no-limit-check "SELECT query_id, duration AS duration_ms, cpu_time_ms, query_start, status, usename, warehouse_name, query::char(200) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND duration > 600000 AND usename != 'system' ORDER BY duration DESC LIMIT 10"
```

**锁竞争检测**（结合 `pg_locks`）：

```bash
hologres sql run --no-limit-check "SELECT blocked.pid AS blocked_pid, blocked.usename AS blocked_user, blocked.query::char(120) AS blocked_query, blocking.pid AS blocking_pid, blocking.usename AS blocking_user, blocking.query::char(120) AS blocking_query, now() - blocked.query_start AS wait_duration FROM pg_stat_activity blocked JOIN pg_locks blk_lock ON blocked.pid = blk_lock.pid AND NOT blk_lock.granted JOIN pg_locks bg_lock ON blk_lock.transactionid = bg_lock.transactionid AND bg_lock.granted JOIN pg_stat_activity blocking ON bg_lock.pid = blocking.pid WHERE blocked.usename != 'system' ORDER BY wait_duration DESC LIMIT 50"
```

> 同时建议结合 FixedQE 后端的「拿锁耗时」指标，定位阻塞源 PID 与 SQL。

#### 3.3 高频小 Query 排查

```bash
# 按 SQL 指纹聚合 Top CPU
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(cpu_time_ms)::numeric, 2) AS avg_cpu_ms, round(sum(cpu_time_ms)::numeric / 1000, 2) AS total_cpu_sec, warehouse_name, max(query)::char(120) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND digest IS NOT NULL AND usename != 'system' GROUP BY digest, warehouse_name ORDER BY sum(cpu_time_ms) DESC LIMIT 10"
```

---

### Q4：后台任务干扰

**目标**：判断 CPU 上涨是否由 Compaction 写放大或 DDL 变更引起。

#### 数据源

- 云监控（SE 指标）：`{prefix}_compaction_duration`、`{prefix}_compaction_num`、`{prefix}_se_cpu_usage`
- 元数据：DDL 审计日志（`hologres.hg_query_log` 中 DDL 类查询）

#### 执行命令

```bash
# Compaction 时长曲线
hologres metric query {prefix}_compaction_duration \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

# Compaction 次数曲线
hologres metric query {prefix}_compaction_num \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60
```

```bash
# 时间窗口内的 DDL 变更审计
hologres sql run --no-limit-check "SELECT query_start, usename, query_id, status, query::char(300) AS ddl_sql FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND command_tag IN ('ALTER TABLE','CREATE TABLE','CALL') AND (query ILIKE '%bitmap_columns%' OR query ILIKE '%dictionary_encoding_columns%' OR query ILIKE '%clustering_key%' OR query ILIKE '%segment_key%' OR query ILIKE '%set_table_property%') ORDER BY query_start DESC LIMIT 50"
```

#### Compaction 写放大判定

满足以下任一即判定为 **Compaction 写放大干扰**：
- `compaction_duration` 或 `compaction_num` 曲线相对基线激增 > 50%
- 激增时间点附近（±10 min）有 `bitmap_columns` / `dictionary_encoding_columns` / `clustering_key` 等表属性 DDL 变更

---

## 第三阶段：输出诊断报告

完成第一/二阶段后，输出以下 Markdown 结构化报告。**所有占位符必须基于真实查询结果填充，不得编造。**

```markdown
# Hologres CPU 使用率异常诊断报告

- 实例 ID：{instance_id}
- 诊断时段：{start_time} ~ {end_time}
- 健康评分：{score}/100 | 整体状态：{🔴 持续打满 / 🟠 持续高位 / 🟢 安全平稳}

## 一、今日摘要

> 核心结论：{summary}
> 根因归类：{root_cause}（业务增长 / 大 Query / 锁竞争 / Shard 不均 / Compaction 干扰 / 复合）

- 关键风险：{risks}
- 推荐动作：{actions}

## 二、Q1：宏观定性

| 指标 | 当前窗口 | 同比基线 | 波动 | 是否异常 |
|------|----------|----------|------|----------|
| CPU 均值 | …% | …% | ±…% | … |
| QPS | … | … | ±…% | … |
| RPS | … | … | ±…% | … |
| SQL Latency P99 | … ms | … ms | ±…% | … |

定性结论：{业务增长 / 异常瓶颈 / 拥塞}

## 三、Q2：分布定位

| Worker | Shard 数 | CPU avg | CPU max | 偏差 |
|--------|----------|---------|---------|------|
| worker_0 | … | …% | …% | … |
| worker_1 | … | …% | …% | … |

分布结论：{全局高 / 局部高（Worker N）/ Shard 物理不均}

## 四、Q3：查询归因

### 4.1 Top 10 大 Query（按 CPU 时间）

| QueryID | Duration | CPU(ms) | Warehouse | Plan | SQL 样本 |
|---------|----------|---------|-----------|------|----------|
| … | … | … | … | Fixed/Adaptive | … |

### 4.2 长 Query / 锁源追踪

- 阻塞源 PID：{pid}（用户：{user}）
- 阻塞 SQL：{sql}
- 受阻 Query 数：{n}，最大等待时长：{duration}

## 五、Q4：后台干扰

- Compaction 状态：{正常 / 激增 ×N 倍}
- DDL 变更：{无 / 命中 bitmap_columns 调整 @ {timestamp}}
- 结论：{是否存在写放大干扰}

## 六、治理行动清单

### P0 立即处理
- [ ] {例如：取消阻塞源 PID xxx，释放锁}
- [ ] {例如：终止 Top1 大 Query，避免 CPU 100% 持续}

### P1 近期优化
- [ ] {例如：对 Top SQL 添加分区裁剪或 clustering key}
- [ ] {例如：调整 Compaction 时间窗到业务低峰}

### P2 长期规划
- [ ] {例如：扩容 Warehouse / 拆分读写流量}
- [ ] {例如：建立 CPU 与 Latency 联合告警阈值}
```

---

## 数据支撑来源映射

| 诊断项 | 数据来源 | 获取方式 |
|---------|----------|----------|
| CPU 水位 | 云监控 | `hologres metric query {prefix}_cpu_usage` / `hologres metric latest {prefix}_cpu_usage` |
| QPS / RPS | 云监控 | `hologres metric query {prefix}_query_qps` / `{prefix}_dml_rps` |
| SQL 延迟 | 云监控 | `hologres metric query {prefix}_query_latency` |
| Worker CPU | 云监控 | `hologres metric query {prefix}_cpu_usage_by_worker` |
| 锁等待 | 云监控 + PG 系统表 | `hologres metric` + `hologres sql run`（`pg_locks` + `pg_stat_activity`） |
| 慢 / 长 Query | 元仓 | `hologres sql run`（`hologres.hg_query_log`） |
| Shard 分布 | PG 系统表 | `hologres sql run`（`hologres.hg_worker_info`） |
| Compaction | 云监控 + 元数据 | `hologres metric query {prefix}_compaction_*` + `hg_query_log` DDL 审计 |

## 异常判断阈值配置

| 维度 | 时间窗口 | 异常阈值 |
|------|----------|----------|
| CPU | 长周期（>24h） | 日均值波动 > 10% |
| CPU | 短周期（<24h） | 小时均值波动 > 30% |
| SQL Latency | 长周期 | 日均延迟波动 > 10% |
| SQL Latency | 短周期 | 小时延迟波动 > 20% |
| Long Query | 长周期 | Max Duration 波动 > 10 Hour |
| Long Query | 短周期 | Max Duration > 1 Hour |
| Shard | 实时 | Shard 数偏差 > 1 或 > 20% |
| Compaction | 实时 | duration / num 相对基线激增 > 50% |

## 执行指导

**环境准备**：

```bash
export HOLOGRES_SKILL=hologres-diagnosis-cpu
# 推荐：通过 `hologres metric config` 为 metric 命令单独配置 AK/SK
# hologres metric config --access-key-id <ak> --access-key-secret <sk>
# 也可通过 `hologres config` 在 profile 中配置通用 AK/SK，云监控会自动读取
# 仅当 profile 未配置 AK/SK 时，再使用环境变量作为回退：
# export ALIBABA_CLOUD_ACCESS_KEY_ID=<ak>
# export ALIBABA_CLOUD_ACCESS_KEY_SECRET=<sk>
```

**逐步执行，每步汇报中间结果**：

1. `hologres metric query {prefix}_cpu_usage` —— 获取 CPU 时间序列，做状态分级
2. （若命中打满 / 高位）`hologres metric query {prefix}_query_qps / {prefix}_dml_rps / {prefix}_query_latency` —— Q1 宏观定性
3. `hologres metric query {prefix}_cpu_usage_by_worker` + `hologres sql run`（`hg_worker_info`） —— Q2 分布定位
4. `hologres sql run`（`hg_query_log` Top CPU + `pg_locks` 阻塞链） —— Q3 查询归因
5. `hologres sql run`（DDL 审计） —— Q4 后台干扰
6. 综合 1~5 步结果，按第三阶段模板输出 Markdown 诊断报告

**错误处理**：

CLI 返回结构化错误时，根据 `retryable` 字段决定是否重试：

```json
{"ok": false, "error": {"code": "QUERY_TIMEOUT", "message": "...", "retryable": true, "hint": "..."}}
```

- `retryable: true` → 等待 3 秒后重试一次
- `retryable: false` → 根据 `hint` 调整参数后重试

常见可重试错误：`CONNECTION_ERROR`、`CONNECTION_TIMEOUT`、`QUERY_TIMEOUT`、`QUERY_ERROR`、`API_ERROR`（云监控限流）。

云监控特有错误：

| Code | 说明 | 处理 |
|------|------|------|
| `DEPENDENCY_MISSING` | 缺少 `alibabacloud_cms20190101` 等 SDK | `pip install 'hologres-cli[cms]'` |
| `CREDENTIAL_ERROR` | 凭证未配置或失效 | 通过 `hologres metric config` 配置专用 AK/SK（推荐），或通过 `hologres config` 配置通用 AK/SK，或设置 `ALIBABA_CLOUD_ACCESS_KEY_*` 环境变量作为回退 |
| `API_ERROR` | 云监控 API 调用失败 | 检查 Region / 限流，重试 |
| `INVALID_INPUT` | 时间格式或 dimensions JSON 不合法 | 修正后重试 |

## 注意事项

1. `hologres.hg_query_log` 默认保留一个月，单次最多返回 10000 条；查询必须带 `query_start` 范围条件，避免全表扫描
2. 元仓 SQL 不要使用 `to_char(query_start, ...)` 等表达式条件（无法走索引）
3. 云监控 `period` 推荐 `60s`（细粒度）或 `300s`（长周期）；时间跨度大时使用 `300s` 减少数据点
4. 时间格式建议 ISO-8601（`2025-05-19T10:00:00`），云监控会按 UTC 处理
5. `digest` 字段从 V2.2 起支持，低版本实例为空，需降级为按 `query` 文本聚合
6. `cpu_usage_by_worker` 等 Worker 粒度指标在多 Warehouse 场景下需结合 `warehouse` dimension 过滤
7. 所有 `hologres metric` / `hologres sql run` 返回 JSON，结果在 `data.rows`（SQL）或顶层数组（云监控数据点）
8. 使用 `--no-limit-check` 跳过 LIMIT 检查（聚合诊断查询无需 LIMIT 保护）

## 参考命令速查

```bash
# 确定产品类型前缀：standard_（通用型）/ warehouse_（计算组）/ follower_（从实例）/ serverless_ / shared_（湖仓加速）
# 可先用 list 查看实际可用指标名：
hologres metric list --search cpu

# CPU 水位（以通用型 standard_ 为例）
hologres metric query standard_cpu_usage --instance-id {id} --start-time {s} --end-time {e} --period 60
hologres metric latest standard_cpu_usage --instance-id {id}

# 业务负载
hologres metric query standard_query_qps --instance-id {id} --start-time {s} --end-time {e}
hologres metric query standard_dml_rps --instance-id {id} --start-time {s} --end-time {e}
hologres metric query standard_query_latency --instance-id {id} --start-time {s} --end-time {e}

# Worker 维度
hologres metric query standard_cpu_usage_by_worker --instance-id {id} --start-time {s} --end-time {e}

# 计算组实例则使用 warehouse_ 前缀：
hologres metric query warehouse_cpu_usage --instance-id {id} --start-time {s} --end-time {e} --period 60
```
