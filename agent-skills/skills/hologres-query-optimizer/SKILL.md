---
name: hologres-query-optimizer
depends: [hologres-cli]
description: |
  Hologres Query Execution Plan Analyzer and Optimizer. Use for analyzing SQL performance issues,
  understanding EXPLAIN/EXPLAIN ANALYZE output, interpreting query operators, and providing
  optimization recommendations for Hologres queries. Users may provide a query_id, raw SQL query,
  or pasted EXPLAIN ANALYZE result text.
  SQL execution / 慢日志查询通过 `hologres sql run` / `hologres sql explain`；GUC 通过 `hologres guc` 操作。
  Triggers: "hologres explain", "query plan", "execution plan", "sql optimization", "query performance",
  "hologres performance", "slow query", "query optimizer", "explain analyze", "query_id"
---

> ⚠️ **执行前就绪检查（所有分析步骤之前完成）**：
> 1. 已 `pip install hologres-cli`，且 `hologres status` 能连通目标实例（连接哪个实例 / 库由当前 profile 决定，可用 `--profile <name>` 切换）。
> 2. `export HOLOGRES_SKILL=hologres-query-optimizer`，便于事后审计。
>
> 完整就绪细节（权限 / GUC 作用域）见 [references/preconditions.md](references/preconditions.md)。

# Hologres Query Execution Plan Analyzer

基于 `EXPLAIN` / `EXPLAIN ANALYZE` 与慢查询日志记录分析并优化 Hologres SQL。支持三种输入:`query_id`、原始 SQL、粘贴的 `EXPLAIN ANALYZE` 文本。文档目标 Hologres V1.3.4x+。所有 SQL 通过 `hologres sql run` / `hologres sql explain` 执行,GUC 通过 `hologres guc` 操作。

## hologres-cli 约定

- 慢日志 / 原始 SQL 查询用 `hologres sql run --no-limit-check "<SQL>"`。
- 执行计划用 `hologres sql explain "<SQL>"`(内部执行 `EXPLAIN <SQL>`)。`EXPLAIN ANALYZE` 需用 `hologres sql run --no-limit-check "EXPLAIN ANALYZE <SQL>"`。
- GUC 库级持久化用 `hologres guc set <param> <value>` / `hologres guc reset <param>`;查看用 `hologres guc show <param>` / `hologres guc list`。
- 连接层已自动 `SET hg_computing_resource = 'serverless'`;来源标记由 `export HOLOGRES_SKILL` 注入 `application_name`,**无需** 手写 `SET ...` 前缀。
- 输出 `query` / `query_id` / `plan` 必须完整,**禁止** 用 `left()` / `substr()` / `::char(N)` 截断。
- 数据库由当前 profile 的 `database` 决定;换库用 `hologres config set database <db>` 或 `--profile <name>`。

## Supported Inputs

| 用户输入 | 必需动作 |
|----------|----------|
| `query_id` | 先查慢日志记录;分析记录中的 `plan` / `statistics` / 阶段耗时 / 资源指标。见 [references/slow-log-lookup.md](references/slow-log-lookup.md)。 |
| 原始 SQL | 安全且允许时跑 `EXPLAIN ANALYZE <sql>`;否则跑 `EXPLAIN <sql>` 并说明无运行时指标。 |
| 粘贴的 `EXPLAIN ANALYZE` 文本 | 直接分析提供计划;除非需额外验证,否则不执行 SQL。 |

当用户提供 `query_id` 时,**不要** 让用户先贴 SQL/计划 —— 直接查 `hologres.hg_query_log`。它记录已完成 SQL,字段含 `query_id`、`query`、`plan`、`statistics`、`duration`、`optimization_cost`、`start_query_cost`、`get_next_cost`、`read_bytes`、`shuffle_bytes`、`memory_bytes`、`cpu_time_ms`、`engine_type`、`table_read`、`query_detail`。

## EXPLAIN vs EXPLAIN ANALYZE

