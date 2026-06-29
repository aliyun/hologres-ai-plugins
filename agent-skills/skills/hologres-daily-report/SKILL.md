---
name: hologres-daily-report
depends: [hologres-cli]
description: >
  Hologres 运维诊断日报生成技能。生成一份"诊断结论 + 根因解释 + 行动建议"的每日巡检报告，
  覆盖实例健康、可用性、计算资源、SQL 性能、成本治理、容量预测六大维度。
  触发词：日报、每日巡检、daily report、运维日报、诊断日报、实例巡检报告、每日健康报告。
  实例 / 计算组 / SQL 数据通过 `hologres instance-manage get` / `hologres warehouse` / `hologres sql run` 获取；云监控数据通过 `hologres metric query` 获取。
---

> ⚠️ **执行前就绪检查（所有采集步骤之前完成）**：
> 1. 已 `pip install hologres-cli`，且 `hologres status` 能连通目标实例（连接哪个实例 / 库由当前 profile 决定，可用 `--profile <name>` 切换）。
> 2. 云监控 AK/SK 已就绪（`hologres metric config` 专用配置，或 profile 通用 AK/SK，或默认凭证链）。
> 3. `export HOLOGRES_SKILL=hologres-daily-report`，便于事后审计。
>
> 完整就绪细节（凭证优先级 / RAM 权限 / 前缀判定 / 时间格式）见 [references/preconditions.md](references/preconditions.md)。

# Hologres 运维诊断日报

不是监控面板的数据搬运，而是一份由 AI 助手生成的**"诊断结论 + 根因解释 + 行动建议"型日报**。

## 输入参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `instance_id` | 实例 ID（如 `hgprecn-cn-xxx`，传给 `hologres metric` 的 `--instance-id`） | 用户指定 / 当前 profile |
| `report_date` | 报告日期 | 昨天（`YYYY-MM-DD`） |
| `region` | 实例所在 Region（如 `cn-hangzhou`） | 默认从 profile `region_id` 读取 |
| `time_range` | 诊断时间窗口 | `{report_date} 00:00 ~ 23:59`（北京时间） |

> 数据库由当前 profile 的 `database` 决定，无需也无法在命令上指定 `--db-name`；如需换库用 `hologres config set database <db>` 或 `--profile <name>`。

### 时间窗口约束

日报只诊断 **最近 30 天内、且跨度不超过 24 小时** 的数据。校验规则（按顺序执行）：

1. **30 天有效期**：`start_time` 必须满足 `start_time >= current_time - 30d`（`hg_query_log` 默认保留 30 天）。若早于 30 天前，**拒绝执行**并提示：
   > ⚠️ 诊断时间范围超出 hg_query_log 保留期（30 天），请重新指定 start_time >= {30天前日期}。
2. **24 小时跨度上限**：若 `end_time - start_time > 24小时`，**自动将 `start_time` 重置为 `end_time - 24h`**，并在报告开头说明实际使用的时间范围。
3. **默认值**：若未传入 `--start-time` / `--end-time`，默认使用 `{report_date} 00:00:00 ~ 23:59:59`（昨天整天）。

## hologres-cli 约定

- 元仓 / PG 系统表查询统一用 `hologres sql run --no-limit-check "<SQL>"`。
- 云监控指标用 `hologres metric query <metric> --instance-id <id> --start-time <s> --end-time <e> --period <p>`；`instanceId` 由 CLI 自动注入。
- 指标名前缀（`standard_` / `warehouse_` / ...）需由 `hologres instance-manage get` 判定后拼进 metric 名（见 preconditions §5）。
- 时间格式：`hologres metric` 接受 ISO-8601 或 epoch ms，无时区 ISO 串按 UTC 解析，北京时间显式带 epoch ms 或 `+08:00`。
- 连接层已自动 `SET hg_computing_resource = 'serverless'`；来源标记由 `export HOLOGRES_SKILL` 注入，**无需** 手写 `SET ...` 前缀。
- 独立命令可在同一轮并行下发以加速。

