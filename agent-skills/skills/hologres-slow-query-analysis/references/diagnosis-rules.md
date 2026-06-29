# Diagnosis Rules — 优先优化与慢因判定

两条流程共用：
- **实例整体流程 Step 3** 用下方的*优先优化规则*选出 P0 / P1 / P2 SQL。
- **单条 SQL 流程 Step 2 / 3** 用*慢因判定规则*归类瓶颈。

---

## 优先优化规则（选 SQL 优化优先级）

当**未**提供 `query_id` 时，按以下顺序排候选：

### Tier 1 — 单次执行重
- `duration` 高
- `read_bytes` 高
- `memory_bytes` 高
- `cpu_time_ms` 高
- `physical_reads` 高

### Tier 2 — 聚合重
- `digest` 聚合后 `SUM(duration)` 高
- 执行频次高（同 `digest` 出现次数多）
- 总资源消耗高（`SUM(read_bytes / memory_bytes / cpu_time_ms)` 高）

### Tier 3 — 坏扫描比
- `read_rows / result_rows` 比值很高（扫描大、返回少）

### Tier 4 — 热点表
- 反复出现在 `table_read` 中的热点表
- 慢 SQL 集中访问的重点表

> Tier 1 候选 → P0。Tier 2 + 坏扫描比 → P1。热点表候选且无其他红旗 → P2。

---

## 慢因判定规则（cause identification）

用于填充 `慢因诊断` 与 `原因总结` 块。

| 维度 | 触发条件 | 典型现象 / 处理方向 |
|------|----------|---------------------|
| 扫描过大 | `read_rows`、`read_bytes` 很高 | 缺过滤 / 全表扫描 / 分区裁剪失效 → 增加过滤、调分区键 |
| 过滤不够好 | `read_rows / result_rows` 很高 | SARG 失效 / 过滤条件不可下推 → 改写谓词、利用索引 |
| 内存压力大 | `memory_bytes` 很高 | 大 Hash / Sort / Aggregation → 拆分、预聚合、调 distribution_key |
| IO 压力大 | `physical_reads` 很高 | 缓存命中差 / 扫描宽 → 缩列、提高复用 |
| CPU 压力大 | `cpu_time_ms` 很高 | 计算密集 / UDF 在 PQE → 改写到 HQE |
| 热点表问题 | 某些表在 `table_read` 中高频出现 | 集中访问导致单表瓶颈 → 缓存、读写分离、shard 调整 |
| SQL 写法问题 | 过滤条件不足、返回列太多、Join 顺序不合理、子查询过重 | 重写 SQL 表达 |
| 执行计划问题 | 需要重点看 `plan`、`statistics`、`query_detail`、`extended_info` | 统计信息陈旧 → `ANALYZE`；计划失真 → 调整 GUC / 改写 |
| 引擎类型问题 | `engine_type` 含 PQE 或非预期 PG | 函数 / 表达式不支持 HQE → 改写下推 |
