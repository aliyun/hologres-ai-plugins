---
name: hologres-diagnosis-memory
depends: [hologres-cli]
description: >
  Hologres 实例内存使用率异常诊断技能。当用户提到内存打满、OOM、内存持续高位、Worker 内存不均、内存泄漏、内存倾斜、内存归因分析等场景时使用。
  以 instance_id + 时间窗口为输入，自动完成内存水位形态判定（全局高 / 局部倾斜 / 持续不回落）、业务指标对齐、内存分类初筛（Query vs System/Cache）、
  并沿 Query 主线、倾斜主线、Write/后台主线、System/元数据主线四大归因维度自动下钻，输出结构化的 Markdown 诊断报告与治理行动清单。
  云监控数据通过 `hologres metric query` / `hologres metric latest` 获取；元仓与 PG 系统表数据通过 `hologres sql run` 获取；
  内部工具数据（OOM/Jeprof/Coredump）通过 `holo oncall common` 获取，全程享有 hologres-cli 的安全护栏、JSON 结构化输出与自动错误重试能力。
---

# Hologres 内存使用率诊断

系统性诊断 Hologres 实例内存异常（OOM / 持续高位 / 倾斜），按照「宏观水位形态 → 业务对齐 → 内存分类 → 三大主线归因」的链路自动化归因，并输出结构化诊断报告。

**定位**：自动锚定异常窗口，精准定位 OOM/泄漏/倾斜根因。仅限根因诊断：对于问题 Query，仅输出 ID 及资源指标快照，不包含具体 SQL 优化建议或改写指导。

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `instance_id` | 是 | Hologres 实例 ID，例如 `hgprecn-cn-xxx` |
| `start_time` | 是 | 诊断开始时间，ISO-8601 格式（北京时间须带 `+08:00` 后缀，如 `2025-05-19T10:00:00+08:00`）或 epoch 毫秒 |
| `end_time` | 是 | 诊断结束时间，格式同 `start_time` |
| `region` | 否 | 云监控 Region，自动从 config profile 的 `region_id` 读取，无需手动指定；也可通过 `--region` 显式覆盖 |

> 时间窗口长度决定了「短周期 / 长周期」分支阈值：`<24h` 为短周期，`>24h` 为长周期。

## 指标名称前缀约定

Hologres 云监控指标名称包含 **产品类型前缀**，前缀通过「前置步骤：实例类型自动判断」自动获取，无需用户手动指定：

| 实例类型 | 前缀 | 示例 |
|----------|------|------|
| 计算组（Warehouse） | `warehouse_` | `warehouse_memory_usage` |
| 通用型（Standard） | `standard_` | `standard_memory_usage` |
| 从实例（Follower） | `follower_` | `follower_memory_usage` |
| Serverless 型 | `serverless_` | `serverless_memory_usage` |
| 湖仓加速型（Shared） | `shared_` | `shared_memory_usage` |

## 诊断主流程

```
前置步骤：实例类型自动判断
   └── 调用 instance-manage get → 获取 InstanceType → 映射指标前缀 {prefix}

第一阶段：内存水位采集 + 形态分级
   ├── 全局高 / 局部倾斜 / 持续不回落 → 第二阶段（分类下钻）
   └── 安全平稳                        → 直接出具「健康」报告

第二阶段：内存分类下钻
   ├── Q1 内存水位总览：水位形态判定（全局高 / 局部倾斜 / 持续不回落）
   ├── Q2 业务指标对齐：排除正常业务增长
   ├── Q3 内存分类初筛：Query vs System/Cache 分流
   └── 进入对应主线（Query / 倾斜 / System / 泄漏）

第三阶段：四大主线深挖
   ├── 主线 A：Query 侧（高内存 SQL / Plan 失真 / 访问不均）
   ├── 主线 B：倾斜侧（Shard 分配与访问热点）
   ├── 主线 C：Write/后台侧（批量写入冲击 / 后台内存占用）
   └── 主线 D：System/元数据侧 & 内部故障排查

第四阶段：综合输出诊断报告（Markdown）
```

## 前置步骤：实例类型自动判断

在执行任何指标查询之前，必须先获取实例类型并自动映射到对应的指标名前缀 `{prefix}`，无需用户手动指定。

