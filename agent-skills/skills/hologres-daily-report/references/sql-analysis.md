# Q4 SQL/任务性能诊断 — 详细查询

本文档包含日报中 Q4（SQL 和任务是否存在性能或正确性问题）诊断所需的详细查询和分析逻辑。

> **前置准备**：
>
> ```bash
> export HOLOGRES_SKILL=hologres-daily-report
> ```
>
> 以下查询中 `{report_date}` 替换为报告日期（如 `2026-04-27`）。

---

## 1. SQL 总量统计

```bash
hologres sql run --no-limit-check "SELECT count(*) as total_queries, count(*) FILTER (WHERE status = 'SUCCESS') as success_count, count(*) FILTER (WHERE status = 'FAILED') as failed_count, count(*) FILTER (WHERE duration > 10000 AND status = 'SUCCESS') as slow_count FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND usename != 'system'"
```

**输出解读**：
- `total_queries`：当日 SQL 总量
- `success_count`：成功查询数
- `failed_count`：失败查询数
- `slow_count`：慢查询数（执行时间 > 10s）

---

## 2. 慢查询 Top N

> 引用 **hologres-slow-query-analysis** skill 的分析逻辑。

### 2.1 按最大耗时排序的 Top 10

```bash
hologres sql run --no-limit-check "SELECT query_digest as sql_fingerprint, count(*) as exec_count, round(avg(duration)::numeric, 2) as avg_duration_ms, max(duration) as max_duration_ms, round(sum(duration)::numeric, 2) as total_duration_ms, round(avg(cpu_time_ms)::numeric, 2) as avg_cpu_ms, round(avg(memory_bytes / 1048576.0)::numeric, 2) as avg_memory_mb, round(avg(read_bytes / 1048576.0)::numeric, 2) as avg_read_mb, round(avg(scan_rows)::numeric, 0) as avg_scan_rows, min(query_start) as first_seen, max(query_start) as last_seen FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'SUCCESS' AND duration > 10000 AND usename != 'system' GROUP BY 1 ORDER BY max_duration_ms DESC LIMIT 10"
```

### 2.2 按总消耗 CPU 排序的 Top 10

```bash
hologres sql run --no-limit-check "SELECT query_digest as sql_fingerprint, count(*) as exec_count, round(sum(cpu_time_ms)::numeric, 2) as total_cpu_ms, round(avg(cpu_time_ms)::numeric, 2) as avg_cpu_ms, round(avg(duration)::numeric, 2) as avg_duration_ms, max(duration) as max_duration_ms FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'SUCCESS' AND usename != 'system' AND cpu_time_ms > 0 GROUP BY 1 ORDER BY total_cpu_ms DESC LIMIT 10"
```

### 2.3 按总消耗内存排序的 Top 10

```bash
hologres sql run --no-limit-check "SELECT query_digest as sql_fingerprint, count(*) as exec_count, round(max(memory_bytes / 1048576.0)::numeric, 2) as max_memory_mb, round(avg(memory_bytes / 1048576.0)::numeric, 2) as avg_memory_mb, round(avg(duration)::numeric, 2) as avg_duration_ms FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'SUCCESS' AND usename != 'system' AND memory_bytes > 0 GROUP BY 1 ORDER BY max_memory_mb DESC LIMIT 10"
```

### 2.4 获取慢查询的完整 SQL 示例

对于 Top N 中的每个 `sql_fingerprint`，获取一条完整 SQL 示例用于根因分析：

```bash
hologres sql run --no-limit-check "SELECT query_id, left(query, 500) as query_preview, duration, cpu_time_ms, memory_bytes, scan_rows, read_bytes, query_start FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND query_digest = '{sql_fingerprint}' ORDER BY duration DESC LIMIT 1"
```

**根因判断规则**（引用 **hologres-slow-query-analysis** skill）：

| 现象 | 可能根因 | 优化建议 |
|------|---------|---------|
| scan_rows 极大（> 1000 万） | 全表扫描 / 分区裁剪缺失 | 确认分区键、添加过滤条件 |
| memory_bytes 极大（> 4GB） | 中间结果集膨胀 | 拆分查询、添加 LIMIT |
| cpu_time_ms 远大于 duration | 并行度不足 | 调整 DOP 参数 |
| duration 远大于 cpu_time_ms | IO 瓶颈或锁等待 | 检查存储层、优化索引 |
| read_bytes 极大 | 缺少索引或过滤条件 | 添加 clustering_key、bitmap 索引 |

> 如需对单条 SQL 进行深入分析，可使用 **hologres-query-optimizer** skill 执行 `hologres sql explain "<query>"` 获取执行计划。

---

## 3. 失败查询分类统计

> 引用 **hologres-instance-health-analyse** skill 的错误分类逻辑。

### 3.1 按错误类型分类

```bash
hologres sql run --no-limit-check "SELECT CASE WHEN message ILIKE '%out of memory%' OR message ILIKE '%OOM%' OR message ILIKE '%cannot allocate%' THEN 'OOM' WHEN message ILIKE '%cancel%' OR message ILIKE '%timeout%' OR message ILIKE '%statement timeout%' THEN 'Timeout/Cancel' WHEN message ILIKE '%permission%' OR message ILIKE '%denied%' OR message ILIKE '%privilege%' THEN 'Permission' WHEN message ILIKE '%does not exist%' OR message ILIKE '%not found%' OR message ILIKE '%undefined%' THEN 'NotFound' WHEN message ILIKE '%syntax error%' OR message ILIKE '%parse error%' THEN 'SyntaxError' WHEN message ILIKE '%connection%' OR message ILIKE '%connect%' OR message ILIKE '%server closed%' THEN 'Connection' WHEN message ILIKE '%duplicate%' OR message ILIKE '%unique%' OR message ILIKE '%already exists%' THEN 'DuplicateKey' WHEN message ILIKE '%lock%' OR message ILIKE '%deadlock%' THEN 'Lock' WHEN message ILIKE '%type%' OR message ILIKE '%cast%' OR message ILIKE '%convert%' THEN 'TypeMismatch' WHEN message ILIKE '%partition%' THEN 'Partition' WHEN message ILIKE '%resource%' OR message ILIKE '%limit%' THEN 'ResourceLimit' ELSE 'Other' END as error_category, count(*) as cnt, min(query_start) as first_seen, max(query_start) as last_seen FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'FAILED' AND usename != 'system' GROUP BY 1 ORDER BY 2 DESC"
```

