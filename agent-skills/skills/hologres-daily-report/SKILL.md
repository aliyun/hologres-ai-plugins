---
name: hologres-daily-report
depends: [hologres-cli]
description: >
  Hologres 运维诊断日报生成技能。生成一份包含"诊断结论 + 根因解释 + 行动建议"的每日巡检报告，
  覆盖实例健康、可用性、计算资源、SQL性能、成本治理、容量预测六大维度。
  触发词：日报、每日巡检、daily report、运维日报、诊断日报、实例巡检报告、每日健康报告。
---

# Hologres 运维诊断日报

不是监控面板的数据搬运，而是一份由 AI 助手生成的**"诊断结论 + 根因解释 + 行动建议"型日报**。

## 输入参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `instance_id` | 实例 ID（如 `hgprecn-cn-xxx`） | 当前 profile 的 instance_id |
| `report_date` | 报告日期 | 昨天（`YYYY-MM-DD`） |
| `region` | 地域 | 当前 profile 的 region_id |
| `time_range` | 诊断时间窗口 | `{report_date} 00:00 ~ {report_date} 23:59` |

## 前提条件

1. **安装 hologres-cli**：`pip install hologres-cli`
2. **配置 Profile**：`hologres config`（需包含 instance_id、region_id、数据库连接信息）
3. **配置云监控凭证**：`hologres metric config --access-key-id <AK> --access-key-secret <SK>`（用于 CPU/内存/连接数等指标查询）
4. **权限要求**：账号需有 `hologres.hg_query_log`、`pg_stat_activity`、`pg_locks` 等系统表的读取权限
5. **设置 SQL 追踪标识**：

```bash
export HOLOGRES_SKILL=hologres-daily-report
```

> **注意**：所有 SQL 查询默认路由到 serverless 计算池（CLI 自动设置 `hg_computing_resource = 'serverless'`），不会影响用户业务负载。

## 日报整体结构

```
┌─────────────────────────────────────────────────────────────────┐
│  Hologres 运维诊断日报  —  {report_date}（{weekday}）           │
│  实例：{instance_id} / {region}                                  │
├─────────────────────────────────────────────────────────────────┤
│  今日健康评分：{score}/100  （较昨日 {change}）                  │
│  需关注：{attention}项  |  可优化：{optimize}项  |  正常：其余    │
├─────────────────────────────────────────────────────────────────┤
│  核心六问速览                                                    │
│  ① 实例整体健康吗？        →  {q1_summary}                      │
│  ② 可用性/稳定性有问题吗？ →  {q2_summary}                      │
│  ③ 计算资源紧张吗？        →  {q3_summary}                      │
│  ④ SQL/任务有性能问题吗？  →  {q4_summary}                      │
│  ⑤ 成本是否异常/可治理？   →  {q5_summary}                      │
│  ⑥ 未来有容量风险吗？      →  {q6_summary}                      │
├─────────────────────────────────────────────────────────────────┤
│  详细诊断（下文展开）                                            │
└─────────────────────────────────────────────────────────────────┘
```

## 数据采集与诊断流程

按以下 6 个步骤依次执行数据采集和诊断分析。每一步的详细 SQL 和命令见 `references/` 目录。

---

### Step 1: 实例基础信息采集（Q1 实例健康 + Q2 可用性）

> 详细 SQL 见 [references/health-check.md](references/health-check.md)

#### 1.1 实例状态与版本

```bash
# 检查连接状态和版本
hologres status

# 查询实例详细信息（版本、最大连接数）
hologres instance <instance_name>

# 查询实例管理信息（实例类型、状态）
hologres instance-manage get

# 查询 Warehouse 列表（资源分配）
hologres warehouse
```

**诊断标准**：
- 实例状态非 Running → 严重异常
- 版本距离 EOS < 3 个月 → 关注；已过 EOS → 异常

#### 1.2 Worker 节点与连接

