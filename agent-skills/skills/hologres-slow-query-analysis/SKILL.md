---
name: hologres-slow-query-analysis
description: |
  Hologres slow query log analysis and diagnosis skill. Use for analyzing slow queries, 
  failed queries, query performance diagnosis, and log management in Alibaba Cloud Hologres.
  Triggers: "hologres slow query", "hg_query_log", "query diagnosis", "慢Query分析", "Hologres性能诊断"
---

## Prerequisites

This skill requires **hologres-cli** to be installed first:

```bash
pip install hologres-cli
export HOLOGRES_SKILL=hologres-slow-query-analysis
```

All SQL execution and GUC parameter operations depend on `hologres-cli` commands (`hologres sql run`, `hologres guc set`).

# Hologres Slow Query Analysis

Diagnose and analyze slow/failed queries in Alibaba Cloud Hologres using the `hologres.hg_query_log` system table.

## Version Requirements

| Hologres Version | Feature |
|-----------------|---------|
| V0.10+ | Basic slow query log |
| V2.2+ | SQL fingerprint (digest) |
| V2.2.7+ | Default threshold 100ms |
| V3.0.2+ | Aggregated records for <100ms queries |

## Quick Start

### 1. Check Permissions

```sql
-- Superuser: view all DB logs
ALTER USER "cloud_account_id" SUPERUSER;

-- Or join pg_read_all_stats group
GRANT pg_read_all_stats TO "cloud_account_id";

-- For current DB only (SPM model)
CALL spm_grant('<db_name>_admin', 'cloud_account_id');
```

### 2. Basic Query Count

```sql
SELECT count(*) FROM hologres.hg_query_log;
```

### 3. Recent Slow Queries (10 min)

```sql
SELECT status AS "Status",
       duration AS "Duration(ms)",
       query_start AS "Start Time",
       (read_bytes/1048576)::text || ' MB' AS "Read",
       (memory_bytes/1048576)::text || ' MB' AS "Memory",
       (cpu_time_ms/1000)::text || ' s' AS "CPU",
       query_id AS "QueryID",
       query::char(50) AS "Query"
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '10 min'
ORDER BY duration DESC
LIMIT 100;
```

## Core Diagnostic Workflows

### Workflow 1: Find Resource-Heavy Queries

Use when CPU/memory usage is high.

```sql
-- Top 10 CPU-consuming queries (past day)
SELECT digest, avg(cpu_time_ms), sum(cpu_time_ms)
FROM hologres.hg_query_log
WHERE query_start >= CURRENT_DATE - INTERVAL '1 day'
  AND digest IS NOT NULL AND usename != 'system'
GROUP BY 1 ORDER BY 3 DESC LIMIT 10;
```

### Workflow 2: Find Failed Queries

```sql
SELECT status, message::char(100), duration, query_start, query_id, query::char(80)
FROM hologres.hg_query_log
WHERE query_start BETWEEN '2024-01-01 00:00:00'::timestamptz 
      AND '2024-01-01 01:00:00'::timestamptz
  AND status = 'FAILED'
ORDER BY query_start ASC LIMIT 100;
```

### Workflow 2.1: Failed Query Error Code Classification

Extract unified error codes from the `message` field and group by error type for pattern analysis:

```sql
-- Extract error code from message and classify by error type
SELECT ltrim(split_part(message, ': ', 2), ' ') AS error_code,
       count(*) AS error_count,
       min(query_start) AS first_seen,
       max(query_start) AS last_seen
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '3 h'
  AND status = 'FAILED'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;
```

**Error code extraction formula:** `ltrim(split_part(message, ': ', 2), ' ')` — splits the message on `': '` and trims leading spaces to get the SQLSTATE code (e.g., `'XX000'`, `'53200'`, `'57014'`).

**Common Error Code → Type Mapping:**

