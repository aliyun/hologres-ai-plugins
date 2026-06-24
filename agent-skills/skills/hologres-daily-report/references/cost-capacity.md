# Q5 成本治理 + Q6 容量预测 — 详细查询

本文档包含日报中 Q5（成本是否异常，能否治理）和 Q6（未来是否存在容量风险）诊断所需的详细查询和预测方法。

> **前置准备**：SQL 查询通过 `hologres sql run --no-limit-check` 执行；云监控指标通过 `hologres metric query`（命名空间 `acs_hologres`）查询。连接层已自动 `SET hg_computing_resource = 'serverless'`，来源标记由 `export HOLOGRES_SKILL=hologres-daily-report` 注入，无需手写 `SET ...`。
>
> 以下查询中 `{report_date}` 替换为报告日期，`{prefix}` 替换为实例对应的指标前缀（含尾下划线）。

---

## Q5：成本治理

### 1. 存储使用总量

#### 1.1 通过云监控查询存储使用量

```bash
# 查询近 7 天存储使用量趋势（1h 粒度）
hologres metric query {prefix}storage_usage --instance-id {instance_id} --start-time "{7_days_ago}T00:00:00" --end-time "{report_date}T23:59:59" --period 3600
```

> 部分实例无 `{prefix}storage_usage`，可改用 `storage_usage_percent`（无前缀）或 `warehouse_hot_storage_used`（热存储量，单位 KB）。用 `hologres metric list --search storage` 确认可用指标名。

**输出解读**：
- 获取每天的存储使用量快照
- 计算当日 vs 昨日的环比变化
- 计算近 7 天的日均增长量

#### 1.2 通过 hg_table_info 查询冷热存构成

> 存储总量已通过 1.1 的云监控获取，本节补充冷热存拆分信息（CMS 不提供冷热存分离数据）。

```bash
# 当前冷热存汇总
hologres sql run --no-limit-check "SELECT pg_size_pretty(sum(hot_storage_size)) as hot_size, pg_size_pretty(sum(cold_storage_size)) as cold_size, sum(hot_storage_size) as hot_bytes, sum(cold_storage_size) as cold_bytes FROM hologres.hg_table_info WHERE db_name = current_database() AND collect_time = (SELECT max(collect_time) FROM hologres.hg_table_info WHERE db_name = current_database())"
```

**输出解读**：
- `hot_size` / `cold_size`：热存和冷存各自占用空间
- 结合 1.1 的 CMS 存储总量，可计算冷热存占比
- 注意：`hg_table_info` 为 T+1 产出，反映前一天的存储快照

### 2. 表存储排名

> 使用 `hologres.hg_table_info`（V1.3+，按天采集 T+1）获取表存储数据，比 `pg_total_relation_size` 更准确（含冷热存分离，分区父表可正确返回行数）。

```bash
# Top 20 大表（含 schema、冷热存明细）
hologres sql run --no-limit-check "SELECT schema_name, table_name, type, pg_size_pretty(hot_storage_size + cold_storage_size) as total_size, hot_storage_size + cold_storage_size as size_bytes, pg_size_pretty(hot_storage_size) as hot_size, pg_size_pretty(cold_storage_size) as cold_size, row_count FROM hologres.hg_table_info WHERE db_name = current_database() AND schema_name NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hologres_statistic') AND type IN ('TABLE', 'PARTITION TABLE') AND (hot_storage_size + cold_storage_size) > 0 AND collect_time = (SELECT max(collect_time) FROM hologres.hg_table_info WHERE db_name = current_database()) ORDER BY size_bytes DESC LIMIT 20"
```

**输出解读**：
- `size_bytes`：表总存储量（热存 + 冷存）
- `hot_size` / `cold_size`：热存和冷存各自占用空间
- 识别占用存储最大的表，关注是否有异常大表（如临时表、日志表不清理）
- 注意：`hg_table_info` 数据为 T+1 产出，反映的是前一天的存储快照