```bash
# 活跃连接数与分布（使用 hologres-instance-health-analyse skill 的 warehouse-metrics 查询）
hologres sql run --no-limit-check "SELECT state, wait_event_type, count(*) FROM pg_stat_activity WHERE backend_type = 'client backend' GROUP BY 1, 2 ORDER BY 3 DESC"

# 锁等待检测
hologres sql run --no-limit-check "SELECT count(*) as waiting_locks FROM pg_locks WHERE NOT granted"

# 长时间阻塞检测（>30s）
hologres sql run --no-limit-check "SELECT pid, now() - query_start as duration, query FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '30 seconds' AND backend_type = 'client backend' ORDER BY duration DESC LIMIT 10"
```

**诊断标准**：
- 等待锁 > 10 个或阻塞时长 > 30s → 异常
- 连接数瞬时跌至 0 → 严重异常

#### 1.3 可用性事件检测（Q2）

```bash
# 检测当日 DDL 变更事件（CREATE/ALTER/DROP）
hologres sql run --no-limit-check "SELECT command_tag, count(*) as cnt FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND command_tag IN ('CREATE TABLE', 'ALTER TABLE', 'DROP TABLE', 'CREATE INDEX', 'DROP INDEX', 'ALTER DATABASE') AND usename <> 'system' GROUP BY 1 ORDER BY 2 DESC"
```

**诊断标准**：
- 任何重启/coredump 记录 → 事件
- DDL 变更操作 → 事件（需评估业务影响）

---

### Step 2: 计算资源指标采集（Q3 计算资源）

> 详细指标查询见 [references/resource-analysis.md](references/resource-analysis.md)

#### 指标名称前缀约定

> 引用 **hologres-diagnosis-cpu** skill 的前缀规则。先执行 `hologres instance-manage get` 获取实例类型，确定指标前缀：

| 实例类型 | 前缀 |
|---------|------|
| Standard / 通用型 | `standard_` |
| Warehouse / 计算组型 | `warehouse_` |
| Follower / 只读从实例 | `follower_` |
| Serverless | `serverless_` |
| Shared / 共享型 | `shared_` |

以下命令中用 `{prefix}` 表示实际前缀。

#### 2.1 CPU 使用率

```bash
# 查询 CPU 使用率时序数据（最近24h，60s粒度）
hologres metric query {prefix}cpu_usage --start "{report_date}T00:00:00" --end "{report_date}T23:59:59" --period 60
```

#### 2.2 内存使用率

```bash
hologres metric query {prefix}memory_usage --start "{report_date}T00:00:00" --end "{report_date}T23:59:59" --period 60
```

#### 2.3 连接数

```bash
hologres metric query {prefix}connections --start "{report_date}T00:00:00" --end "{report_date}T23:59:59" --period 60
```

#### 2.4 查询延迟

```bash
hologres metric query {prefix}query_latency --start "{report_date}T00:00:00" --end "{report_date}T23:59:59" --period 60
```

#### 2.5 查询 QPS

```bash
hologres metric query {prefix}query_qps --start "{report_date}T00:00:00" --end "{report_date}T23:59:59" --period 60
```

**从时序数据中计算**：
- avg / P95 / max 各指标值
- 是否存在连续 1 小时 CPU p95 > 90%
- 是否存在连续 1 小时内存 p95 > 90%
- 是否存在连续 10 分钟连接使用率 > 90%
- 查询延迟 P99 较前一日同期是否上涨 > 50%

**诊断标准**：

| 检查项 | 诊断标准 | 状态 |
|--------|---------|------|
| CPU | 连续 1h p95 > 90% | 紧张 |
| 内存 | 连续 1h p95 > 90% 或存在 OOM | 紧张 |
| 连接数 | 连续 10min > 90% | 紧张 |
| 查询延迟 | P99 较前日上涨 > 50% | 明显波动 |
| Query Queue | 队列长度 > 0 且排队时间 > 500ms | 紧张 |

---

### Step 3: SQL 与任务诊断（Q4）

> 详细查询见 [references/sql-analysis.md](references/sql-analysis.md)

#### 3.1 慢查询 Top N

> 使用 **hologres-slow-query-analysis** skill 的查询逻辑。