### 执行命令

```bash
hologres instance-manage get
```

### 解析规则

从返回 JSON 中提取 `data.Instance.InstanceType` 字段，根据以下映射表确定 `{prefix}`：

| InstanceType | 中文名 | 指标前缀 |
|---|---|---|
| Warehouse | 计算组型 | `warehouse_` |
| Follower | 只读从实例 | `follower_` |
| Standard | 普通型 | `standard_` |
| Serverless | Serverless 型 | `serverless_` |
| Shared | 共享型 | `shared_` |

### 计算组实例特殊处理

若为计算组（Warehouse）实例，需要：
1. 获取各计算组的内存使用率
2. 判断是否存在单计算组内存异常（某组显著高于其他组或阈值）
3. 若存在单组异常 → 锁定该异常计算组，后续所有诊断步骤仅在该计算组范围内执行
4. 若所有组均高 → 视为全局高，进入后续排查

---

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

云监控 API 的 AK/SK 支持 **metric 专用配置**，推荐使用 `hologres metric config` 单独配置：

```bash
hologres metric config --access-key-id <your_ak> --access-key-secret <your_sk>
```

若未配置 metric 专用凭证，则**回退读取 `hologres config` 配置的通用 AK/SK**；若 profile 中均未配置，则回退到阿里云默认凭证链：

```bash
export ALIBABA_CLOUD_ACCESS_KEY_ID=<your_ak>
export ALIBABA_CLOUD_ACCESS_KEY_SECRET=<your_sk>
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
export HOLOGRES_SKILL=hologres-diagnosis-memory
```

---

## 第一阶段：内存水位采集与形态分级

调用云监控获取 `instance_id` 下各粒度的内存使用率时间序列，并据此对实例内存状态进行形态分类。指标名前缀 `{prefix}` 已由前置步骤自动确定。

### 1.1 获取内存使用率时间序列（按 Warehouse 粒度）

```bash
# 时间窗口内的内存使用率曲线（建议 period=60 秒）
# 注意：{prefix} 已由前置步骤自动确定
hologres metric query {prefix}_memory_usage \
    --instance-id {instance_id} \
    --start-time {start_time} \
    --end-time {end_time} \
    --period 60
```

### 1.2 获取内存最新点（快速健康检查）

```bash
hologres metric latest {prefix}_memory_usage --instance-id {instance_id} --period 60
```

### 1.3 获取 Worker 维度内存分布

```bash
# 各 Worker 内存使用率（如存在该指标）
hologres metric query {prefix}_memory_usage_by_worker \
    --instance-id {instance_id} \
    --start-time {start_time} \
    --end-time {end_time} \
    --period 60
```

### 1.4 检查 OOM 事件

```bash
# 通过 holo CLI 查询 OOM 记录
holo oncall common oom {instance_id}
```

### 1.5 内存形态分级

| 状态 | 判定条件 | 后续动作 |
|------|----------|----------|
| 🔴 全局高 | 所有 Worker 内存 P95 > 85% | 进入第二阶段分类下钻 |
| 🟠 局部倾斜 | Max Worker - Avg Worker > 20% 或绝对差值显著 | 进入倾斜主线排查 |
| 🟡 持续不回落 | 低峰期水位较基线上涨 > 10% 且不回落 | 进入泄漏/Cache滞留排查 |
| 🟢 安全平稳 | 水位平稳，30%-50% 空闲 | 跳过归因，输出健康报告 |

**形态识别补充**：
- **尖峰**：持续时间 < 1h，随后回落 → 通常为突发查询或写入
- **持续高位**：持续时间 > 4h，且无显著回落 → 疑似泄漏或配置不当

---

## 第二阶段：内存分类下钻

### Q1：内存水位总览

**目标**：区分是整体资源不足、局部数据倾斜，还是疑似泄漏（不回落），以此决定后续分支走向。

**数据源**：云监控内存水位 + Worker 分布 + OOM List

#### 判断逻辑