## 数据采集与诊断流程

六步。每步只列「意图 + 下发哪些命令」；完整 SQL、阈值表、结果处理逻辑见 `references/`。

### Step 1 — 实例基础信息（Q1 健康 + Q2 可用性）

详见 [references/health-check.md](references/health-check.md)。并行下发：
- `hologres instance-manage get` —— 实例状态、版本、类型、规格（同时确定 `{prefix}`）。
- `hologres warehouse` —— 计算组 / 资源布局。
- `hologres sql run --no-limit-check` 查 `pg_stat_activity`、`pg_locks`、`hologres.hg_query_log`，统计连接数、锁等待、长阻塞会话、`{report_date}` 当日 DDL 事件。

诊断：实例非 Running → 严重；版本过 EOS 或 < 3 个月到期 → 关注；等待锁 > 10 或任一阻塞 > 30s → 异常；DDL 事件计入可用性事件。

### Step 2 — 计算资源指标（Q3）

详见 [references/resource-analysis.md](references/resource-analysis.md)。先 `hologres instance-manage get` 取一次确定 `{prefix}`（preconditions §5）。然后并行下发 `hologres metric query`：`{prefix}cpu_usage`、`{prefix}memory_usage`、`{prefix}connections`、`{prefix}query_latency`、`{prefix}query_qps`，均 `--period 60` 覆盖全天。

从时序计算 avg / P95 / max，对照 `resource-analysis.md` 阈值表（CPU/内存连续 1h p95 > 90%；连接 10min > 90%；P99 延迟环比 > 50%；队列长度 > 0 且等待 > 500ms）。

### Step 3 — SQL 与任务诊断（Q4）

详见 [references/sql-analysis.md](references/sql-analysis.md)。并行下发：
- 从 `hologres.hg_query_log` 按 `digest` 聚合的 Top-N 慢查询（`duration > 10s`）。
- 失败查询分类（`status = 'FAILED'`，对 `message` 做正则：OOM / Timeout / Permission / NotFound / SyntaxError / Connection / DuplicateKey / Lock / Other）。
- Dynamic Table 刷新状态：`hologres dt list`（或 `SELECT * FROM hologres.hg_dynamic_tables`）。

诊断：慢 SQL > 0 → 列 Top-N（按耗时 / 频次）；同 digest 耗时 > 7 天基线 +50% → 退化。

### Step 4 — 存储与成本（Q5）

详见 [references/cost-capacity.md](references/cost-capacity.md)。并行下发：
- Top-20 大表：`hg_table_info`（`hot_storage_size + cold_storage_size`）。
- 7 天存储趋势：`storage_usage_percent`、`warehouse_hot_storage_used`（CMS，`--period 3600`）。
- 冷数据表：`hg_table_info` 中 `last_access_time < now() - 30 days` 且 `> 1GB`。

诊断：存储环比 > 10% → 异常增长；冷数据 > 1GB 且 30 天未访问 → 可治理。

### Step 5 — 容量预测（Q6）

详见 [references/cost-capacity.md](references/cost-capacity.md)。基于 Step 2/4 已采数据线性外推。风险阈值：存储 / 连接预计 30 天内达 80%；CPU 峰值持续接近 90%；表数量逼近实例上限。另取当前表数量（`hg_table_info`，排除系统 schema）。

### Step 6 — 健康评分与报告生成

评分规则与分档：[references/health-check.md](references/health-check.md)。最终报告骨架（顶层布局 + 八节完整 Markdown body）：[references/report-template.md](references/report-template.md)。

汇总 Step 1–5，计算评分，填模板。所有占位符必须用真实查询结果填充，不得编造。

## 日报风格原则