```bash
# 按耗时排序的 Top 10 慢查询（按 SQL 指纹聚合）
hologres sql run --no-limit-check "SELECT digest as sql_fingerprint, count(*) as exec_count, round(avg(duration)::numeric, 2) as avg_duration_ms, max(duration) as max_duration_ms, round(avg(cpu_time_ms)::numeric, 2) as avg_cpu_ms, round(avg(memory_bytes/1048576.0)::numeric, 2) as avg_memory_mb, round(avg(read_bytes/1048576.0)::numeric, 2) as avg_read_mb, round(avg(read_rows)::numeric, 0) as avg_read_rows FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'SUCCESS' AND duration > 10000 AND usename <> 'system' GROUP BY 1 ORDER BY max_duration_ms DESC LIMIT 10"
```

#### 3.2 失败查询统计

> 使用 **hologres-instance-health-analyse** skill 的错误分类逻辑。

```bash
# 失败查询按错误类型分类统计
hologres sql run --no-limit-check "SELECT CASE WHEN message ILIKE '%out of memory%' OR message ILIKE '%OOM%' THEN 'OOM' WHEN message ILIKE '%cancel%' OR message ILIKE '%timeout%' THEN 'Timeout/Cancel' WHEN message ILIKE '%permission%' OR message ILIKE '%denied%' THEN 'Permission' WHEN message ILIKE '%does not exist%' OR message ILIKE '%not found%' THEN 'NotFound' WHEN message ILIKE '%syntax error%' THEN 'SyntaxError' WHEN message ILIKE '%connection%' OR message ILIKE '%connect%' THEN 'Connection' WHEN message ILIKE '%duplicate%' OR message ILIKE '%unique%' THEN 'DuplicateKey' WHEN message ILIKE '%lock%' OR message ILIKE '%deadlock%' THEN 'Lock' ELSE 'Other' END as error_category, count(*) as cnt, min(query_start) as first_seen, max(query_start) as last_seen FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'FAILED' AND usename <> 'system' GROUP BY 1 ORDER BY 2 DESC"
```

#### 3.3 Dynamic Table 刷新状态

```bash
# 列出所有 Dynamic Table 及刷新状态
hologres dt list
```

**诊断标准**：
- 慢 SQL（> 10s）> 0 → 需关注，按耗时/频率排序给出 Top N
- 失败查询 > 0 → 需关注，按错误类型分类
- Dynamic Table 刷新延迟超过 freshness 设定值 → 异常
- 同一查询指纹耗时较 7 天基线上涨 > 50% → 退化

---

### Step 4: 存储与成本分析（Q5）

> 详细查询见 [references/cost-capacity.md](references/cost-capacity.md)

#### 4.1 表存储大小排名

```bash
# Top 20 大表
hologres sql run --no-limit-check "SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) as total_size, pg_total_relation_size(schemaname || '.' || tablename) as size_bytes FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'hologres') ORDER BY size_bytes DESC LIMIT 20"
```

#### 4.2 存储使用量趋势

```bash
# 查询近 7 天存储使用量（用于环比和趋势预测）
hologres metric query {prefix}storage_usage --start "{7_days_ago}T00:00:00" --end "{report_date}T23:59:59" --period 3600
```

#### 4.3 冷数据识别

```bash
# 30 天未访问的表（通过 hg_query_log 最后访问时间）
hologres sql run --no-limit-check "SELECT t.schemaname, t.tablename, pg_size_pretty(pg_total_relation_size(t.schemaname || '.' || t.tablename)) as size, pg_total_relation_size(t.schemaname || '.' || t.tablename) as size_bytes FROM pg_tables t WHERE t.schemaname NOT IN ('pg_catalog', 'information_schema', 'hologres') AND NOT EXISTS (SELECT 1 FROM hologres.hg_query_log q WHERE q.query ILIKE '%' || t.tablename || '%' AND q.query_start >= now() - interval '30 days' AND q.usename <> 'system') AND pg_total_relation_size(t.schemaname || '.' || t.tablename) > 1073741824 ORDER BY size_bytes DESC LIMIT 20"
```

**诊断标准**：
- 存储环比增幅 > 10% → 异常增长
- 冷数据（30 天未访问且 > 1GB）→ 可治理

---

### Step 5: 容量预测（Q6）