### 3. 空表检测

```bash
# 有表结构但无数据的表（行数 = 0 且无存储）
hologres sql run --no-limit-check "SELECT schema_name, table_name, type, owner_name, create_time FROM hologres.hg_table_info WHERE db_name = current_database() AND schema_name NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hologres_statistic') AND type IN ('TABLE', 'PARTITION TABLE') AND row_count = 0 AND (hot_storage_size + cold_storage_size) = 0 AND collect_time = (SELECT max(collect_time) FROM hologres.hg_table_info WHERE db_name = current_database()) ORDER BY create_time ASC LIMIT 20"
```

### 4. 冷数据识别

通过 `hg_table_info` 的 `last_access_time` 字段直接判断表的最后访问时间，比 `hg_query_log` ILIKE 模糊匹配更准确：

```bash
# 30 天未访问且大小 > 1GB 的表
hologres sql run --no-limit-check "SELECT schema_name, table_name, pg_size_pretty(hot_storage_size + cold_storage_size) as size, hot_storage_size + cold_storage_size as size_bytes, row_count, last_access_time, owner_name FROM hologres.hg_table_info WHERE db_name = current_database() AND schema_name NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hologres_statistic') AND type IN ('TABLE', 'PARTITION TABLE') AND (hot_storage_size + cold_storage_size) > 1073741824 AND (last_access_time < now() - interval '30 days' OR last_access_time IS NULL) AND collect_time = (SELECT max(collect_time) FROM hologres.hg_table_info WHERE db_name = current_database()) ORDER BY size_bytes DESC LIMIT 20"
```

**输出解读**：
- 列出 30 天未被访问且大小 > 1GB 的表
- 这些表是潜在的冷数据，可评估归档或删除
- `last_access_time` 为系统精确记录的表访问时间，无 ILIKE 子串误判问题
- `last_access_time IS NULL` 的表表示自 V1.3 以来从未被访问过

### 5. 临时表/备份表检测

```bash
# 疑似临时表或备份表（命名模式匹配，通过 hg_table_info 获取存储和 Owner）
hologres sql run --no-limit-check "SELECT schema_name, table_name, pg_size_pretty(hot_storage_size + cold_storage_size) as size, hot_storage_size + cold_storage_size as size_bytes, row_count, owner_name, last_access_time FROM hologres.hg_table_info WHERE db_name = current_database() AND schema_name NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hologres_statistic') AND type IN ('TABLE', 'PARTITION TABLE') AND (table_name ILIKE 'tmp_%' OR table_name ILIKE '%_tmp' OR table_name ILIKE '%_bak' OR table_name ILIKE '%_backup%' OR table_name ILIKE '%_old' OR table_name ILIKE '%_copy%' OR table_name ILIKE 'test_%') AND (hot_storage_size + cold_storage_size) > 104857600 AND collect_time = (SELECT max(collect_time) FROM hologres.hg_table_info WHERE db_name = current_database()) ORDER BY size_bytes DESC LIMIT 20"
```

**输出解读**：
- 临时表/备份表（> 100MB）是最直接的治理目标
- 确认后可直接删除释放空间

### 6. 存储增长来源分析

如果存储环比增幅 > 10%，进一步分析增长来源：

```bash
# 需与前次巡检的表大小数据对比
# 如果没有历史数据，可通过 hg_query_log 分析写入量最大的表
hologres sql run --no-limit-check "SELECT split_part(query, ' ', 3) as target_table, count(*) as write_count FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND command_tag IN ('INSERT', 'COPY') AND usename <> 'system' GROUP BY 1 ORDER BY 2 DESC LIMIT 10"
```

---

## Q5 诊断输出模板