### 3.2 失败查询示例（每类取 1 条）

```bash
hologres sql run --no-limit-check "SELECT DISTINCT ON (CASE WHEN message ILIKE '%out of memory%' OR message ILIKE '%OOM%' THEN 'OOM' WHEN message ILIKE '%cancel%' OR message ILIKE '%timeout%' THEN 'Timeout' WHEN message ILIKE '%permission%' OR message ILIKE '%denied%' THEN 'Permission' ELSE 'Other' END) query_id, left(query, 300) as query_preview, left(message, 200) as error_message, duration, query_start FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'FAILED' AND usename != 'system' ORDER BY CASE WHEN message ILIKE '%out of memory%' OR message ILIKE '%OOM%' THEN 'OOM' WHEN message ILIKE '%cancel%' OR message ILIKE '%timeout%' THEN 'Timeout' WHEN message ILIKE '%permission%' OR message ILIKE '%denied%' THEN 'Permission' ELSE 'Other' END, duration DESC LIMIT 10"
```

---

## 4. 高频查询退化检测

```bash
# 对比同一查询指纹近 7 天 vs 当天的平均耗时
hologres sql run --no-limit-check "SELECT cur.sql_fingerprint, cur.avg_duration_today, hist.avg_duration_7d, round(((cur.avg_duration_today - hist.avg_duration_7d) / NULLIF(hist.avg_duration_7d, 0) * 100)::numeric, 1) as change_pct FROM (SELECT query_digest as sql_fingerprint, round(avg(duration)::numeric, 2) as avg_duration_today, count(*) as exec_count_today FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'SUCCESS' AND usename != 'system' GROUP BY 1 HAVING count(*) >= 10) cur JOIN (SELECT query_digest as sql_fingerprint, round(avg(duration)::numeric, 2) as avg_duration_7d FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz - interval '7 days' AND query_start < '{report_date} 00:00:00'::timestamptz AND status = 'SUCCESS' AND usename != 'system' GROUP BY 1 HAVING count(*) >= 10) hist ON cur.sql_fingerprint = hist.sql_fingerprint WHERE cur.avg_duration_today > hist.avg_duration_7d * 1.5 ORDER BY change_pct DESC LIMIT 10"
```

**输出解读**：
- `change_pct` > 50% 的查询被视为"退化"
- 只看执行次数 >= 10 的高频查询，排除偶发异常
- 退化查询需要进一步分析根因（数据量增长 / 统计信息过期 / 执行计划变化）

---

## 5. Dynamic Table 刷新状态

```bash
# 列出所有 Dynamic Table 及其刷新信息
hologres dt list
```

**输出解读**：
- 关注 `auto_refresh` 是否开启
- 关注刷新延迟是否超过设定的 `freshness` 值
- 刷新模式为 `incremental` 的 DT 如果延迟异常，可能需检查基表数据变化量

### 5.1 刷新延迟超标检测

```bash
# 查看特定 DT 的详细属性
hologres dt show <dt_table_name>
```

**诊断标准**：
- 刷新延迟超过 freshness 设定的 2 倍 → 异常
- 刷新失败 → 严重异常
- 刷新成功但数据新鲜度不满足业务需求 → 需调整 freshness 或刷新模式

---

## 6. 查询量时段分布

```bash
# 按小时统计查询量和失败率
hologres sql run --no-limit-check "SELECT date_trunc('hour', query_start) as hour, count(*) as total, count(*) FILTER (WHERE status = 'FAILED') as failed, count(*) FILTER (WHERE duration > 10000 AND status = 'SUCCESS') as slow, round(100.0 * count(*) FILTER (WHERE status = 'FAILED') / NULLIF(count(*), 0), 2) as fail_rate_pct FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND usename != 'system' GROUP BY 1 ORDER BY 1"
```

**输出解读**：
- 识别查询量高峰时段
- 关注高峰时段的失败率是否明显上升
- 与 Q3（计算资源）的 CPU 峰值时段对齐分析

---

## 诊断输出模板

```
### 结论
{一句话总结，如：发现 N 条需关注的查询，M 条失败查询}

### 关键事实
- SQL 总数：{total_queries}
- 慢 SQL 数（> 10s）：{slow_count}
- 失败查询数：{failed_count}
- Dynamic Table 刷新状态：{dt_status}

### Top 慢 SQL
| 排名 | 查询摘要 | 耗时 | 执行次数 | 根因诊断 | 优化建议 |
|------|----------|------|----------|----------|----------|
| 1 | {摘要} | {ms} | {N}次 | {根因} | {建议} |

### 失败查询
| 错误类型 | 数量 | 首次出现 | 最后出现 | 建议 |
|----------|------|----------|----------|------|
| {类型} | {N} | {时间} | {时间} | {建议} |

### 退化查询
| 查询摘要 | 今日均耗时 | 7日均耗时 | 变化幅度 |
|----------|-----------|----------|---------|
| {摘要} | {ms} | {ms} | +{N}% |

### 分析
{综合分析慢查询根因、失败模式、退化趋势}

### 建议
- {具体可执行建议}
```