| 形态 | 判定条件 | 后续路由 |
|------|----------|----------|
| 整体高 | 所有 Worker 水位均高，P95 > 85% | → 全局并发高 / 系统性资源不足 → Q2 + Q3 |
| 局部倾斜 | 少数 Worker 水位显著高于其他节点 | → 数据/Shard 倾斜 / 热点 Key → 倾斜主线 |
| 持续不回落 | 低峰期水位仍维持高位 | → 内存泄漏 / Cache 滞留 / 长事务 → System/泄漏主线 |

**基线校准**：空闲状态 30%-50% 为正常；长期 > 80% 为异常。

---

### Q2：业务指标对齐 —— 排除正常业务增长

**目标**：区分"业务繁荣导致的资源消耗"与"故障/异常"。若为正常增长，仅需提示扩容；若为异常，则需深入排查。

**数据源**：云监控 QPS、RPS、DML RPS

#### 执行命令

```bash
# QPS 时间序列
hologres metric query {prefix}_query_qps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

# DML RPS 时间序列
hologres metric query {prefix}_dml_rps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60
```

#### 判断逻辑

| 现象 | 结论 | 后续动作 |
|------|------|----------|
| 内存↑ + QPS/RPS/DML 同比例↑ + 无 OOM | **正常业务增长** | 评估扩容；可中止归因 |
| 内存飙升但业务量平稳 / 下降 | **异常瓶颈** | 继续 Q3 分类初筛 |
| 内存↑ + 伴随 Failed Query / OOM | **异常瓶颈** | 继续 Q3 + 对应主线 |

---

### Q3：内存分类初筛 —— Query vs System/Cache

**目标**：决定是去查"慢 SQL/并发"，还是查"元数据/后台任务/泄漏"。这是分流枢纽。

**数据源**：云监控内存分类指标 / 内存技术大盘

#### 执行命令

```bash
# 内存分类指标：{prefix}_memory_usage_detail（按 memType 拆分：query / cache / meta / system 等）
# 先获取最新快照判断分类占比：
hologres metric latest {prefix}_memory_usage_detail --instance-id {instance_id} --period 60

# 再获取时间序列观察趋势：
hologres metric query {prefix}_memory_usage_detail \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 300

# QE 引擎 Query 内存使用率（辅助判断 Query 是否为内存主导）：
hologres metric query {prefix}_qe_memory_used_percentage \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

# 如果内存分类指标不可用，通过 PG 系统表辅助判断
hologres sql run --no-limit-check "SELECT state, count(1) AS conn_count FROM pg_stat_activity WHERE usename <> 'system' AND datname IS NOT NULL GROUP BY state ORDER BY conn_count DESC"
```

#### 分支判断

| 分类 | 判定条件 | 后续路由 |
|------|----------|----------|
| Query 内存占比高 | Query Memory 占比显著升高（>60-70%） | → 主线 A：Query 侧排查 |
| Worker 内存倾斜 | 少数 Worker 水位显著高于其他节点 | → 主线 B：倾斜侧排查 |
| Cache/System 内存占比高 | 非 Query 类内存占比高或持续累积 | → 主线 C+D：Write/后台侧 + System/元数据侧 |
| 无明显分类异常但水位高 | 无法明确区分 | → 默认进入全量排查，四条主线都走 |
| 疑似泄漏 | 水位高且不回落，无明显大 Query | → 主线 D 泄漏排查 + 内部工具（Jeprof/Coredump/OOM） |

> **注意**：用户侧监控较粗，若无法明确区分，默认进入全量排查。

---

## 第三阶段：三大主线深挖

### 主线 A：Query 侧 —— 高内存查询分析

#### A1：高内存消耗查询 Top 10

**数据源**：元仓 `hologres.hg_query_log`

```bash
# 按内存消耗降序取 Top 10
hologres sql run --no-limit-check "SELECT query_id, duration AS duration_ms, memory_bytes, shuffle_bytes, cpu_time_ms, query_start, status, usename, engine_type, query::char(200) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND memory_bytes IS NOT NULL AND usename <> 'system' ORDER BY memory_bytes DESC LIMIT 10"
```

**展示字段**：Query ID、内存消耗（memory_bytes）、Shuffle 量（shuffle_bytes）、CPU 时间、Warehouse、SQL 样本。

**关键指标**：
- `memory_bytes`：各节点峰值内存的累加值，仅供参考相对大小
- `shuffle_bytes`：Shuffle 数据量，> 1GB 需关注
- 需结合当时 RPS/QPS 判断是单条巨大还是并发累积