```
### 结论
{一句话总结，如：存储使用率 66%，环比增加 7%，存在治理空间}

### 关键事实
| 维度 | 当前值 | 昨日 | 环比 | 状态 |
|------|--------|------|------|------|
| 存储使用率 | XX%（XXTB / XXTB quota） | XX% | +X% | {正常/关注/异常} |
| 冷数据 | XXGB | — | — | {有/无治理空间} |

- 存储增长来源：{分析结果}
- 冷数据（30 天未访问）：{表名列表}
- 临时表残留：{有 N 个/无}

### 分析
{分析存储增长原因、冷数据成因、治理收益}

### 建议
- {治理建议，含预估收益}
```

---

## Q6：容量预测

### 1. 存储容量预测

基于近 7 天的存储使用数据（来自 Q5 的云监控查询），计算日均增长量并线性外推：

**预测算法**：
1. 获取近 7 天每日存储量快照
2. 日均增长 = (最新存储 - 7 天前存储) / 7
3. 预计达 80% quota 天数 = (quota × 0.8 - 当前存储) / 日均增长

### 2. 连接容量预测

基于 Q3 的连接数数据：

```bash
# 获取最大连接数上限
hologres sql run "SHOW max_connections"
```

**预测算法**：
1. 获取当日连接峰值（来自 Q3 metric 数据）
2. 计算连接使用率 = 峰值 / max_connections
3. 使用率 > 80% → 高风险
4. 使用率 60-80% → 需关注

### 3. CPU 容量预测

基于 Q3 的 CPU 数据：

**预测算法**：
1. 获取当日 CPU 峰值和均值
2. 峰值持续接近 90% → 需升配
3. 结合 QPS 趋势判断：QPS 增长 + CPU 接近上限 = 需扩容

### 4. 表数量预测

```bash
# 当前表数量（通过 hg_table_info 统计）
hologres sql run --no-limit-check "SELECT count(*) as table_count FROM hologres.hg_table_info WHERE db_name = current_database() AND schema_name NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hologres_statistic') AND type IN ('TABLE', 'PARTITION TABLE', 'LOGICAL PARTITION TABLE') AND collect_time = (SELECT max(collect_time) FROM hologres.hg_table_info WHERE db_name = current_database())"

# 近 7 天新增表数量（通过 DDL 日志推算）
hologres sql run --no-limit-check "SELECT count(*) as new_tables FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz - interval '7 days' AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND command_tag = 'CREATE TABLE' AND usename <> 'system'"
```

**表数量上限参考**：

| 实例规格 | 建议表数量上限 |
|---------|---------------|
| 32C128G | 50,000 |
| 64C256G | 100,000 |
| 128C512G | 200,000 |

> 注意：实际上限受 Shard 数、元数据大小等因素影响，以上为参考值。

### 5. 风险等级判定

| 资源 | 高风险 | 中风险 | 低风险 |
|------|--------|--------|--------|
| 存储 | 预计 30 天内达 80% | 预计 30-90 天达 80% | > 90 天 |
| 连接 | 使用率 > 80% | 使用率 60-80% | < 60% |
| CPU | 峰值连续 > 90% | 峰值 70-90% | < 70% |
| 表数量 | > 80% 规格上限 | 50-80% 规格上限 | < 50% |

---

## Q6 诊断输出模板

```
### 结论
{一句话总结，如：存储存在中期容量风险，连接数已接近上限}

### 关键事实
| 资源 | 当前使用率 | 预计达 80% 时间 | 风险等级 |
|------|------------|-----------------|----------|
| 存储 | XX%（XXTB / XXTB） | ~N 天 | {高/中/低} |
| 连接 | XX%（N / N） | {已接近/充足} | {高/中/低} |
| CPU | 峰值 XX% | {视业务增长} | {高/中/低} |
| 表数量 | N / N | > N 天 | {高/中/低} |

- 存储近 7 天日均增长 XXGB

### 分析
{分析各维度容量风险的原因和影响}

### 建议
- {容量规划建议，含优先级和时间节点}
```