> 详细预测方法见 [references/cost-capacity.md](references/cost-capacity.md)

基于 Step 2（计算资源）和 Step 4（存储）的数据，做线性趋势外推：

| 资源 | 预测方法 | 风险标准 |
|------|---------|---------|
| 存储 | 近 7 天日均增长量外推 | 预计 30 天内达 80% quota |
| 连接 | 峰值趋势分析 | 预计 30 天内达 80% 最大连接数 |
| CPU | 历史峰值趋势 | 峰值持续接近 90% |
| 表数量 | 当前表数 / 规格上限 | 接近实例规格上限 |

```bash
# 当前表数量
hologres sql run "SELECT count(*) as table_count FROM pg_tables WHERE schemaname NOT IN ('pg_catalog', 'information_schema', 'hologres')"
```

---

### Step 6: 健康评分与报告生成

#### 健康评分计算规则

基线 100 分，各检查项异常按以下规则扣分：

| 检查项 | 异常条件 | 扣分 |
|--------|---------|------|
| 实例状态非 Running | coredump/只读 | -20 |
| 版本已过 EOS | 停止支持 | -10 |
| 版本距 EOS < 3 月 | 即将停止支持 | -5 |
| CPU 连续 1h p95 > 90% | 资源紧张 | -10 |
| 内存连续 1h p95 > 90% | 资源紧张 | -10 |
| 存在 OOM 事件 | 内存溢出 | -15 |
| 连接数连续 10min > 90% | 连接饱和 | -10 |
| 查询延迟 P99 上涨 > 50% | 性能退化 | -5 |
| Query Queue 积压 > 500ms | 排队严重 | -5 |
| 慢 SQL > 10 条 | 性能问题多 | -5 |
| 失败查询 > 10 条 | 错误较多 | -5 |
| 存储环比增幅 > 10% | 存储异常增长 | -5 |
| 存储使用率 > 80% | 容量风险 | -10 |
| 连接峰值 > 80% 上限 | 连接风险 | -5 |
| 当日有重启/coredump | 可用性事件 | -15 |

评分下限为 0 分。最终评分 = max(0, 100 - 总扣分)。

**评分等级**：
- 90-100：健康
- 70-89：基本健康，存在关注项
- 50-69：需要治理
- < 50：严重问题，需立即处理

#### 汇总所有诊断结果，生成日报

按下文"日报标准输出模板"组装最终报告。

---

## 日报标准输出模板