#### A2：按 SQL 指纹聚合内存 Top 10

```bash
# 按 digest 聚合，找出内存消耗最高的 Query 模式
hologres sql run --no-limit-check "SELECT digest AS sql_digest, count(1) AS exec_count, round(avg(memory_bytes)::numeric / 1048576, 2) AS avg_memory_mb, round(max(memory_bytes)::numeric / 1048576, 2) AS peak_memory_mb, round(avg(shuffle_bytes)::numeric / 1048576, 2) AS avg_shuffle_mb, round(sum(memory_bytes)::numeric / 1048576, 2) AS total_memory_mb, max(query_id) AS sample_query_id, max(query)::char(120) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND digest IS NOT NULL AND memory_bytes IS NOT NULL AND usename <> 'system' GROUP BY digest ORDER BY sum(memory_bytes) DESC LIMIT 10"
```

#### A3：Plan 失真与 Broadcast 倾斜

若发现单点内存爆炸，需检查是否存在统计信息过期导致大表被错误 Broadcast：

```bash
# 查询执行计划中是否存在 Broadcast 的 SQL（通过 query_log 中的 plan 字段或 EXPLAIN ANALYZE）
# 注意：此步骤需要用户配合执行 EXPLAIN ANALYZE，诊断报告中仅给出建议
```

**根因**：统计信息过期 → 大表被错误地 Broadcast → 单点内存爆炸。

#### A4：Worker 倾斜下的 Query 访问不均

若发现 Worker 倾斜，需检查高频访问该 Worker 的 Query 特征：

```bash
# 高频访问特定 Worker 的高内存 Query（结合 hg_query_log + hg_worker_info）
hologres sql run --no-limit-check "SELECT query_id, usename, warehouse_name, memory_bytes, cpu_time_ms, duration AS duration_ms, query::char(200) AS sql_sample FROM hologres.hg_query_log WHERE query_start >= '{start_time}' AND query_start <= '{end_time}' AND memory_bytes > 1073741824 AND usename <> 'system' ORDER BY memory_bytes DESC LIMIT 20"
```

**判定**：是否存在热点 Dist Key 导致特定 Worker 被集中访问，或特定表的 Aggregate 操作集中在少数 Worker。

---

### 主线 B：倾斜侧 —— Shard 分配与访问热点

#### B1：Shard 物理分布检查

**数据源**：PG 系统表 `hologres.hg_worker_info`

```bash
# 各 Worker 的 Shard 数量分布
hologres sql run --no-limit-check "SELECT worker_id, count(shard_id) AS shard_count FROM hologres.hg_worker_info GROUP BY worker_id ORDER BY shard_count DESC"
```

**物理不均判定**：Worker 之间 `shard_count` 与平均值偏差 > 20% → 判定物理不均。

#### B2：Worker 内存热点与逻辑倾斜

**数据源**：云监控 Worker 内存分布

```bash
# 各 Worker 内存使用率（云监控）
hologres metric query {prefix}_memory_usage_by_worker \
    --instance-id {instance_id} \
    --start-time {start_time} --end-time {end_time} --period 60
```

**逻辑倾斜判定**：物理均衡但特定 Worker CPU/Mem 极高 → 逻辑倾斜。可能原因：热点 Dist Key 导致 Broadcast 或 Aggregate 倾斜。

#### B3：热点 Key 检测

若发现 Worker 倾斜，检查：
1. 是否存在热点 Dist Key（如 `user_id` 倾斜）
2. 是否有大量 Broadcast 导致单点内存爆炸
3. 是否有特定表的 Aggregate 操作集中在少数 Worker

---

### 主线 C：Write/后台侧 —— 是否有写入积压？

#### C1：批量写入冲击

**数据源**：云监控 DML RPS

```bash
# DML RPS 时间序列
hologres metric query {prefix}_dml_rps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60

# FixedQE DML RPS（如存在）
hologres metric query {prefix}_fixedqe_dml_rps \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60
```

**根因**：Batch Size 过大或提交间隔长导致 Buffer 积压。

#### C2：后台内存占用