| SQLSTATE Code | Error Type | Description | Typical Root Cause |
| :--- | :--- | :--- | :--- |
| `XX000` | ERRCODE_INTERNAL_ERROR | Internal error | Engine bug or unexpected state |
| `XX001` | ERRCODE_DATA_CORRUPTED | Data corrupted | Storage corruption |
| `53200` | ERRCODE_OUT_OF_MEMORY | Out of memory | Query needs too much memory, reduce concurrency or optimize SQL |
| `53300` | ERRCODE_TOO_MANY_CONNECTIONS | Too many connections | Connection pool exhausted |
| `53000` | ERRCODE_INSUFFICIENT_RESOURCES | Insufficient resources | General resource exhaustion |
| `57014` | ERRCODE_QUERY_CANCELED | Query canceled | Timeout or manual cancel |
| `57P01` | ERRCODE_ADMIN_SHUTDOWN | Admin shutdown | Instance restart or maintenance |
| `57000` | ERRCODE_OPERATOR_INTERVENTION | Operator intervention | Manual intervention |
| `40P01` | ERRCODE_T_R_DEADLOCK_DETECTED | Deadlock detected | Concurrent transactions conflict |
| `40001` | ERRCODE_T_R_SERIALIZATION_FAILURE | Serialization failure | Transaction conflict |
| `23505` | ERRCODE_UNIQUE_VIOLATION | Unique violation | Duplicate key on insert/update |
| `23502` | ERRCODE_NOT_NULL_VIOLATION | Not null violation | NULL inserted into NOT NULL column |
| `42P01` | ERRCODE_UNDEFINED_TABLE | Undefined table | Table does not exist |
| `42703` | ERRCODE_UNDEFINED_COLUMN | Undefined column | Column does not exist |
| `42601` | ERRCODE_SYNTAX_ERROR | Syntax error | SQL syntax problem |
| `42501` | ERRCODE_INSUFFICIENT_PRIVILEGE | Insufficient privilege | Permission denied |
| `42883` | ERRCODE_UNDEFINED_FUNCTION | Undefined function | Function does not exist |
| `55P03` | ERRCODE_LOCK_NOT_AVAILABLE | Lock not available | Lock timeout |
| `08006` | ERRCODE_CONNECTION_FAILURE | Connection failure | Network or backend disconnect |
| `08P01` | ERRCODE_PROTOCOL_VIOLATION | Protocol violation | Client/server protocol mismatch |
| `22012` | ERRCODE_DIVISION_BY_ZERO | Division by zero | Arithmetic error |
| `22001` | ERRCODE_STRING_DATA_RIGHT_TRUNCATION | String data right truncation | Value too long for column |
| `HG000` | ERRCODE_HG_NEED_RETRY | Hologres need retry | Transient Hologres error, retry |
| `HG001` | ERRCODE_HG_PLPGSQL_NEED_RETRY | Hologres PL/pgSQL need retry | Transient PL/pgSQL error, retry |

For a complete mapping, see [error-codes.md](references/error-codes.md).

### Workflow 3: Query Phase Analysis

Identify bottleneck phase (optimization/startup/execution).

```sql
SELECT status, duration AS "Total(ms)",
       optimization_cost AS "Optimize(ms)",
       start_query_cost AS "Startup(ms)",
       get_next_cost AS "Execute(ms)",
       duration - optimization_cost - start_query_cost - get_next_cost AS "Other(ms)",
       query_id, query::char(50)
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '10 min'
ORDER BY duration DESC LIMIT 100;
```

### Workflow 4: Compare with Yesterday

```sql
SELECT query_date, count(1), sum(read_bytes), sum(cpu_time_ms)
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '3 h'
GROUP BY query_date
UNION ALL
SELECT query_date, count(1), sum(read_bytes), sum(cpu_time_ms)
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '1d 3h' AND query_start <= now() - interval '1d'
GROUP BY query_date;
```

## Key Fields Reference

