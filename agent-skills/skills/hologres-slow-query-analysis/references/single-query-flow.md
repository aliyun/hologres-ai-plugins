# 单条 SQL 分析 — 5 步

当用户提供 `query_id` 时，按序执行这 5 步。完整输出覆盖 基本信息 → 慢因逐维拆解 → 根因 → 优先级建议。

所有 SQL 经 `hologres sql run --no-limit-check "<SQL>"` 执行。连接层已自动路由到 serverless 池并标记来源，无需手写 `SET ...`（见 [preconditions.md §1](preconditions.md)）。

---

## Step 1 — 定位 SQL 记录

**意图**：按 `query_id` 拉取完整记录。

```bash
hologres sql run --no-limit-check "SELECT query_id, digest, usename, application_name, client_addr, status, command_tag, duration, query_start, query_end, read_rows, read_bytes, result_rows, result_bytes, cpu_time_ms, memory_bytes, shuffle_bytes, physical_reads, table_read, table_write, query, plan, statistics, agg_stats, query_detail, query_extinfo, extended_info, visualization_info, extended_cost FROM hologres.hg_query_log WHERE query_id = '{query_id}'"
```

**输出模板**

```
【SQL 基本信息】
- SQL 标识：{query_id}
- SQL 原文：{完整 query，不可截断}
- 用户：{usename}
- 应用：{application_name}
- 客户端：{client_addr}
- 状态：{status}
- 执行时间：{query_start} ~ {query_end}
- 耗时：{duration}
- 结论：{summary}
```

---

## Step 2 — 慢在哪里？（逐维）

**意图**：读各指标，判定该维度是否瓶颈。

| 维度 | 指标 |
|------|------|
| 扫描 | `read_rows`, `read_bytes` |
| 过滤 | `read_rows / result_rows` 比值 |
| 返回 | `result_rows`, `result_bytes` |
| 内存 | `memory_bytes` |
| CPU | `cpu_time_ms` |
| IO | `physical_reads` |
| 引擎 | `engine_type`（HQE / PQE / SDK·FixedQE / PG，详见 [preconditions.md §5](preconditions.md)） |

阈值式规则（扫描过大 / 过滤不够 / 内存压力 / IO 压力 / CPU 压力 / 表设计）见 [diagnosis-rules.md](diagnosis-rules.md)。

**输出模板**

```
【慢因诊断】
- 扫描情况：{是否扫描过大}
- 过滤情况：{是否有效过滤}
- Join 情况：{是否 Join 代价高}
- 聚合 / 排序情况：{是否有大聚合 / 排序}
- 内存情况：{是否有内存压力}
- CPU 情况：{是否有 CPU 压力}
- 表设计 / SQL 写法：{是否存在问题}
- 引擎分析：{HQE / PQE / SDK·FixedQE / PG 的使用情况与影响}
- 结论：{summary}
```

---

## Step 3 — 计划与统计深挖

**意图**：结合 `query`、`plan`、`statistics`、`agg_stats`、`query_detail`、`query_extinfo`、`extended_info`、`table_read`、`table_write` 解释为何慢。

### 引擎子检查清单（必做）

- **出现 PQE** → 找不支持的函数 / 表达式 / 复杂 cast / 不可下推算子；改写使逻辑回到 HQE。
- **主要为 SDK / FixedQE** → 负载为点读 / 点写 / 前缀扫描时合理；否则检查优化空间。
- **PG** → 通常系统目录 / DDL；若是用户数据查询，本身就是红旗。
- **主要为 HQE** → 执行路径通常健康；仍交叉检查资源指标 + 计划的其他瓶颈。

**输出模板**

```
【慢因诊断】
- 扫描情况：{是否扫描过大}
- 过滤情况：{是否有效过滤}
- Join 情况：{是否 Join 代价高}
- 聚合 / 排序情况：{是否有大聚合 / 排序}
- 内存情况：{是否有内存压力}
- CPU 情况：{是否有 CPU 压力}
- 执行引擎情况：{推荐使用 HQE / 当前 engine_type 是否合理}
- 表设计 / SQL 写法：{是否存在问题}
- 结论：{summary}
```

---

## Step 4 — 原因总结

**意图**：陈述主 / 次要瓶颈与最优先修改点。

```
【原因总结】
- 主瓶颈：{primary_reason}
- 次要瓶颈：{secondary_reason}
- 解释：{why_slow}
- 最优先修改点：{first_action}
```

常见原因分类：
- 扫描量大
- 返回量少（大扫描小返回）
- Join 成本高
- 聚合 / 排序重
- 内存占用高
- CPU 消耗高
- 表设计不合理（分布键 / 分区 / 索引）
- SQL 写法不合理（缺过滤、返回列过多、子查询过重）

---

## Step 5 — 优化建议

**意图**：给出可执行、有序的建议。

常见手段：
- 增加过滤条件
- 减少扫描列 / 扫描行
- 调整 Join 顺序
- 减少返回数据量
- 调整表分布键 / 分区键 / 索引
- 采用预聚合或拆分查询

**输出模板**

```
【优化建议】
- 最核心优化点：{core_suggestion}
- 高收益建议：{high_value_suggestions}
- 辅助建议：{secondary_suggestions}
- 优先级顺序：{priority_order}
- 结论：{summary}
```

单条 SQL 分析的完整必含输出项见 [output-spec.md](output-spec.md)。