**数据源**：云监控内存分类指标 `{prefix}_memory_usage_detail`（含 memType 维度）

```bash
# 内存分类明细（按 memType 拆分：query / cache / meta / system 等）
hologres metric query {prefix}_memory_usage_detail \
    --instance-id {instance_id} --start-time {start_time} --end-time {end_time} --period 60
```

**判定**：非 Query 类内存（cache / system / meta）占比激增，且伴随 DML RPS 上升或大量小文件写入 → 后台任务内存膨胀。

---

### 主线 D：System/元数据侧 & 内部故障排查

#### D1：元数据膨胀检测

**数据源**：PG 系统表（`pg_catalog.pg_class`、`hologres.hg_table_info`）

```bash
# 各 schema 表数量检查（单 schema > 10,000 为异常）
hologres sql run --no-limit-check "SELECT schemaname, count(*) AS table_count FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'hologres') GROUP BY schemaname ORDER BY table_count DESC LIMIT 20"

# 分区表数量检查
hologres sql run --no-limit-check "SELECT n.nspname AS schemaname, c.relname AS tablename, count(i.inhrelid) AS partition_count FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace LEFT JOIN pg_catalog.pg_inherits i ON i.inhparent = c.oid WHERE c.relkind = 'p' AND n.nspname NOT IN ('pg_catalog', 'information_schema') GROUP BY n.nspname, c.relname ORDER BY partition_count DESC LIMIT 20"
```

**判定**：单 Schema 表/分区数 > 10,000 → Meta Cache 常驻内存过高。

#### D2：长事务检测

```bash
# 长事务检查
hologres sql run --no-limit-check "SELECT pid, usename, state, now() - query_start AS txn_duration, wait_event_type, wait_event, left(query, 200) AS sql_snippet FROM pg_stat_activity WHERE state = 'active' AND usename <> 'system' AND now() - query_start > interval '10 min' ORDER BY query_start ASC"
```

#### D3：内部工具排查（P2 疑难杂症）

当分类不明、水位不回落、无大 SQL 时，使用内部高阶工具排查。

**数据源**：`holo oncall common` 命令系列

```bash
# OOM 记录列表
holo oncall common oom {instance_id}

# Jeprof 结果列表
holo oncall common coredumps {instance_id}

# Coredump 记录
holo oncall common coredumps {instance_id}
```

**泄漏判定**：
- Jeprof 显示某类 Java Heap 对象随时间线性增长且不释放 → 确认内存泄漏
- Coredump List 有记录 → 分析崩溃现场
- OOM List 频繁触发且无对应大 Query → 容量不足或异常泄漏

---

## 第四阶段：输出诊断报告

完成第一/二/三阶段后，输出以下 Markdown 结构化报告。**所有占位符必须基于真实查询结果填充，不得编造。**