| Field | Description |
|-------|-------------|
| `query_id` | Unique query identifier |
| `digest` | SQL fingerprint (MD5 hash) |
| `duration` | Total query time (ms) |
| `cpu_time_ms` | CPU time consumed |
| `memory_bytes` | Peak memory usage |
| `read_bytes` | Data read volume |
| `engine_type` | Query engine (HQE/PQE/SDK/PG) |
| `optimization_cost` | Plan generation time |
| `start_query_cost` | Query startup time |
| `get_next_cost` | Execution time |

## Configuration

```sql
-- Set slow query threshold (DB level, superuser only)
ALTER DATABASE dbname SET log_min_duration_statement = '250ms';

-- Session level
SET log_min_duration_statement = '250ms';

-- Set log retention (V3.0.27+, 3-30 days)
ALTER DATABASE dbname SET hg_query_log_retention_time_sec = 2592000;
```

Or use the CLI for database-level settings:
```bash
hologres guc set log_min_duration_statement '250ms'
hologres guc set hg_query_log_retention_time_sec 2592000
```

## References

| Document | Content |
|----------|--------|
| [diagnostic-queries.md](references/diagnostic-queries.md) | Complete diagnostic SQL collection |
| [log-export.md](references/log-export.md) | Export logs to internal/external tables |
| [configuration.md](references/configuration.md) | Configuration parameters |
| [error-codes.md](references/error-codes.md) | SQLSTATE error code → type mapping (PostgreSQL + Hologres) |

## Output Format

When performing slow query analysis, generate a structured report following one of the two templates below depending on the scenario.

### Scenario A: Instance-Level Report (No specific Query ID)

When the user does NOT specify a Query ID, perform an overall instance-level analysis and output the report in the following format:

---

# Hologres 实例级整体慢 Query 分析报告

**实例 ID**: `{{instance_id}}`  
**生成时间**: `{{current_time}}`  
**数据范围**: `{{start_date}}` ~ `{{end_date}}`

---

## 1. 核心结论 (Executive Summary)

> **健康状态**: {{health_status}} (正常 / 警告 / 严重)
>
> **关键发现**:
> {{key_findings_text}}
> *例如：过去 3 小时内检测到 50 条慢查询，其中 3 条失败。主要瓶颈集中在物理读过高，建议检查热点表索引。*

---

## 2. 总体概览与用户分布

### 2.1 慢 Query 统计

| 指标 | 数值 | 说明 |
| :--- | :--- | :--- |
| **慢 Query 总数** | `{{total_count}}` | 超过阈值({{threshold}}ms)的查询数量 |
| **失败 Query 数** | `{{failed_count}}` | 状态为 FAILED 的查询数量 |
| **涉及用户数** | `{{unique_user_count}}` | 产生慢查询的不同用户名数量 |

### 2.2 用户慢 Query 排行

| 排名 | 用户名 (User) | 慢 Query 个数 | 占比 |
| :--- | :--- | :--- | :--- |
| 1 | `{{user_1}}` | `{{count_1}}` | `{{pct_1}}%` |
| 2 | `{{user_2}}` | `{{count_2}}` | `{{pct_2}}%` |
| 3 | `{{user_3}}` | `{{count_3}}` | `{{pct_3}}%` |

---

## 3. 流量趋势与同比分析

### 3.1 近 3 小时负载趋势

| 时间段 | Query 访问量 | 数据读取总量 (MB) | CPU 总耗时 (s) |
| :--- | :--- | :--- | :--- |
| `{{query_start_1}}` | `{{count_h1}}` | `{{read_h1}}` | `{{cpu_h1}}` |
| `{{query_start_2}}` | `{{count_h2}}` | `{{read_h2}}` | `{{cpu_h2}}` |
| `{{query_start_3}}` | `{{count_h3}}` | `{{read_h3}}` | `{{cpu_h3}}` |

### 3.2 昨日同比对比