| 命令 | 说明 |
|------|------|
| `EXPLAIN <sql>` | 显示 QO 的**估算**计划,仅供参考。`hologres sql explain "<sql>"`。 |
| `EXPLAIN ANALYZE <sql>` | 显示**实际**计划与真实运行时指标,用于优化。会执行查询。 |

```sql
EXPLAIN SELECT * FROM my_table WHERE id > 100;
EXPLAIN ANALYZE SELECT * FROM my_table WHERE id > 100;
```

## Query ID 工作流

1. 查慢日志记录。完整 SQL、结果处理矩阵、阶段症状映射见 [references/slow-log-lookup.md](references/slow-log-lookup.md)。
2. 若 `plan` 非空,连同同记录的阶段/资源指标一起分析。
3. 若 `plan` 为空但 `query` 存在,跑 `EXPLAIN <query>`;仅在确认重跑安全后才跑 `EXPLAIN ANALYZE`。
4. 若查无结果,请用户放宽 `query_start` 范围或提供 SQL / EXPLAIN ANALYZE 文本。

## Reading EXPLAIN Output

自底向上读计划,每个 `->` 是一个节点/算子。

| 参数 | 说明 |
|------|------|
| `cost` | 估算代价:`startup_cost..total_cost`。父节点含子节点代价。 |
| `rows` | 估算输出行数。**`rows=1000` 提示统计信息缺失** —— 跑 `ANALYZE <table>`。 |
| `width` | 估算平均输出宽度(字节)。 |

## Reading EXPLAIN ANALYZE Output

输出四节:**Query Plan**、**ADVICE**、**Cost**、**Resource**。

### Query Plan Metrics

格式:`[dop_in:dop_out id=X dop=N time=max/avg/min rows=total(max/avg/min) mem=max/avg/min open=X get_next=Y]`

| 指标 | 说明 |
|------|------|
| `dop_in:dop_out` | 并行比(如 `21:1` gather、`21:21` shuffle) |
| `dop` | 实际并行度(匹配 shard 数) |
| `time` | 总耗时 = open + get_next(ms),自子节点**累加** |
| `rows` | 输出行:`total(max/avg/min)`,方差大 = 数据倾斜 |
| `mem` | 内存:`max/avg/min` |
| `open` | 初始化耗时,Hash 算子在此建表 |
| `get_next` | 取数耗时,反复调用直到完成 |

> `time` 累加。当前算子耗时 = 当前 time − 子节点 time。

### ADVICE Section

系统自动建议:
- 缺索引:`Table xxx misses bitmap index`
- 缺统计:`Table xxx Miss Stats! please run 'analyze xxx';`
- 数据倾斜:`shuffle data skew! max rows is X, min rows is Y`

### Cost Breakdown

| 指标 | 说明 |
|------|------|
| Total cost | 查询总耗时(ms) |
| Optimizer cost | QO 生成计划耗时 |
| Start query cost | 执行前初始化(schema 同步、加锁) |
| Get the first block cost | 首批记录耗时 |
| Get result cost | 全部结果耗时 |

### Resource Consumption

格式:`total(max_worker/avg_worker/min_worker)`

| 指标 | 说明 |
|------|------|
| Memory | 总量与每 worker 内存 |
| CPU time | 跨核累计 CPU 时间 |
| Physical read bytes | 磁盘读(cache miss) |
| Read bytes | 总读(磁盘 + cache) |

## Common Operators

详细算子参考:[references/operators.md](references/operators.md)。

| 分组 | 算子 | 说明 |
|------|------|------|
| Scan | Seq Scan | 全表扫描 |
| Scan | Index Scan using Clustering_index | 列存索引扫描 |
| Scan | Index Seek (pk_index) | 行存主键扫描 |
| Filter | Filter | 未命中索引 —— **加索引** |
| Filter | Segment / Cluster / Bitmap Filter | Segment / clustering / bitmap 索引命中 |
| Movement | Local Gather / Gather | shard 内合并 / 跨 shard 合并 |
| Movement | Redistribution | 数据 shuffle —— **检查 distribution_key** |
| Movement | Broadcast | 小表广播到全 shard |
| Join | Hash Join | Hash 连接(确保小表做 hash 表) |
| Join | Nested Loop | **大表慎用** |
| Join | Cross Join | 优化的非等值连接(V3.0+) |
| Aggregation | HashAggregate / Partial / Final HashAggregate | Hash 聚合,可能多阶段 |
| Other | Sort / Limit / ExecuteExternalSQL | ORDER BY / 行数限制 / **PQE —— 改写为 HQE** |