```markdown
# Hologres 内存使用率诊断

- **实例 ID**：`{instance_id}`（通用型/计算组型） / `{region}`
- **诊断时段**：`{start_time}` ~ `{end_time}`（北京时间）
- **涉及计算组**：{affected_clusters} (仅当检测到单组异常时显示)
- **健康评分**：`{score}`/100 | **整体状态**：`{status}` (正常 / 警告 / 异常)

## 一、今日摘要

> **核心结论**：`{summary_conclusion}`
> **根因归类**：`{root_cause_category}`

- **关键风险**：`{top_risks}` (例如：OOM 风险极高、新查询可能被 Reject、潜在内存泄漏)
- **推荐动作**：`{action_top_1}`, `{action_top_2}`

---

## 二、Q1: 内存水位总览

### 1. 结论
`{q1_conclusion}`

### 2. 关键事实数据

| 维度 | 指标 | 当前值/峰值 | 基线/预期值 | 波动幅度 | 状态判定 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **整体水位** | 实例内存使用率 (Max) | `{mem_max_pct}%` | `{mem_baseline_pct}%` | `{mem_diff}%` | **高危** |
| **稳定性** | OOM 事件次数 | `{oom_count}` | 0 | - | **异常** |
| **回落情况** | 低峰期最小水位 | `{min_mem_pct}%` | `{base_min_pct}%` | - | **未回落/倾斜** |
| **影响面** | 高水位 Worker 占比 | `{high_worker_pct}%` | - | - | `{scope_status}` |

### 3. 分析与建议
- **分析**：`{q1_analysis}` (基于形态判断：全体高 vs 局部高 vs 不回落)
- **建议**：根据形态进入后续 Q2-Q5 专项排查。

---

## 三、Q2: Worker 内存分布分析

### 1. 结论
`{q2_conclusion}`

### 2. 关键事实数据

| 维度 | 最大值 (Max) | 最小值 (Min) | 平均值 (Avg) | 偏差状态 |
| :--- | :--- | :--- | :--- | :--- |
| **Worker 内存 P95** | `{max_worker_mem}%` | `{min_worker_mem}%` | `{avg_worker_mem}%` | `{skew_flag}` |

- **倾斜详情**：
    - 热点 Worker：`{hot_worker_id}`
    - 疑似热点表/Shard：`{skewed_table_name}` (Dist Key: `{dist_key}`)
    - Shard 分配检查：`{shard_distribution_status}`

### 3. 分析与建议
- **分析**：`{q2_analysis}`
- **建议**：`{q2_suggestion}` (如：发现热点 Dist Key，建议调整分布键)

---

## 四、Q3: 高内存查询分析

### 1. 结论
`{q3_conclusion}`

### 2. 关键事实数据：Top 内存消耗 SQL

| 排名 | SQL 摘要 | 内存累加 (MB)* | Shuffle (GB) | CPU 时间 (s) | 算子类型 | 根因推测 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `{top1_sql}` | `{top1_mem}` | `{top1_spill}` | `{top1_cpu}` | `{top1_op}` | `{top1_reason}` |
| 2 | `{top2_sql}` | `{top2_mem}` | `{top2_spill}` | `{top2_cpu}` | `{top2_op}` | `{top2_reason}` |

*\*注：`memory_bytes` 为各节点峰值内存的累加值，仅供参考相对大小*

- **负载关联分析**：
    - 当时 QPS/RPS：`{current_qps}` / `{current_rps}`
    - QE 内存水位：`{qe_mem_pct}%`

### 3. 分析与建议
- **根因判断**：`{q3_conclusion}` (例如：Query ID 123456789 为内存主要消耗者，单次执行峰值内存达 20GB)
- **关键证据**：
  - Problematic Query ID: `{top1_query_id}`
  - 内存峰值: `{top1_mem}`
  - Shuffle 量: `{top1_spill}`
  - 关联算子: `{top1_op}` (如 HashJoin, Sort)
- **后续行动建议**：对问题 SQL 进行优化分析。

---

## 五、Q4: 系统与后台内存分析

### 1. 结论
`{q4_conclusion}`

### 2. 关键事实数据

| 组件类型 | 估值/计数 | 阈值/基线 | 状态 | 数据源参考 |
| :--- | :--- | :--- | :--- | :--- |
| **Meta Objects** | `{table_partition_count}` | < 10,000 | `{meta_status}` | PG System Tables |
| **Long Transactions** | `{long_txn_count}` | 0 | `{txn_status}` | pg_stat_activity |
| **Background Mem** | `{bg_mem_pct}%` | < 5% | `{bg_status}` | CloudMonitor |
| **Leak Suspect** | `{leak_object_type}` | - | `{leak_status}` | Jeprof Result List |
| **Crash Evidence** | `{coredump_count}` | 0 | `{crash_status}` | Coredump List |

- **内部工具洞察**：
    - **Jeprof 摘要**：`{jeprof_summary}` (例如：Top 1 对象增长曲线)
    - **OOM 详情**：`{oom_details}` (来自 OOM List)

### 3. 分析与建议
- **分析**：`{q4_analysis}`
- **建议**：`{q4_suggestion}`
    - 若是泄漏：收集 Jeprof/Coredump 信息提单研发，重启实例临时恢复。
    - 若是元数据：清理无效分区/表，合并小分区。
    - 若是长事务：`SELECT pg_terminate_backend({txn_pid});`

---

## 六、Q5: 治理行动清单 (Action Plan)

### P0 - 立即处理 (阻断性风险)
- [ ] `{action_p0_1}` (例如：终止高内存消耗 Query xxx，释放内存)
- [ ] `{action_p0_2}` (例如：处理长事务 PID xxx)

### P1 - 近期优化 (性能提升)
- [ ] `{action_p1_1}` (例如：对 Top 3 大查询 SQL 进行优化分析)
- [ ] `{action_p1_2}` (例如：清理无效分区/表，合并小分区)

### P2 - 长期规划 (容量与架构)
- [ ] `{action_p2_1}` (例如：扩容 Warehouse / 拆分读写流量)
- [ ] `{action_p2_2}` (例如：建立内存与 OOM 联合告警阈值)
```