| 对比项 | 今日同期 (Past 3h) | 昨日同期 (Yesterday) | 变化幅度 |
| :--- | :--- | :--- | :--- |
| **总访问量** | `{{today_total_count}}` | `{{yesterday_total_count}}` | `{{count_change_pct}}%` |
| **总读取量** | `{{today_total_read}}` MB | `{{yesterday_total_read}}` MB | `{{read_change_pct}}%` |
| **总 CPU 耗时** | `{{today_total_cpu_s}}` s | `{{yesterday_total_cpu_s}}` s | `{{cpu_change_pct}}%` |

> **趋势解读**: {{trend_analysis}}

---

## 4. 异常检测：失败与阶段耗时

### 4.1 最新失败 Query

| 开始时间 | Query ID | Error Code | 错误类型 | 报错信息摘要 | 耗时 (ms) | SQL 预览 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `{{fail_time_1}}` | `{{fail_id_1}}` | `{{fail_code_1}}` | `{{fail_type_1}}` | `{{fail_msg_1}}` | `{{fail_dur_1}}` | `{{fail_sql_1}}` |
| `{{fail_time_2}}` | `{{fail_id_2}}` | `{{fail_code_2}}` | `{{fail_type_2}}` | `{{fail_msg_2}}` | `{{fail_dur_2}}` | `{{fail_sql_2}}` |

> **Error Code 提取方式**: `ltrim(split_part(message, ': ', 2), ' ')` 获取 SQLSTATE 错误码，然后根据错误码映射表确定错误类型。

### 4.1.1 错误码分布统计

| Error Code | 错误类型 | 出现次数 | 占比 | 建议处理方式 |
| :--- | :--- | :--- | :--- | :--- |
| `{{err_code_1}}` | `{{err_type_1}}` | `{{err_count_1}}` | `{{err_pct_1}}%` | {{err_action_1}} |
| `{{err_code_2}}` | `{{err_type_2}}` | `{{err_count_2}}` | `{{err_pct_2}}%` | {{err_action_2}} |
| `{{err_code_3}}` | `{{err_type_3}}` | `{{err_count_3}}` | `{{err_pct_3}}%` | {{err_action_3}} |

### 4.2 各阶段耗时异常

| 异常类型 | Query ID | 总耗时 (ms) | 优化耗时 (ms) | 启动耗时 (ms) | 执行耗时 (ms) | 其他耗时 (ms) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **启动耗时最高** | `{{start_top_id}}` | `{{start_total}}` | `{{start_opt}}` | **`{{start_val}}`** | `{{start_exec}}` | `{{start_other}}` |
| **优化耗时最高** | `{{opt_top_id}}` | `{{opt_total}}` | **`{{opt_val}}`** | `{{opt_start}}` | `{{opt_exec}}` | `{{opt_other}}` |
| **执行耗时最高** | `{{exec_top_id}}` | `{{exec_total}}` | `{{exec_opt}}` | `{{exec_start}}` | **`{{exec_val}}`** | `{{exec_other}}` |

---

## 5. 高消耗 Query 排行榜 Top 3 深度透视

### No.1 最高消耗 Query

- **Query ID**: `{{top1_id}}`
- **开始时间**: `{{top1_start_time}}`
- **SQL 预览**: `{{top1_sql_preview}}`

**关键运行指标:**

| 指标 | 数值 | 说明 |
| :--- | :--- | :--- |
| **状态** | `{{top1_status}}` | SUCCESS / FAILED |
| **总耗时** | `{{top1_duration}}` ms | Query 执行总时长 |
| **CPU 时间** | `{{top1_cpu_time}}` s | 所有计算节点 CPU 累加时间 |
| **数据读取量** | `{{top1_read_bytes}}` MB | 从存储层读取的数据量 |
| **物理读次数** | `{{top1_physical_reads}}` | 磁盘 IO 次数，高值表示缓存未命中 |
| **内存峰值** | `{{top1_memory}}` MB | 查询过程中使用的最大内存 |
| **Shuffle 数据量** | `{{top1_shuffle}}` MB | 节点间网络传输数据量，高值可能暗示倾斜 |

