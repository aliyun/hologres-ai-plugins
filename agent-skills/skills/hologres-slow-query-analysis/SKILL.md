---
name: hologres-slow-query-analysis
depends: [hologres-cli]
description: |
  Hologres slow query log analysis and diagnosis skill. Use for analyzing slow queries,
  failed queries, query performance diagnosis, and log management in Alibaba Cloud Hologres.
  All SQL is executed via `hologres sql run` (`hologres sql run --no-limit-check`).
  Triggers: "hologres slow query", "hg_query_log", "query diagnosis", "慢Query分析", "Hologres性能诊断"
---

> ⚠️ **执行前就绪检查（所有分析步骤之前完成）**：
> 1. 已 `pip install hologres-cli`，且 `hologres status` 能连通目标实例（连接哪个实例 / 库由当前 profile 决定，可用 `--profile <name>` 切换）。
> 2. `export HOLOGRES_SKILL=hologres-slow-query-analysis`，便于事后审计。
>
> RAM 权限、慢日志读授权（`pg_read_all_stats` / `spm_grant`）、版本矩阵、引擎类型语义见 [references/preconditions.md](references/preconditions.md)。

# Hologres 慢 SQL 分析

基于 `hologres.hg_query_log` 视图分析 Hologres 实例的慢 SQL，输出**结构化诊断结论 + 优化建议**，回答：哪些 SQL 最值得优先优化、为什么慢、应当怎么优化。所有 SQL 通过 `hologres sql run --no-limit-check` 执行。

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `start_time` | 是 | 分析开始时间，ISO-8601（北京时间须带 `+08:00`） |
| `end_time` | 是 | 分析结束时间，格式同 `start_time` |
| `query_id` | 否 | 单条 SQL 标识；提供时优先做单条 SQL 分析 |

> 数据库由当前 profile 的 `database` 决定，无需也无法在命令上指定 `--db-name`；换库用 `hologres config set database <db>` 或 `--profile <name>`。

## 决策逻辑

| 输入条件 | 执行流程 | 详见 |
|----------|----------|------|
| 未提供 `query_id` | **实例整体慢 SQL 分析** — 6 步：总体汇总 → 多维画像 → 优先优化对象 → 重点 SQL 深挖 → 错误 SQL 分类 → 最终结论 | [references/instance-flow.md](references/instance-flow.md) |
| 提供了 `query_id` | **单条 SQL 分析** — 5 步：定位记录 → 慢因维度判断 → 计划/统计深挖 → 原因总结 → 优化建议 | [references/single-query-flow.md](references/single-query-flow.md) |

每个步骤的具体 SQL、输出模板、判定阈值都在对应 references 文件中。**每个诊断项都必须输出固定格式的总结**，模板见 [output-spec.md](references/output-spec.md)。

## 实例整体慢 SQL 分析（intent overview）

| Step | 目的 | 主要查询 / 规则 |
|------|------|------------------|
| 1 | 拉取时间段内 SQL 总量 / 成功 / 失败 | [instance-flow §1](references/instance-flow.md) |
| 2 | 按 digest / 用户 / 应用 / SQL 类型 / 读写表 / 资源等多维度做整体画像 | [instance-flow §2](references/instance-flow.md)（独立 SQL 之间应**并行**执行） |
| 3 | 选出最该优先优化的 SQL（P0 / P1 / P2） | 优先级判定见 [diagnosis-rules.md](references/diagnosis-rules.md) |
| 4 | 对重点 SQL 做 plan / statistics / 资源特征深挖 | [instance-flow §4](references/instance-flow.md) |
| 5 | 错误 SQL 按 SQLSTATE 分类汇总 | [instance-flow §5](references/instance-flow.md) + [error-codes.md](references/error-codes.md) |
| 6 | 输出最终结论 + 优化清单（含 `query_id` 与完整 SQL 原文，不可截断） | [instance-flow §6](references/instance-flow.md) + [output-spec.md](references/output-spec.md) |

## 单条 SQL 分析（intent overview）

| Step | 目的 | 关键内容 |
|------|------|----------|
| 1 | 通过 `query_id` 拉取完整记录 | [single-query-flow §1](references/single-query-flow.md) |
| 2 | 判断慢在哪里（扫描 / 过滤 / 内存 / CPU / 引擎） | `duration / read_bytes / memory_bytes / cpu_time_ms / engine_type` |
| 3 | 结合 `plan / statistics / agg_stats / query_detail / extended_info` 深挖慢因 | 引擎子检查清单见 [single-query-flow §3](references/single-query-flow.md) |
| 4 | 输出主 / 次要瓶颈与首要修改点 | 慢因判断规则见 [diagnosis-rules.md](references/diagnosis-rules.md) |
| 5 | 给出可执行的优化建议（核心 / 高收益 / 辅助） | [single-query-flow §5](references/single-query-flow.md) |

## 输出模板总则

每个诊断项必须采用以下固定格式输出（具体字段在各 step 模板内细化）：

```
【诊断项名称】
- 指标口径：{统计口径说明}
- 关键结果：{核心数值或 Top 对象（含 query_id）}
- 典型完整 SQL：query_id={...}，SQL={完整 query 原文，不可截断}
- 现象总结：{现象描述}
- 原因判断：{原因分析}
- 建议：{优化建议}
- 结论：{一句话总结}
```

完整输出规范（标题 / 分析人 / 引擎类型规则 / 实例级 vs 单条 SQL 输出清单）见 [references/output-spec.md](references/output-spec.md)。

## References

| 主题 | 文件 |
|------|------|
| 前置依赖 / 版本 / 权限 / `hg_query_log` 字段 / 引擎类型语义 | [preconditions.md](references/preconditions.md) |
| 实例整体慢 SQL 分析 6 步流程（含 SQL + 输出模板） | [instance-flow.md](references/instance-flow.md) |
| 单条 SQL 分析 5 步流程（含 SQL + 输出模板） | [single-query-flow.md](references/single-query-flow.md) |
| 优先优化规则 + 慢因判断规则 | [diagnosis-rules.md](references/diagnosis-rules.md) |
| 输出规范（标题 / 分析人 / 引擎规则 / 输出清单） | [output-spec.md](references/output-spec.md) |
| SQLSTATE 错误码完整映射（PostgreSQL + Hologres） | [error-codes.md](references/error-codes.md) |
| 补充诊断 SQL 库（new-query / 流量 / 高峰期等） | [diagnostic-queries.md](references/diagnostic-queries.md) |
| 慢日志导出（内表 / OSS） | [log-export.md](references/log-export.md) |
| 日志配置参数（`log_min_duration_statement` 等） | [configuration.md](references/configuration.md) |

## 注意事项

1. `hologres.hg_query_log` 默认保留约一个月，单次最多 10000 条；查询必须带 `query_start` 范围条件，不要用 `to_char(query_start, ...)` 包裹（无法走索引）。
2. `engine_type` 为数组类型，聚合时使用 `engine_type::text`；FixedQE 类 SQL 在慢 SQL 诊断中通常**不是瓶颈**，建议在 digest 聚合 SQL 中过滤 `engine_type::text NOT LIKE '%FixedQE%'`（详见 [instance-flow §2.1](references/instance-flow.md)）。
3. `digest` 字段从 V2.2 起支持，低版本实例为空，需降级为按 `query` 文本聚合。
4. 输出错误 SQL / 优先优化对象 / 重点 SQL 时，`query` 原文**不可截断**，且必须随附 `query_id`。
5. **当 `hologres sql run` 返回空结果（无数据）时，禁止自行修改参数重试或变通获取数据；直接跳过该步骤，在输出结果中标注「无数据」。**