---

## 数据支撑来源映射

| 诊断项 | 数据来源 | 获取方式 |
|---------|----------|----------|
| 内存水位 | 云监控 | `hologres metric query {prefix}_memory_usage` / `hologres metric latest {prefix}_memory_usage` |
| Worker 内存分布 | 云监控 | `hologres metric query {prefix}_memory_usage_by_worker` |
| QPS / DML RPS | 云监控 | `hologres metric query {prefix}_query_qps` / `{prefix}_dml_rps` |
| 内存分类 | 云监控 / 内存技术大盘 | `hologres metric query {prefix}_memory_usage_detail`（memType 维度） + `{prefix}_qe_memory_used_percentage` |
| Query 内存指标 | 元仓 | `hologres sql run`（`hologres.hg_query_log`，memory_bytes / shuffle_bytes） |
| Shard/数据分布 | 内部元数据 / PG 系统表 | `hologres sql run`（`hologres.hg_worker_info`） |
| 元数据/表结构 | PG 系统表 | `hologres sql run`（`pg_catalog.pg_class`、`hologres.hg_table_info`） |
| 长事务 | PG 系统表 | `hologres sql run`（`pg_stat_activity`） |
| 后台内存占比 | 云监控 | `hologres metric query {prefix}_memory_usage_detail`（cache/system/meta memType 维度） |
| OOM 事件 | 内部工具 | `holo oncall common oom {instance_id}` |
| Java 堆内存剖面 | 内部工具 (Jeprof) | `holo oncall common coredumps {instance_id}` |
| Coredump | 内部工具 | `holo oncall common coredumps {instance_id}` |

## 异常判断阈值配置

| 维度 | 时间窗口 | 指标 | 异常阈值 |
|------|----------|------|----------|
| Memory Usage | 实时 | Worker 内存使用率 | > 85% |
| Memory Usage | 长周期 | 低峰期基线水位 | 环比上涨 > 10% |
| Worker 倾斜 | 实时 | Max Worker - Avg Worker | > 20% |
| Query Memory | 单次查询 | memory_bytes (Top N) | > 实例总内存 5% |
| Shuffle | 单次查询 | shuffle_bytes | > 1 GB |
| Meta Data | 长周期 | 单 TG 表/分区总数 | > 10,000 |
| Internal Faults | 事件驱动 | Coredump/OOM Count | > 0 |

## 执行指导

**环境准备**：

```bash
export HOLOGRES_SKILL=hologres-diagnosis-memory
# 推荐：通过 `hologres metric config` 为 metric 命令单独配置 AK/SK
# hologres metric config --access-key-id <ak> --access-key-secret <sk>
```

**逐步执行，每步汇报中间结果**：

0. `hologres instance-manage get` —— 获取实例类型，自动映射指标前缀 `{prefix}`
1. `hologres metric query {prefix}_memory_usage` —— 获取内存时间序列，做形态分级
2. `holo oncall common oom {instance_id}` —— 检查 OOM 事件
3. （若命中异常）`hologres metric query {prefix}_query_qps / {prefix}_dml_rps` —— 业务指标对齐
4. `hologres metric latest {prefix}_memory_usage_detail` + `{prefix}_qe_memory_used_percentage` —— 内存分类初筛
5. `hologres sql run`（`hg_query_log` Top memory + shuffle） —— 主线 A Query 归因
6. `hologres sql run`（`hg_worker_info` + Shard 分布） —— 主线 B 倾斜排查
7. `hologres metric query {prefix}_dml_rps` + `{prefix}_memory_usage_detail` —— 主线 C Write/后台归因
8. `hologres sql run`（元数据检查 + 长事务） + `holo oncall common oom / coredumps` —— 主线 D System/内部归因
9. 综合 1~8 步结果，按第四阶段模板输出 Markdown 诊断报告

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
| `DEPENDENCY_MISSING` | 缺少 SDK | `pip install 'hologres-cli[cms]'` |
| `CREDENTIAL_ERROR` | 凭证未配置或失效 | 配置 AK/SK |
| `API_ERROR` | 云监控 API 调用失败 | 检查 Region / 限流，重试 |
| `INVALID_INPUT` | 时间格式或 dimensions 不合法 | 修正后重试 |