> **初步诊断**: {{top1_diagnosis}}

---

### No.2 次高消耗 Query

- **Query ID**: `{{top2_id}}`
- **开始时间**: `{{top2_start_time}}`
- **SQL 预览**: `{{top2_sql_preview}}`

**关键运行指标:**

| 指标 | 数值 | 说明 |
| :--- | :--- | :--- |
| **状态** | `{{top2_status}}` | SUCCESS / FAILED |
| **总耗时** | `{{top2_duration}}` ms | Query 执行总时长 |
| **CPU 时间** | `{{top2_cpu_time}}` s | 所有计算节点 CPU 累加时间 |
| **数据读取量** | `{{top2_read_bytes}}` MB | 从存储层读取的数据量 |
| **物理读次数** | `{{top2_physical_reads}}` | 磁盘 IO 次数，高值表示缓存未命中 |
| **内存峰值** | `{{top2_memory}}` MB | 查询过程中使用的最大内存 |
| **Shuffle 数据量** | `{{top2_shuffle}}` MB | 节点间网络传输数据量，高值可能暗示倾斜 |

> **初步诊断**: {{top2_diagnosis}}

---

### No.3 次高消耗 Query

- **Query ID**: `{{top3_id}}`
- **开始时间**: `{{top3_start_time}}`
- **SQL 预览**: `{{top3_sql_preview}}`

**关键运行指标:**

| 指标 | 数值 | 说明 |
| :--- | :--- | :--- |
| **状态** | `{{top3_status}}` | SUCCESS / FAILED |
| **总耗时** | `{{top3_duration}}` ms | Query 执行总时长 |
| **CPU 时间** | `{{top3_cpu_time}}` s | 所有计算节点 CPU 累加时间 |
| **数据读取量** | `{{top3_read_bytes}}` MB | 从存储层读取的数据量 |
| **物理读次数** | `{{top3_physical_reads}}` | 磁盘 IO 次数，高值表示缓存未命中 |
| **内存峰值** | `{{top3_memory}}` MB | 查询过程中使用的最大内存 |
| **Shuffle 数据量** | `{{top3_shuffle}}` MB | 节点间网络传输数据量，高值可能暗示倾斜 |

> **初步诊断**: {{top3_diagnosis}}

---

## 6. 系统性优化建议

基于上述分析，建议采取以下措施：

1. **索引优化**: {{global_index_tip}}
2. **资源隔离**: {{global_resource_tip}}
3. **SQL 规范**: {{global_sql_tip}}

---

### Scenario B: Single Query Report (Specific Query ID provided)

When the user specifies a Query ID, perform a single-query deep analysis and output in the following format:

---

# 单条 SQL 慢 Query 分析报告

**实例版本**: {{instance_id}}  
**生成时间**: {{current_time}}  
**目标 Query ID**: {{query_id}}

---

## 1. 核心结论 (Executive Summary)

- **诊断结果**: {{diagnosis_result}} (例如：性能良好 / 存在严重瓶颈 / 执行失败)
- **根因定位**: 该 Query 总耗时 **{{duration}} ms**。主要瓶颈位于 **{{bottleneck_stage}}** 阶段 (占比 **{{bottleneck_pct}}%**)。
- **具体原因**: {{root_cause_text}}

---

## 2. 基础执行信息

| 字段 | 值 | 字段 | 值 |
| :--- | :--- | :--- | :--- |
| **状态 (Status)** | {{status}} | **执行用户** | {{usename}} |
| **数据库** | {{datname}} | **应用来源** | {{application_name}} |
| **客户端 IP** | {{client_addr}} | **开始时间** | {{query_start}} |
| **SQL 类型** | {{command_tag}} | **执行引擎** | {{engine_type}} |
| **读取表** | {{table_read}} | **写入表** | {{table_write}} |
| **报错信息** | {{message}} | **Session ID** | {{session_id}} |
| **Query Date** | {{query_date}} | **PID** | {{pid}} |
| **Command ID** | {{command_id}} | **Session Start** | {{session_start}} |

