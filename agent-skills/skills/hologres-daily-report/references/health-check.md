# Q1 实例健康 + Q2 可用性/稳定性 — 详细诊断

本文档包含日报中 Q1（实例整体健康）和 Q2（可用性与稳定性）诊断所需的详细 SQL 和判断逻辑。

> **前置准备**：所有 SQL 查询通过 `hologres sql run --no-limit-check` 执行，实例/计算组信息通过 `hologres instance-manage get` / `hologres warehouse` 获取，云监控指标通过 `hologres metric query`（命名空间 `acs_hologres`）查询。
>
> 连接层已自动 `SET hg_computing_resource = 'serverless'`；来源标记由 `export HOLOGRES_SKILL=hologres-daily-report` 注入 `application_name`，无需在 SQL 内手写 `SET ...`。
>
> CMS 指标名称为 `{prefix}<metric>`，前缀 `{prefix}` 由实例类型决定（参见 `resource-analysis.md` 的「指标名称前缀约定」）。

---

## Q1：实例整体健康

### 1.1 实例状态与版本

```bash
# 实例详情（状态、版本、实例类型、规格、最大连接数）
hologres instance-manage get

# Warehouse 资源分配
hologres warehouse

# （可选）通过 SQL 查询服务端版本
hologres sql run "SELECT version()"
```

**输出解读**：
- `hologres instance-manage get` 返回 `data.Instance` 下的实例状态、版本、实例类型（Standard/Warehouse/Shared 等，用于确定监控指标前缀）、规格等
- `hologres warehouse` 返回各 Warehouse 的 CPU/内存/Shard 分配和状态

**版本 EOS 判断**：

| 大版本 | EOS 日期（参考） | 状态 |
|--------|-----------------|------|
| 2.x | 已过期 | 异常 — 已停止支持 |
| 3.0.x | 请查询最新 EOS 时间表 | 根据距离判断 |
| 3.1.x | 请查询最新 EOS 时间表 | 根据距离判断 |

> 请参考阿里云官方文档获取准确的 EOS 时间表。

### 1.2 连接数与分布

```bash
# 按状态统计连接数
hologres sql run --no-limit-check "SELECT state, count(*) as cnt FROM pg_stat_activity WHERE backend_type = 'client backend' GROUP BY 1 ORDER BY 2 DESC"

# 按用户统计连接分布
hologres sql run --no-limit-check "SELECT usename::text, state, count(*) as cnt FROM pg_stat_activity WHERE backend_type = 'client backend' GROUP BY 1, 2 ORDER BY 3 DESC"

# 按应用统计连接分布
hologres sql run --no-limit-check "SELECT application_name, state, count(*) as cnt FROM pg_stat_activity WHERE backend_type = 'client backend' AND application_name <> '' GROUP BY 1, 2 ORDER BY 3 DESC"

# 获取最大连接数上限
hologres sql run "SHOW max_connections"
```

**输出解读**：
- `state` 值：`active`（执行中）、`idle`（空闲）、`idle in transaction`（事务内空闲）
- 关注 `idle in transaction` 数量，过多可能导致锁竞争和资源浪费
- 计算连接使用率 = 当前连接总数 / max_connections

**诊断阈值**：
- 连接使用率 > 90%（连续 10 分钟）→ 紧张
- 连接数瞬时跌至 0 → 严重异常（可能 FE 进程异常）
- `idle in transaction` > 总连接 30% → 关注（可能有未提交事务）

### 1.3 锁等待检测