## 注意事项

1. `hologres.hg_query_log` 默认保留一个月，单次最多返回 10000 条；查询必须带 `query_start` 范围条件，避免全表扫描
2. 元仓 SQL 不要使用 `to_char(query_start, ...)` 等表达式条件（无法走索引）
3. 云监控 `period` 推荐 `60s`（细粒度）或 `300s`（长周期）；时间跨度大时使用 `300s` 减少数据点
4. **时区处理（重要）**：云监控 API 将不带时区后缀的 ISO-8601 时间视为 **UTC**。若用户给出的是北京时间，必须携带 `+08:00` 后缀（如 `2025-05-19T10:00:00+08:00`），否则实际查询窗口会偏移 8 小时，导致窄窗口场景下查不到目标数据。也可使用 epoch 毫秒（如 `1716098400000`）彻底规避时区歧义
5. `digest` 字段从 V2.2 起支持，低版本实例为空，需降级为按 `query` 文本聚合
6. `memory_bytes` 为各节点峰值内存的累加值，仅供参考相对大小，不等于实际物理内存消耗
7. 所有 `hologres metric` / `hologres sql run` 返回 JSON，结果在 `data.rows`（SQL）或顶层数组（云监控数据点）
8. 使用 `--no-limit-check` 跳过 LIMIT 检查（聚合诊断查询无需 LIMIT 保护）
9. 内部工具（OOM / Jeprof / Coredump）通过 `holo oncall common` 获取，需要相应的权限配置
10. 本技能仅做根因诊断定位，对于问题 Query 只输出 ID 及资源指标快照，不包含 SQL 优化建议或改写指导
11. `memory_bytes` 字段在 `hg_query_log` 中可能全为 0（轻量查询取整为零、或实例未开启内存采集 GUC）。降级策略：优先使用云监控 `{prefix}_qe_memory_used_percentage` + `{prefix}_memory_usage_detail`（query memType）判断 Query 侧内存消耗，当两个指标均显示 Query 占比极低时，可确认无高内存 SQL

## 参考命令速查

```bash
# 前缀通过 `hologres instance-manage get` 自动获取
# 也可用 list 查看实际可用指标名：
hologres metric list --search memory

# 内存水位（以通用型 standard_ 为例）
hologres metric query standard_memory_usage --instance-id {id} --start-time {s} --end-time {e} --period 60
hologres metric latest standard_memory_usage --instance-id {id}

# 业务负载
hologres metric query standard_query_qps --instance-id {id} --start-time {s} --end-time {e}
hologres metric query standard_dml_rps --instance-id {id} --start-time {s} --end-time {e}

# 内存分类详情（按 memType 拆分）
hologres metric latest warehouse_memory_usage_detail --instance-id {id} --period 60

# QE Query 内存使用率
hologres metric latest warehouse_qe_memory_used_percentage --instance-id {id} --period 60

# 计算组实例则使用 warehouse_ 前缀：
hologres metric query warehouse_memory_usage --instance-id {id} --start-time {s} --end-time {e} --period 60

# 内部工具
holo oncall common oom {instance_id}
holo oncall common coredumps {instance_id}

# Shard 分布
hologres sql run --no-limit-check "SELECT worker_id, count(shard_id) AS shard_count FROM hologres.hg_worker_info GROUP BY worker_id ORDER BY shard_count DESC"

# 高内存 SQL
hologres sql run --no-limit-check "SELECT query_id, memory_bytes, shuffle_bytes, query::char(120) FROM hologres.hg_query_log WHERE query_start >= '{start}' AND query_start <= '{end}' AND memory_bytes IS NOT NULL ORDER BY memory_bytes DESC LIMIT 10"
```