## Optimization Workflow

1. 判定输入类型:`query_id`、原始 SQL、粘贴的 `EXPLAIN ANALYZE` 文本。
2. 对 `query_id`,先查 `hologres.hg_query_log`,以记录的 `query` / `plan` 为主证据。
3. 对原始 SQL,仅在重跑可接受时跑 `EXPLAIN ANALYZE`,否则用 `EXPLAIN`。
4. 检查 **ADVICE** 找即时修复点。
5. 定位瓶颈算子(减去子节点耗时后 time 最高者)。
6. 施加针对性优化:

| 问题 | 症状 | 方案 |
|------|------|------|
| 缺统计 | `rows=1000` | `ANALYZE <table>` |
| 数据 shuffle | Redistribution | 修 `distribution_key` |
| Hash 表选错 | 大表做 hash | 更新统计 |
| 无索引 | 仅 Filter | 加 clustering / bitmap 索引 |
| PQE 执行 | ExecuteExternalSQL | 改写为 HQE 函数 |
| 数据倾斜 | max/min 方差大 | 复查分布 |

## Key GUC Parameters

会话级(单次 SQL 内,经 `hologres sql run`):

```sql
SET optimizer_force_multistage_agg = on;
SET optimizer_join_order = 'query';   -- 跟随 SQL 顺序
SET optimizer_join_order = 'greedy';  -- 贪心
SET hg_experimental_enable_cross_join_rewrite = off;
```

库级持久化(对所有新连接生效,经 `hologres guc`):

```bash
hologres guc set optimizer_force_multistage_agg on
hologres guc set optimizer_join_order query
hologres guc reset optimizer_join_order
```

完整 GUC 目录:[references/guc-parameters.md](references/guc-parameters.md)。

## Best Practices

1. 用户提供 `query_id` 时优先用慢日志记录的证据。
2. 数据大量变化后跑 `ANALYZE`。
3. 按 JOIN/GROUP BY 模式设计 `distribution_key`。
4. 范围查询列设 `clustering_key`。
5. 低基数过滤列用 bitmap 索引。
6. Join 中确保小表做 hash 表。
7. 尽量避免非等值连接。
8. PQE 函数改写为 HQE 替代。
9. 仅在重跑查询安全且预期时,才在生产用 `EXPLAIN ANALYZE`。

## 注意事项

1. `hologres.hg_query_log` 默认保留 30 天、单次最多返回 10000 条;查询必须带 `query_start` 范围或 `query_id` 条件,避免全表扫描。
2. **当 `hologres sql run` 返回空结果(无数据)时,禁止自行改参重试或变通获取;直接跳过该步骤,在输出中标注「无数据」。**
3. `EXPLAIN ANALYZE` 会真正执行查询,生产环境慎用,必要时设 `statement_timeout`。

## References

| File | Content |
|------|---------|
| [references/preconditions.md](references/preconditions.md) | 安装 / 权限 / GUC 作用域 |
| [references/slow-log-lookup.md](references/slow-log-lookup.md) | 完整 lookup SQL、结果处理矩阵、阶段症状映射 |
| [references/operators.md](references/operators.md) | 详细算子说明 |
| [references/optimization-patterns.md](references/optimization-patterns.md) | 常见优化模式 |
| [references/guc-parameters.md](references/guc-parameters.md) | 查询调优参数 |
| [阿里云慢查询日志文档](https://help.aliyun.com/zh/hologres/user-guide/query-and-analyze-slow-query-logs) | `hologres.hg_query_log` 字段与慢查询诊断 SQL |