```markdown
# Hologres 运维诊断日报
- 实例：{instance_name} / {region}
- 日期：{report_date}（{weekday}）
- 报告周期：{start_time} ~ {end_time}（北京时间）
- 健康评分：{score}/100（较昨日 {change}）
- 整体状态：{status} | 需关注：{attention} 项 | 可优化：{optimize} 项

## 一、今日摘要
- 整体状态：{summary}
- 关键风险：{top_risks}
- 关键变化：{important_changes}
- 明日预警：{tomorrow_warning}

## 二、实例整体健康状态（Q1）
### 结论
{health_conclusion}

### 关键事实
- 实例状态：{status}
- 实例版本：{version}，EOS 日期：{eos_date}（{version_status}）
- Worker 节点 CPU：{cpu_facts}
- Locks：{locks_facts}
- 连接数：{conn_facts}
- FE replay 延迟：{fe_replay_facts}
- Shard 多副本同步延迟：{shard_replica_facts}

### 分析
{health_analysis}

### 建议
- {health_suggestion_1}
- {health_suggestion_2}

## 三、可用性与稳定性（Q2）
### 结论
{availability_conclusion}

### 关键事实
- 实例自身：{instance_events}
- 平台运维事件：{ops_events}
- 版本升级：{upgrade_events}
- 控制台配置变更：{config_changes}

### 分析
{availability_analysis}

### 建议
- {availability_suggestion_1}

## 四、计算资源情况（Q3）
### 结论
{resource_conclusion}

### 关键事实
| 维度 | 指标 | 平均值 | P95 | 峰值 | 诊断阈值 | 状态 |
|------|------|--------|-----|------|----------|------|
| CPU | 利用率 | {cpu_avg} | {cpu_p95} | {cpu_peak} | 连续1h > 90% | {status} |
| 内存 | 利用率 | {mem_avg} | {mem_p95} | {mem_peak} | 连续1h > 90% | {status} |
| 连接 | 使用率 | {conn_avg} | {conn_p95} | {conn_peak} | 连续10min > 90% | {status} |
| 查询延迟 | P99 耗时 | {lat_avg} | {lat_p95} | {lat_peak} | 较前日上涨 > 50% | {status} |
| Query Queue | 队列长度/排队时间 | {queue_avg} | {queue_p95} | {queue_peak} | 有排队且 > 500ms | {status} |

### 分析
{resource_analysis}

### 建议
- {resource_suggestion_1}
- {resource_suggestion_2}

## 五、任务与 SQL（Q4）
### 结论
{sql_conclusion}

### 关键事实
- SQL 总数：{sql_total}
- 慢 SQL 数（> 10s）：{slow_sql_count}
- 失败查询数：{failed_sql_count}
- Dynamic Table 刷新状态：{dt_status}

### Top 慢 SQL
| 排名 | 查询摘要 | 耗时 | 执行次数 | 根因诊断 | 优化建议 |
|------|----------|------|----------|----------|----------|
| 1 | {top1_sql} | {top1_time} | {top1_count} | {top1_reason} | {top1_suggest} |
| 2 | {top2_sql} | {top2_time} | {top2_count} | {top2_reason} | {top2_suggest} |
| 3 | {top3_sql} | {top3_time} | {top3_count} | {top3_reason} | {top3_suggest} |

### 失败查询
| 错误类型 | 数量 | 首次出现 | 最后出现 | 建议 |
|----------|------|----------|----------|------|
| {err_type} | {err_count} | {first_seen} | {last_seen} | {err_suggest} |

### 分析
{sql_analysis}

### 建议
- {sql_suggestion_1}
- {sql_suggestion_2}

## 六、成本治理（Q5）
### 结论
{cost_conclusion}

### 关键事实
| 维度 | 当前值 | 昨日 | 环比 | 状态 |
|------|--------|------|------|------|
| 存储使用率 | {storage_now} | {storage_yesterday} | {storage_change} | {status} |
| 冷数据 | {cold_data} | — | — | {status} |

- 存储增长来源：{growth_sources}
- 冷数据（30 天未访问）：{cold_data_tables}

### 分析
{cost_analysis}

### 建议
- {cost_suggestion_1}
- {cost_suggestion_2}

## 七、容量预测与风险预警（Q6）
### 结论
{capacity_conclusion}

### 关键事实
| 资源 | 当前使用率 | 预计达 80% 时间 | 风险等级 |
|------|------------|-----------------|----------|
| 存储 | {storage_rate} | {storage_forecast} | {risk} |
| 连接 | {conn_rate} | {conn_forecast} | {risk} |
| CPU | {cpu_rate} | {cpu_forecast} | {risk} |
| 表数量 | {table_rate} | {table_forecast} | {risk} |

### 分析
{capacity_analysis}

### 建议
- {capacity_suggestion_1}
- {capacity_suggestion_2}

## 八、今日治理建议汇总
### 立即处理（P0）
- {action_p0_1}
- {action_p0_2}

### 近期治理（P1）
- {action_p1_1}
- {action_p1_2}

### 规划优化（P2）
- {action_p2_1}
- {action_p2_2}

## 九、附录：数据说明
- 数据周期：{start_time} ~ {end_time}（北京时间）
- 诊断生成时间：{gen_time}
- 数据来源：Hologres 系统表、云监控、慢查询日志
- 指标口径说明：
  - 慢 SQL：执行时间 > 10s 或超过近 7 天 P95 基线
  - CPU/内存紧张：连续 1 小时 p95 > 90%
  - 连接数紧张：连续 10 分钟 > 90%
  - 查询延迟波动：P99 较前一日同期上涨 > 50%
  - Query Queue 紧张：队列长度 > 0 且平均排队时间 > 500ms
  - 存储异常：环比增幅 > 10%
  - 冷数据：30 天未访问的表
```

---