```bash
# 等待中的锁数量
hologres sql run --no-limit-check "SELECT count(*) as waiting_locks FROM pg_locks WHERE NOT granted"

# 阻塞链详情（阻塞者 → 等待者）
hologres sql run --no-limit-check "SELECT blocked_locks.pid AS blocked_pid, blocked_activity.usename AS blocked_user, blocked_activity.query AS blocked_query, now() - blocked_activity.query_start AS blocked_duration, blocking_locks.pid AS blocking_pid, blocking_activity.usename AS blocking_user, blocking_activity.query AS blocking_query, now() - blocking_activity.query_start AS blocking_duration FROM pg_locks blocked_locks JOIN pg_stat_activity blocked_activity ON blocked_activity.pid = blocked_locks.pid JOIN pg_locks blocking_locks ON blocking_locks.locktype = blocked_locks.locktype AND blocking_locks.database IS NOT DISTINCT FROM blocked_locks.database AND blocking_locks.relation IS NOT DISTINCT FROM blocked_locks.relation AND blocking_locks.page IS NOT DISTINCT FROM blocked_locks.page AND blocking_locks.tuple IS NOT DISTINCT FROM blocked_locks.tuple AND blocking_locks.virtualxid IS NOT DISTINCT FROM blocked_locks.virtualxid AND blocking_locks.transactionid IS NOT DISTINCT FROM blocked_locks.transactionid AND blocking_locks.classid IS NOT DISTINCT FROM blocked_locks.classid AND blocking_locks.objid IS NOT DISTINCT FROM blocked_locks.objid AND blocking_locks.objsubid IS NOT DISTINCT FROM blocked_locks.objsubid AND blocking_locks.pid != blocked_locks.pid JOIN pg_stat_activity blocking_activity ON blocking_activity.pid = blocking_locks.pid WHERE NOT blocked_locks.granted ORDER BY blocked_duration DESC LIMIT 10"
```

**诊断阈值**：
- 等待锁 > 10 个 → 关注
- 阻塞时长 > 30s → 异常
- 存在死锁 → 严重异常

### 1.4 长时间运行查询

```bash
# 运行超过 5 分钟的查询（query 完整输出，不截断）
hologres sql run --no-limit-check "SELECT pid, usename, application_name, state, now() - query_start as duration, query as query_full FROM pg_stat_activity WHERE state = 'active' AND now() - query_start > interval '5 minutes' AND backend_type = 'client backend' ORDER BY duration DESC LIMIT 10"
```

**诊断阈值**：
- 运行 > 30 分钟的查询 → 关注，可能需要优化或终止
- 运行 > 2 小时的查询 → 异常，建议排查

### 1.5 FE Replay 延迟

```bash
# 查询当日 FE replay 延迟时序数据（60s 粒度）
hologres metric query {prefix}fe_replay_delay --instance-id {instance_id} --start-time "{report_date}T00:00:00" --end-time "{report_date}T23:59:59" --period 60
```

> 注意：此指标仅 Hologres V2.2 及以上版本支持。如果查询无数据或失败，跳过此项，在日报中标注「数据不可用」。

**输出解读**：
- 返回每个 FE 节点的 replay 延迟时序数据（单位：毫秒），每个数据点包含 `timestamp` 和 value 字段
- 从时序数据中关注：max（峰值）及持续超过阈值的时长
- 若某个 FE 节点的延迟持续高于其他节点，可能存在该 FE 卡住的情况

**诊断阈值**：
- replay 延迟持续 > 1 分钟 → 关注，检查是否有长时间运行的 DDL 或 Query
- replay 延迟持续 > 5 分钟（连续 10 个 1 分钟周期 ≥ 300000ms）→ 异常，需结合 `pg_stat_activity` 排查并终止阻塞 Query

---

## Q2：可用性与稳定性

### 2.1 DDL 变更事件检测

```bash
# 当日所有 DDL 变更事件
hologres sql run --no-limit-check "SELECT command_tag, usename, count(*) as cnt, min(query_start) as first_at, max(query_start) as last_at FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND command_tag IN ('CREATE TABLE', 'ALTER TABLE', 'DROP TABLE', 'CREATE INDEX', 'DROP INDEX', 'ALTER DATABASE', 'CREATE SCHEMA', 'DROP SCHEMA', 'CREATE VIEW', 'DROP VIEW', 'CREATE EXTENSION', 'ALTER ROLE', 'GRANT', 'REVOKE') AND usename <> 'system' GROUP BY 1, 2 ORDER BY cnt DESC"
```