**SQL 全文:**
```sql
{{full_query}}
```

---

## 3. 耗时拆解与瓶颈分析

| 阶段 | 耗时 (ms) | 占比 | 诊断含义 |
| :--- | :--- | :--- | :--- |
| **优化耗时 (Optimization)** | {{opt_cost}} | {{opt_pct}}% | SQL 解析与计划生成。若 >100ms，检查 SQL 复杂度。 |
| **启动耗时 (Start Query)** | {{start_cost}} | {{start_pct}}% | **关键**。若高，通常因 **等待锁** 或 **资源排队**。 |
| **执行耗时 (Get Next)** | {{exec_cost}} | {{exec_pct}}% | **关键**。若高，通常因 **计算量大** 或 **IO 扫描多**。 |
| **其他耗时 (Extended)** | {{other_cost}} | {{other_pct}}% | Build DAG, Prepare Reqs 等。访问外部表时此项可能高。 |
| **总耗时 (Duration)** | **{{duration}}** | **100%** | - |

---

## 4. 资源消耗详细评估

| 资源项 | 数值 | 人类可读 | 评估与建议 |
| :--- | :--- | :--- | :--- |
| **CPU 时间** | {{cpu_time_ms}} ms | {{cpu_time_s}} s | {{cpu_analysis}} |
| **内存峰值** | {{memory_bytes}} B | {{memory_mb}} MB | {{mem_analysis}} |
| **Shuffle 数据量** | {{shuffle_bytes}} B | {{shuffle_mb}} MB | {{shuffle_analysis}} |
| **物理读次数** | {{physical_reads}} | - | {{io_analysis}} |
| **逻辑读行数** | {{read_rows}} | - | {{read_row_analysis}} |
| **返回行数** | {{result_rows}} | - | - |
| **返回字节数** | {{result_bytes}} | {{result_mb}} MB | - |
| **影响行数** | {{affected_rows}} | - | (DML操作有效) |
| **影响字节数** | {{affected_bytes}} | {{affected_mb}} MB | (DML操作有效) |

---

## 5. 执行计划与引擎分析

- **使用引擎**: {{engine_type}}
    - **HQE**: Hologres 原生引擎，效率最高。
    - **PQE**: PostgreSQL 引擎。**警告**: 若出现 PQE，说明存在 HQE 不支持的算子，建议改写 SQL 以利用 HQE 加速。
    - **FixedQE**: 点查/点写加速引擎。

- **执行计划摘要**:
```text
{{plan_snippet}}
```

---

## 6. 针对性优化建议

1. **SQL 改写**:
    - {{sql_tip_1}}
    - {{sql_tip_2}}
2. **索引/表结构**:
    - {{index_tip}}
3. **配置/架构**:
    - {{config_tip}}

---

## 7. 附录：原始日志数据

```json
{
  "query_id": "{{query_id}}",
  "status": "{{status}}",
  "duration_ms": {{duration}},
  "optimization_cost_ms": {{opt_cost}},
  "start_query_cost_ms": {{start_cost}},
  "get_next_cost_ms": {{exec_cost}},
  "cpu_time_ms": {{cpu_time_ms}},
  "memory_bytes": {{memory_bytes}},
  "shuffle_bytes": {{shuffle_bytes}},
  "physical_reads": {{physical_reads}},
  "read_rows": {{read_rows}},
  "result_rows": {{result_rows}},
  "engine_type": "{{engine_type}}"
}
```

---

## Best Practices

1. Always filter by `query_start` for better performance
2. Use `digest` to group similar queries for pattern analysis
3. Check `engine_type` - PQE queries may need optimization
4. For `start_query_cost` high: check locks or resource contention
5. For `get_next_cost` high: optimize SQL or add indexes
6. Regular cleanup: set appropriate retention period