## 日报风格原则

1. **结论先行**：每个问题先给一句话结论，再展开细节
2. **数据说话**：所有诊断必须有定量数据支撑，拒绝模糊描述
3. **根因必达**：不仅告诉用户"是什么"，更要解释"为什么"
4. **建议可执行**：每条建议要具体、可操作、有明确收益预期
5. **分级呈现**：让用户一眼识别优先级（正常 / 关注 / 需处理）
6. **上下文感**：包含环比、同比、历史基线，让用户理解"异常"的相对性
7. **行动闭环**：日报不止于诊断，必须输出可执行的 To-Do 清单

## 执行指导

### 环境准备

```bash
export HOLOGRES_SKILL=hologres-daily-report
```

### 执行顺序

1. 先执行 Step 1（实例基础信息），确认实例可连接
2. 并行执行 Step 2（计算资源）和 Step 3（SQL 诊断）和 Step 4（存储成本）
3. Step 5（容量预测）依赖 Step 2 和 Step 4 的结果
4. Step 6（评分与报告生成）汇总所有结果

### 错误处理

- 如果 `hologres metric` 命令报错（如未配置云监控凭证），跳过计算资源指标采集，在日报中标注"云监控数据不可用"
- 如果 `hg_query_log` 查询失败（权限不足），跳过 SQL 诊断，在日报中标注"慢查询数据不可用"
- 任何步骤失败不阻塞其他步骤，确保日报尽可能完整

### 数据不足时的处理

- 缺少云监控数据时，Q3（计算资源）和 Q6（容量预测）中的 CPU/内存/连接指标标注为"N/A"
- 缺少 hg_query_log 数据时，Q4（SQL 诊断）标注为"数据不可用"
- 首次生成日报无历史对比数据时，"较昨日"变化项标注为"首次报告"

## 依赖的 Skill 与工具

| Skill / 工具 | 用途 | 涉及日报章节 |
|--------------|------|-------------|
| **hologres-cli** | 所有 CLI 命令执行基础 | 全部 |
| **hologres-diagnosis-cpu** skill | CPU 指标前缀约定、CPU 状态分级逻辑 | Q1、Q3、Q6 |
| **hologres-slow-query-analysis** skill | 慢查询分析 SQL 和根因判断规则 | Q4 |
| **hologres-instance-health-analyse** skill | 错误分类逻辑、Warehouse 资源查询 SQL | Q1、Q4 |
| **hologres-query-optimizer** skill | 单条慢 SQL 的执行计划分析（可选深入） | Q4（深入分析时） |

## 参考文档

| 文档 | 内容 |
|------|------|
| [references/health-check.md](references/health-check.md) | Q1 实例健康 + Q2 可用性：详细诊断 SQL 和判断逻辑 |
| [references/resource-analysis.md](references/resource-analysis.md) | Q3 计算资源：详细指标查询命令和阈值 |
| [references/sql-analysis.md](references/sql-analysis.md) | Q4 SQL/任务：详细查询和分析逻辑 |
| [references/cost-capacity.md](references/cost-capacity.md) | Q5 成本治理 + Q6 容量预测：详细查询和预测方法 |

## 注意事项

1. 所有时间使用北京时间（`Asia/Shanghai`），SQL 中的时间戳带时区
2. `hg_query_log` 默认保留 30 天数据，超出范围的历史对比可能不可用
3. 大表排名查询可能较慢（遍历系统表），建议设置 `statement_timeout`
4. 云监控指标粒度最细为 60s，部分指标可能有 1-2 分钟延迟
5. 健康评分仅作为参考指标，具体问题需结合诊断详情判断
6. 日报中所有"建议"应标注优先级（P0/P1/P2）和建议完成时间
7. 首次生成日报时，建议先运行 `hologres status` 确认连接正常
8. **无数据降级策略**：当 `hg_query_log` 在指定日期无任何用户查询时，Q4（SQL 诊断）章节应明确输出"当日无用户查询"，而非留空或报错；同时跳过慢 SQL Top N、失败查询统计、退化检测等依赖查询日志的子步骤，在日报中标注"当日无查询数据，相关诊断项已跳过"