**输出解读**：
- 按 `command_tag` 分类统计当日的 DDL 操作
- 识别是否有高危操作（DROP TABLE、ALTER DATABASE 等）
- 注意操作时间是否在业务高峰期

### 2.2 异常查询模式检测（重启/Failover 痕迹）

```bash
# 检测是否存在连接断开后重连的模式（重启痕迹）
hologres sql run --no-limit-check "SELECT date_trunc('minute', query_start) as minute, count(*) as query_count FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND status = 'FAILED' AND (message ILIKE '%connection%' OR message ILIKE '%server closed%' OR message ILIKE '%terminating%') GROUP BY 1 ORDER BY 1"
```

**输出解读**：
- 如果某个时间段内集中出现大量连接相关失败，可能是重启/failover 事件
- 关注连续多分钟出现的模式，区分偶发失败和系统性事件

### 2.3 系统级事件检测

```bash
# 查询系统内部操作日志（如有权限）
hologres sql run --no-limit-check "SELECT command_tag, count(*) as cnt, min(query_start) as first_at, max(query_start) as last_at FROM hologres.hg_query_log WHERE query_start >= '{report_date} 00:00:00'::timestamptz AND query_start < '{report_date} 00:00:00'::timestamptz + interval '1 day' AND usename = 'system' AND command_tag NOT IN ('SELECT', 'SET') GROUP BY 1 ORDER BY cnt DESC"
```

**输出解读**：
- 系统用户（`usename = 'system'`）的非 SELECT 操作可能代表平台运维事件
- 关注 ALTER DATABASE、CHECKPOINT 等操作

---

## 诊断输出格式

### Q1 输出模板

```
### 结论
{一句话总结，如：实例整体健康，评分 XX/100}

### 关键事实
- 实例状态：{Running/异常状态}
- 实例版本：{版本号}，EOS 日期：{日期}（{正常/关注/异常}）
- Worker 节点 CPU：{概述}
- Locks：当前等待锁 {N} 个，最大阻塞时长 {N}s
- 连接数：活跃 {N}，总计 {N}/{max}（使用率 {N}%）
- FE replay 延迟：{概述}
- Shard 多副本同步延迟：{概述}

### 分析
{逐项分析异常原因和影响}

### 建议
- {具体可执行建议，含优先级和时间要求}
```

### Q2 输出模板

```
### 结论
{一句话总结，如：今日无实例自身故障}

### 关键事实
- 实例自身：{无重启/有 N 次重启}
- 平台运维事件：{无/有 N 项}
- 版本升级：{无/有}
- 控制台配置变更：{DDL 变更统计}

### 分析
{分析事件影响}

### 建议
- {建议}
```

---

## Health Score Rules

Baseline 100 points. Subtract per the table below; the floor is 0. Final score = `max(0, 100 - total deduction)`.

| Check | Trigger | Deduction |
|-------|---------|-----------|
| Instance status not Running | coredump / read-only | -20 |
| Version past EOS | end of support | -10 |
| Version < 3 months from EOS | nearing end of support | -5 |
| CPU continuous 1h p95 > 90% | resource pressure | -10 |
| Memory continuous 1h p95 > 90% | resource pressure | -10 |
| OOM event present | memory overflow | -15 |
| Connections continuous 10min > 90% | connection saturation | -10 |
| Query latency P99 up > 50% | performance regression | -5 |
| Query Queue backlog > 500ms | severe queueing | -5 |
| Slow SQL > 10 records | many performance issues | -5 |
| Failed queries > 10 records | many errors | -5 |
| Storage MoM growth > 10% | abnormal storage growth | -5 |
| Storage usage > 80% | capacity risk | -10 |
| Connection peak > 80% of cap | connection risk | -5 |
| Restart / coredump same day | availability event | -15 |

### Score Tiers

- 90–100: Healthy
- 70–89: Mostly healthy, with attention items
- 50–69: Needs governance
- < 50: Severe issues, act immediately