1. **结论先行**：每问先一句话结论，再展开细节。
2. **数据说话**：所有诊断必须有定量数据；拒绝模糊描述。
3. **根因必达**：不仅"是什么"，更要"为什么"。
4. **建议可执行**：具体、可操作、有明确收益预期。
5. **分级呈现**：正常 / 关注 / 需处理 一眼可识别。
6. **上下文感**：包含环比、同比、历史基线。
7. **行动闭环**：必须输出可执行 To-Do（P0/P1/P2 + 时间要求）。
8. **禁止截断 / 隐藏任何内容**：报告中的 `digest`（指纹 ID）、`query_id`、`query` 原文等字段必须完整输出，不得使用 `left()`、`substr()`、`::char(N)` 或任何截断函数，不得用 `...` 省略。如果内容过长，仍然必须全文展示。

## 执行指导

执行顺序：

1. 先 Step 1 确认可达性并确定 `{prefix}`。
2. **并行 Step 2 + Step 3 + Step 4** —— 三者无相互依赖。
3. Step 5 依赖 Step 2 与 Step 4。
4. Step 6 汇总。

错误处理：

- CMS 错误（认证 / 未知指标）→ 跳过 Q3 时序，标注「云监控数据不可用」。
- SQL 权限错误 → 提示用户核对 PG 权限。
- `hg_query_log` 拒绝访问 → 跳过 Q4，标注「慢查询数据不可用」。
- **CLI 返回空结果（无数据）→ 禁止自行改参重试或变通获取；直接跳过该步骤，在输出中标注「无数据」。**
- 任一步失败均非阻断；报告应基于已得证据继续渲染。

数据缺口处理：

- 缺 CMS 数据 → Q3/Q6 的 CPU/Mem/Conn 字段标 `N/A`。
- 缺 `hg_query_log` → Q4 标 `数据不可用`。
- 首次运行 / 无历史基线 → 「较昨日」标 `首次报告`。
- 当日 `hg_query_log` 为空 → 标「当日无用户查询」并跳过 Top-N / 失败 / 退化子步骤。

## 依赖的 Skill 与工具

| Skill / 工具 | 用途 | 涉及章节 |
|--------------|------|----------|
| `hologres-cli`（`sql run` / `metric` / `instance-manage` / `warehouse` / `dt`） | 所有 SQL / 实例 / 计算组 / 云监控执行 | All |
| `hologres-diagnosis-cpu` skill | 指标前缀规则、CPU 分级逻辑 | Q1 / Q3 / Q6 |
| `hologres-diagnosis-memory` skill | OOM 检测、内存分类规则 | Q3 / Q4 |
| `hologres-query-optimizer` skill | 慢查询计划深挖与优化 | Q4 |

## References

| File | Content |
|------|---------|
| [references/preconditions.md](references/preconditions.md) | 安装 / 凭证优先级 / RAM 权限 / 前缀判定 / 时间格式 |
| [references/health-check.md](references/health-check.md) | Q1 / Q2 detail SQL + 评分规则 |
| [references/resource-analysis.md](references/resource-analysis.md) | Q3 指标查询与阈值 |
| [references/sql-analysis.md](references/sql-analysis.md) | Q4 慢 / 失败查询 SQL |
| [references/cost-capacity.md](references/cost-capacity.md) | Q5 + Q6 存储与预测 |
| [references/report-template.md](references/report-template.md) | 完整 Markdown 报告骨架 |

## 注意事项

1. 全部使用北京时间（`Asia/Shanghai`）；SQL 时间戳带时区。
2. `hg_query_log` 保留 30 天 —— 超期的历史对比可能不可用。
3. 大表 size 查询可能较慢；必要时设 `statement_timeout`。
4. CMS 指标最细粒度 60s；部分指标滞后 1–2 分钟。
5. 健康评分仅供参考 —— 根因判断仍依赖完整诊断。
6. 每条建议必须带优先级（P0/P1/P2）与目标完成时间。
