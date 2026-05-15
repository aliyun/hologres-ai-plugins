# 报错归类分析

所有 SQL 通过 `hologres sql run` 执行，返回结构化 JSON：`{"ok": true, "data": {"rows": [...], "count": N}}`

执行前设置 SQL tracking：

```bash
export HOLOGRES_SKILL=hologres-instance-health-analyse
```

## 报错归类统计

### 按报错类型归类（过去7天）

```bash
hologres sql run --no-limit-check "SELECT regexp_replace(message, E'\\n', ' ')::char(200) AS error_message, warehouse_name, count(1) AS error_count, min(query_start) AS first_seen, max(query_start) AS last_seen FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '7 days' AND message IS NOT NULL GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 50"
```

### 按小时统计报错趋势

```bash
hologres sql run --no-limit-check "SELECT date_trunc('hour', query_start) AS hour, count(1) AS failed_count, count(DISTINCT regexp_replace(message, E'\\n', ' ')::char(100)) AS error_types FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '1 day' AND message IS NOT NULL GROUP BY 1 ORDER BY 1"
```

输出解读：
- `failed_count` 突增的小时段为故障高峰
- `error_types` 增多表示多种异常同时发生

### 按用户统计报错

```bash
hologres sql run --no-limit-check "SELECT usename, warehouse_name, count(1) AS failed_count, min(query_start) AS first_seen, max(query_start) AS last_seen FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '7 days' GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20"
```

### 查看具体报错 SQL 示例

```bash
hologres sql run "SELECT query_id, usename, warehouse_name, query_start, left(message, 200) AS error_msg, left(query, 200) AS sql_snippet FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '1 day' ORDER BY query_start DESC LIMIT 20"
```

## 常见 Hologres 报错类型与解决方案

| 报错信息（关键词） | 错误码 | 原因 | 解决方案 |
|-------------------|--------|------|----------|
| `canceling statement due to statement timeout` | 57014 | SQL 执行超时 | 1. 优化 SQL 减少扫描量<br>2. 增加 Warehouse 资源<br>3. 调整 `statement_timeout` |
| `memory exceeded` / `out of memory` | 53200 | 内存不足 | 1. 减少 SQL 并发<br>2. 优化大查询（加过滤条件）<br>3. 扩容内存 |
| `could not obtain lock` / `deadlock detected` | 55P03/40P01 | 锁等待或死锁 | 1. 检查长事务<br>2. 减少并发写入<br>3. 调整锁等待超时 |
| `relation "xxx" does not exist` | 42P01 | 表不存在 | 1. 确认 schema 和表名<br>2. 检查用户权限 |
| `permission denied` | 42501 | 权限不足 | 1. GRANT 相应权限<br>2. 使用有权限的账号 |
| `too many connections` | 53300 | 连接数超限 | 1. 检查连接池配置<br>2. 关闭空闲连接<br>3. 调整 `max_connections` |
| `syntax error` | 42601 | SQL 语法错误 | 1. 检查 SQL 拼写<br>2. 注意 Hologres 特有语法 |
| `division by zero` | 22012 | 除零错误 | 1. 添加 NULLIF 或 CASE WHEN 保护 |
| `invalid input syntax` | 22P02 | 类型转换失败 | 1. 检查数据类型匹配<br>2. 使用显式 CAST |
| `duplicate key value violates unique constraint` | 23505 | 主键冲突 | 1. 使用 INSERT ON CONFLICT<br>2. 去重后写入 |
| `query canceled by user` | 57014 | 用户主动取消 | 通常无需处理，确认是否为自动化误取消 |
| `ServerlessComputing: xxx` | - | Serverless 计算报错 | 1. 检查 SQL 是否超出 Serverless 限制<br>2. 使用独占 Warehouse |

## 诊断输出模板

```
报错分析汇总：

报错 1：{error_message}
报错次数：{error_count} 次
Warehouse：{warehouse_name}
发生时段：{first_seen} ~ {last_seen}
解决方案：
  1. ...
  2. ...

报错 2：{error_message}
...

总结：
- FAILED Query 总数：N 条（过去7天）
- 主要报错类型 Top 3：
  1. xxx（N 次）
  2. xxx（N 次）
  3. xxx（N 次）
- 建议优先处理报错次数最多的类型
```
