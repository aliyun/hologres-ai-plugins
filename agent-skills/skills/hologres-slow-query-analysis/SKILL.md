---
name: hologres-slow-query-analysis
description: |
  Hologres slow query log analysis and diagnosis skill. Use for analyzing slow queries,
  failed queries, query performance diagnosis, and log management in Alibaba Cloud Hologres.
  Triggers: "hologres slow query", "hg_query_log", "query diagnosis", "慢Query分析", "Hologres性能诊断"
---

# Hologres 慢 SQL 分析 Skill

## 前提条件

使用本 Skill 前，需要先安装 hologres-cli：

```bash
pip install hologres-cli
export HOLOGRES_SKILL=hologres-slow-query-analysis
```

所有 SQL 执行和 GUC 参数操作均依赖 hologres-cli 命令（`hologres sql run`、`hologres guc set`）。

## Hologres 版本要求

| Hologres 版本 | 特性说明 |
| :--- | :--- |
| V0.10+ | 基础慢查询日志 |
| V2.2+ | SQL 指纹（digest） |
| V2.2.7+ | 默认阈值 100ms |
| V3.0.2+ | <100ms 查询的聚合记录 |

## 权限要求

查询 `hologres.hg_query_log` 需要具备相应的读取权限，以下三种方式任选其一：

```sql
-- 方式一：授予 Superuser 权限（可查看所有数据库的日志）
ALTER USER "<your_cloud_account_id>" SUPERUSER;

-- 方式二：加入 pg_read_all_stats 用户组（推荐，权限更精细）
GRANT pg_read_all_stats TO "<your_cloud_account_id>";

-- 方式三：仅对当前数据库生效（SPM 权限模型）
CALL spm_grant('<db_name>_admin', '<your_cloud_account_id>');
```

## 目标

基于 `hologres.hg_query_log` 视图，对 Hologres 实例中的慢 SQL 进行分析，支持两种模式：
1. **实例整体慢 SQL 分析**
    - 当用户**未提供** `query_id` 时，默认分析指定时间范围内实例整体慢 SQL 情况
2. **单条 SQL 分析**
    - 当用户**提供了** `query_id` 时，默认分析该 SQL 的执行情况、资源消耗、执行计划和优化建议

本 Skill 的目标不仅是找出慢 SQL，还要回答：
- 这段时间内 SQL 总体情况如何
- 哪些 SQL 最值得优先优化
- 为什么慢
- 慢在什么地方
- 应该怎么优化
- 每个诊断项的结果是什么
- 错误 SQL 的报错和原因是什么

---

## 适用场景

当用户需要以下能力时，使用本 Skill：
- 分析某个时间段内的慢 SQL
- 找出实例里最慢、最重、最值得优化的 SQL
- 分析指定 `query_id` 的 SQL 慢因
- 从资源消耗、执行计划、表维度等角度定位问题
- 输出可执行的优化建议
- 对每个诊断项给出明确总结
- 分析错误 SQL 的报错和原因

---

## 输入参数

### 必填
- `start_time`：分析开始时间
- `end_time`：分析结束时间

### 选填
- `query_id`：SQL 标识；如果提供，则优先分析该单条 SQL

---

## 决策逻辑

### 情况一：未提供 query_id

执行**实例整体慢 SQL 分析**：
- 统计指定时间段内的 SQL 总量、成功数量、失败数量
- 找出 TOP 慢 SQL / TOP 总耗时 SQL
- 分析用户、应用、SQL 类型、表等维度
- 找出最值得优先优化的 SQL
- 分析错误 SQL 的报错和原因
- 给出整体优化建议
- **每个诊断项都要输出总结**

### 情况二：提供了 query_id

执行**单条 SQL 分析**：
- 精确定位该 SQL
- 分析其耗时、扫描量、返回量、资源消耗
- 查看执行计划、诊断信息、读写表
- 解释该 SQL 为什么慢
- 给出针对性的优化建议
- **每个诊断项都要输出总结**

---

## 数据源

主要使用视图：`hologres.hg_query_log`

### 关键字段说明

#### 标识类字段
- `query_id`：SQL 唯一标识
- `digest`：SQL 指纹
- `usename`：用户名
- `application_name`：应用名
- `client_addr`：客户端地址
- `datname`：数据库名
- `command_tag`：SQL 类型
- `status`：执行状态
- `message`：错误信息

#### 时间类字段
- `query_start`：开始时间
- `query_end`：结束时间
- `duration`：执行耗时
- `query_date`：日期

#### SQL 原文
- `query`：SQL 文本

#### 资源与执行特征字段
- `result_rows`：返回行数
- `result_bytes`：返回字节数
- `read_rows`：读取行数
- `read_bytes`：读取字节数
- `affected_rows`：影响行数
- `affected_bytes`：影响字节数
- `memory_bytes`：内存消耗
- `shuffle_bytes`：Shuffle 数据量
- `cpu_time_ms`：CPU 时间
- `physical_reads`：物理读

#### 表相关字段
- `table_read`：读到的表数组
- `table_write`：写入的表

#### 执行计划与诊断字段
- `plan`
- `statistics`
- `agg_stats`
- `visualization_info`
- `query_detail`
- `query_extinfo`
- `extended_info`
- `extended_cost`

## 引擎类型说明

在单条 SQL 分析中，需要分析 `engine_type`，判断 SQL 使用了哪些引擎：

### HQE
- Hologres 原生自研引擎
- 大多数查询通过 HQE 实现
- HQE 执行效率较高
- 如果 SQL 主要走 HQE，通常说明执行路径较优

### PQE
- PostgreSQL 引擎
- 说明有部分 SQL 算子或表达式在 PQE 执行
- 一般是因为存在 HQE 未原生支持的算子或表达式
- 如果出现 PQE，应考虑是否能通过改写函数或表达式让 SQL 回到 HQE，以提升执行效率

### SDK / FixedQE
- Fixed Plan 的执行引擎
- 适合高效执行点读、点写、PrefixScan 等偏 Serving 类型的 SQL
- 从 Hologres V2.2 开始，SDK 执行引擎正式更名为 FixedQE
- 如果 SQL 属于 Serving 场景，使用 SDK/FixedQE 可能是合理的

### PG
- Frontend 本地计算
- 一般用于读取系统表元数据查询，不读取用户表数据
- 只占用极少系统资源
- 需要注意：DDL 也会使用 PostgreSQL 引擎
- 如果用户 SQL 走 PG，通常要判断是否属于系统元数据查询或 DDL

---

# 分析流程

## 一、实例整体慢 SQL 分析流程

当没有提供 `query_id` 时，按以下流程执行。

### 第 1 步：拉取时间段内 SQL 总体汇总

统计指定时间范围内的：
- SQL 总量
- 成功数量
- 失败数量

#### 该项输出模板
```
【总体汇总】
- 时间范围：{start_time} ~ {end_time}
- SQL 总量：{total_sql_cnt}
- 成功数量：{success_sql_cnt}
- 失败数量：{failed_sql_cnt}
- 成功率：{success_rate}
- 失败率：{failed_rate}
- 结论：{summary}
```

#### 推荐查询 SQL
```sql
SELECT
  COUNT(*) AS total_sql_cnt,
  COUNT(*) FILTER (WHERE status = 'success') AS success_sql_cnt,
  COUNT(*) FILTER (WHERE status <> 'success') AS failed_sql_cnt
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start <  TIMESTAMPTZ '{end_time}';
```

### 第 2 步：做整体画像分析

从以下维度分析慢 SQL 分布特征：
- 慢 SQL 总量
- 平均耗时 / 最大耗时
- 单次最慢 SQL
- 按 `digest` 聚合后的总耗时最高 SQL
- 按 `usename` 分布
- 按 `application_name` 分布
- 按 `command_tag` 分布
- 按 `table_read` / `table_write` 分布
- 按资源消耗特征分布
- 错误状态分布

#### 该项输出模板
```
【{诊断项名称}】
- 指标口径：{统计口径说明}
- 关键结果：{核心数值或Top对象，每条需包含 query_id（示例）}
- 典型完整 SQL（含 query_id）：query_id={sample_query_id}，SQL={从该类别中选取一条具有代表性的 SQL，输出完整 query 原文，不可截断}
- 现象总结：{现象描述}
- 原因判断：{原因分析}
- 建议：{优化建议}
- 结论：{一句话总结}
```

### 第 3 步：找出最该优先优化的 SQL

优先考虑以下 SQL：
1. 单次耗时高且资源消耗高
2. 按 `digest` 聚合后总耗时高
3. 扫描量大但返回少
4. CPU / 内存高
5. 物理读高

#### 该项输出模板
```
【优先优化对象】
- 优先级：{P0/P1/P2}
- SQL 标识：{query_id}
- 对应 digest：{digest}（如有）
- SQL 原文：{query}
- 耗时：{duration}
- 资源特征：{read_bytes / memory_bytes / cpu_time_ms / physical_reads}
- 入选原因：{为什么优先}
- 优化建议：{建议}
```

### 第 4 步：对重点 SQL 做进一步诊断

重点查看：
- `query`
- `plan`
- `statistics`
- `agg_stats`
- `query_detail`
- `query_extinfo`
- `extended_info`
- `table_read`
- `table_write`

#### 该项输出模板
```
【重点 SQL 诊断】
- SQL 标识：{query_id}
- SQL 原文：{query}
- 主要现象：{慢的表现}
- 执行计划特征：{plan/diagnostic summary}
- 资源特征：{扫描/CPU/内存/IO}
- 慢因判断：{原因}
- 优化建议：{建议}
```

### 第 5 步：输出错误 SQL 分析（按错误类型分类）

对 `status <> 'success'` 的 SQL 进行分析，**先按 SQLSTATE 错误码分类汇总**，再逐一分析。

#### 错误码提取方式

从 `message` 字段中提取 5 位 SQLSTATE 错误码：
```sql
ltrim(split_part(message, ': ', 2), ' ') AS error_code
```

#### 常见 Error Code 与错误类型映射

| SQLSTATE Code | 错误类型 | 说明 | 典型根因 |
| :--- | :--- | :--- | :--- |
| `XX000` | ERRCODE_INTERNAL_ERROR | 内部错误 | 引擎 bug 或异常状态 |
| `XX001` | ERRCODE_DATA_CORRUPTED | 数据损坏 | 存储损坏 |
| `53200` | ERRCODE_OUT_OF_MEMORY | 内存不足 | 查询内存过大，需降低并发或优化 SQL |
| `53300` | ERRCODE_TOO_MANY_CONNECTIONS | 连接过多 | 连接池耗尽 |
| `53000` | ERRCODE_INSUFFICIENT_RESOURCES | 资源不足 | 通用资源耗尽 |
| `57014` | ERRCODE_QUERY_CANCELED | 查询被取消 | 超时或手动取消 |
| `57P01` | ERRCODE_ADMIN_SHUTDOWN | 管理员关闭 | 实例重启或维护 |
| `57000` | ERRCODE_OPERATOR_INTERVENTION | 操作员干预 | 手动干预 |
| `40P01` | ERRCODE_T_R_DEADLOCK_DETECTED | 死锁检测 | 并发事务冲突 |
| `40001` | ERRCODE_T_R_SERIALIZATION_FAILURE | 序列化失败 | 事务冲突 |
| `23505` | ERRCODE_UNIQUE_VIOLATION | 唯一性冲突 | 插入/更新时主键/唯一键重复 |
| `23502` | ERRCODE_NOT_NULL_VIOLATION | 非空约束冲突 | 向 NOT NULL 列插入 NULL |
| `42P01` | ERRCODE_UNDEFINED_TABLE | 表不存在 | 表不存在 |
| `42703` | ERRCODE_UNDEFINED_COLUMN | 列不存在 | 列不存在 |
| `42601` | ERRCODE_SYNTAX_ERROR | 语法错误 | SQL 语法问题 |
| `42501` | ERRCODE_INSUFFICIENT_PRIVILEGE | 权限不足 | 权限被拒绝 |
| `42883` | ERRCODE_UNDEFINED_FUNCTION | 函数不存在 | 函数不存在 |
| `55P03` | ERRCODE_LOCK_NOT_AVAILABLE | 锁不可用 | 锁超时 |
| `08006` | ERRCODE_CONNECTION_FAILURE | 连接失败 | 网络或后端断开 |
| `08P01` | ERRCODE_PROTOCOL_VIOLATION | 协议违规 | 客户端/服务端协议不匹配 |
| `22012` | ERRCODE_DIVISION_BY_ZERO | 除零错误 | 算术错误 |
| `22001` | ERRCODE_STRING_DATA_RIGHT_TRUNCATION | 字符串截断 | 值长度超过列限制 |
| `HG000` | ERRCODE_HG_NEED_RETRY | Hologres 需重试 | 临时错误，可重试 |
| `HG001` | ERRCODE_HG_PLPGSQL_NEED_RETRY | Hologres PL/pgSQL 需重试 | 临时 PL/pgSQL 错误，可重试 |

完整映射表见 [error-codes.md](references/error-codes.md)。

#### 错误码分类汇总 SQL
```sql
SELECT
  ltrim(split_part(message, ': ', 2), ' ') AS error_code,
  count(*) AS error_count,
  min(query_start) AS first_seen,
  max(query_start) AS last_seen,
  count(DISTINCT usename) AS affected_users
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start < TIMESTAMPTZ '{end_time}'
  AND status = 'FAILED'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;
```

#### 该项输出模板
```
【错误 SQL 按错误类型分类】
- 指标口径：按 SQLSTATE 错误码归类，统计每类错误的失败数量、涉及用户、首次/末次出现时间
- 关键结果：
  | 错误类型 (SQLSTATE) | 失败数 | 涉及用户 | 首次出现 | 末次出现 | 典型报错 |
  | :--- | :--- | :--- | :--- | :--- | :--- |
  | {error_type} ({sqlstate}) | {cnt} | {affected_users} | {first_seen} | {last_seen} | {sample_error} |
- 典型完整 SQL（含 query_id）：query_id={sample_query_id}，SQL={从该类别中选取一条具有代表性的 SQL，输出完整 query 原文，不可截断}
- 现象总结：{各类错误占比和集中度}
- 原因判断：{错误根因分析}
- 建议：{针对性修复建议}
- 结论：{一句话总结}
```

### 第 6 步：输出结论和建议（合并优化清单）

输出应明确包含：
- 哪些 SQL 最慢
- 哪些 SQL 最值得优先优化
- 慢因是什么
- 错误 SQL 的报错和原因是什么
- 应该如何优化
- **每个优化对象必须给出具体的 query_id 和完整 SQL 原文**
- **优化对象和最终结论合并到同一个章节输出**

#### 该项输出模板
```
【最终结论与优化建议】
- 时间范围：{start_time} ~ {end_time}
- 总体情况：{summary}
- 主要瓶颈：{瓶颈}

### 需要整改的 SQL 清单

#### P0 - 立即处理
**{表名/SQL标识}**（{错误类型简述}）
- query_id：{query_id}
- 完整 SQL：{完整 SQL 原文，不可截断，必须包含全部 query 内容}
- 报错信息：{message}
- 错误类型：{语法/权限/资源/超时/对象不存在/其他}
- 整改动作：{具体处理建议}

#### P1 - 观察监控
**{表名/SQL标识}**（{现象简述}）
- query_id：{query_id}
- 完整 SQL：{完整 SQL 原文，不可截断}
- 状态：{SUCCESS/FAILED}，耗时 {duration}
- 整改动作：{监控/优化建议}

### DROP/修复命令参考（如适用）
```sql
{可直接执行的 DDL/DML 命令}
```

### 总体建议
1. **立即处理**：{优先级最高的动作}
2. **监控观察**：{需要持续关注的对象}
3. **例行维护**：{长期优化建议}
```

## 二、单条 SQL 分析流程

当提供了 `query_id` 时，按以下流程执行。

### 第 1 步：定位 SQL 记录

通过 `query_id` 精确查询对应 SQL。

#### 该项输出模板
```
【SQL 基本信息】
- SQL 标识：{query_id}
- SQL 原文：{query}
- 用户：{usename}
- 应用：{application_name}
- 客户端：{client_addr}
- 状态：{status}
- 执行时间：{query_start} ~ {query_end}
- 耗时：{duration}
- 结论：{summary}
```

### 第 2 步：判断该 SQL 是否慢、慢在哪里

关注以下指标：
- `duration`
- `read_rows`
- `read_bytes`
- `result_rows`
- `result_bytes`
- `memory_bytes`
- `cpu_time_ms`
- `physical_reads`
- `engine_type`

#### 该项输出模板
```
【慢因诊断】
- 扫描情况：{是否扫描过大}
- 过滤情况：{是否有效过滤}
- Join 情况：{是否Join代价高}
- 聚合/排序情况：{是否有大聚合/排序}
- 内存情况：{是否有内存压力}
- CPU 情况：{是否有CPU压力}
- 表设计/SQL写法：{是否存在问题}
- 引擎分析：{HQE/PQE/SDK/PG 的使用情况与影响}
- 结论：{summary}
```

### 第 3 步：分析慢因

结合以下信息进行诊断：
- SQL 原文 `query`
- 执行计划 `plan`
- 统计信息 `statistics`
- 聚合信息 `agg_stats`
- 执行细节 `query_detail`
- 扩展诊断 `query_extinfo`
- 扩展信息 `extended_info`
- 读写表信息 `table_read`、`table_write`

#### 该项输出模板
```
【慢因诊断】
- 扫描情况：{是否扫描过大}
- 过滤情况：{是否有效过滤}
- Join 情况：{是否Join代价高}
- 聚合/排序情况：{是否有大聚合/排序}
- 内存情况：{是否有内存压力}
- CPU 情况：{是否有CPU压力}
- 执行引擎情况：{查询的sql推荐使用高性能执行引擎HQE}
- 表设计/SQL写法：{是否存在问题}
- 结论：{summary}
```

#### 引擎分析说明

单条 SQL 分析中，`engine_type` 是必须分析项：
- 如果出现 PQE
    - 说明 SQL 中有部分逻辑未走 HQE
    - 优先判断是否存在：
        - 不支持的函数
        - 不支持的表达式
        - 复杂类型转换
        - 无法下推的算子
    - 可尝试改写 SQL 让更多逻辑进入 HQE
- 如果主要是 SDK / FixedQE
    - 说明 SQL 更偏 Serving 访问模式
    - 如果业务场景符合点查、前缀扫描等，可认为合理
    - 如果不是 Serving 场景，则需要看是否存在优化空间
- 如果是 PG
    - 说明可能是系统表查询或 DDL
    - 若是用户数据查询却走 PG，需要重点关注
- 如果主要是 HQE
    - 通常说明执行路径较优
    - 仍需结合资源指标和执行计划判断是否存在其他瓶颈

### 第 4 步：输出原因判断

说明该 SQL 慢的主要原因，例如：
- 扫描量大
- 返回量少
- Join 成本高
- 聚合 / 排序重
- 内存占用高
- CPU 消耗高
- 表设计不合理
- SQL 写法不合理

#### 该项输出模板
```
【原因总结】
- 主瓶颈：{primary_reason}
- 次要瓶颈：{secondary_reason}
- 解释：{why_slow}
- 最优先修改点：{first_action}
```

### 第 5 步：输出优化建议

给出可执行的优化建议，例如：
- 增加过滤条件
- 减少扫描列 / 扫描行
- 调整 Join 顺序
- 减少数据量
- 调整表分布键 / 分区键 / 索引
- 减少返回数据量
- 采用预聚合或拆分查询

#### 该项输出模板
```
【优化建议】
- 最核心优化点：{core_suggestion}
- 高收益建议：{high_value_suggestions}
- 辅助建议：{secondary_suggestions}
- 优先级顺序：{priority_order}
- 结论：{summary}
```

---

## 参考文档

| 文档 | 内容 |
| :--- | :--- |
| [error-codes.md](references/error-codes.md) | SQLSTATE 错误码 → 错误类型完整映射表（PostgreSQL + Hologres） |
| [diagnostic-queries.md](references/diagnostic-queries.md) | 完整诊断 SQL 集合 |
| [log-export.md](references/log-export.md) | 导出日志到内外部表 |
| [configuration.md](references/configuration.md) | 配置参数说明 |

---

# 推荐查询 SQL

### 1、查询指定时间段内 SQL 总体汇总
```sql
SELECT
  COUNT(*) AS total_sql_cnt,
  COUNT(*) FILTER (WHERE status = 'success') AS success_sql_cnt,
  COUNT(*) FILTER (WHERE status <> 'success') AS failed_sql_cnt
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start <  TIMESTAMPTZ '{end_time}';
```

### 2、按 digest 聚合，找总耗时最高的 SQL 模板（含 engine_type，排除 FixedQE）
```sql
SELECT
  digest,
  (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id,
  command_tag,
  (array_agg(engine_type::text ORDER BY duration DESC))[1] AS sample_engine_type,
  COUNT(*) AS exec_cnt,
  AVG(duration)::bigint AS avg_duration,
  MAX(duration) AS max_duration,
  SUM(duration) AS total_duration,
  SUM(read_rows) AS total_read_rows,
  SUM(read_bytes) AS total_read_bytes,
  SUM(result_rows) AS total_result_rows,
  SUM(cpu_time_ms) AS total_cpu_time_ms,
  SUM(memory_bytes) AS total_memory_bytes,
  (array_agg(query ORDER BY duration DESC))[1] AS sample_query
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start < TIMESTAMPTZ '{end_time}'
  AND digest IS NOT NULL
  AND (engine_type IS NULL OR engine_type::text NOT LIKE '%FixedQE%')
GROUP BY digest, command_tag
ORDER BY total_duration DESC
LIMIT 20;
```

> **说明**：`engine_type` 为数组类型，聚合时需使用 `engine_type::text` 转换。
>
> **FixedQE 过滤原因**：Fixed Plan（FixedQE）引擎专为点查/点写优化，其 SQL 特征为 `unnest` 批量 INSERT 或单条点查。这类 SQL 执行频次极高（日均数十万~数百万次），累计总耗时大，但单次平均耗时通常在几百毫秒内，属于正常的业务 Serving 负载。在慢 SQL 诊断中，FixedQE 类 SQL 通常**不是性能瓶颈的重点**，因此本 SQL 主动过滤掉 FixedQE，让诊断聚焦于 **HQE（分析型查询）** 和 **PG（系统/后台任务）** 等真正需要深入分析的引擎类型。
>
> 如需单独查看 FixedQE 的执行情况，可去掉 `AND (engine_type IS NULL OR engine_type::text NOT LIKE '%FixedQE%')` 条件另行查询。

### 3、按单次耗时找最慢 SQL（含 engine_type）
```sql
SELECT
  query_id,
  digest,
  usename,
  application_name,
  command_tag,
  engine_type,
  duration,
  read_rows,
  read_bytes,
  result_rows,
  result_bytes,
  cpu_time_ms,
  memory_bytes,
  physical_reads,
  query
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start <  TIMESTAMPTZ '{end_time}'
ORDER BY duration DESC
LIMIT 20;
```

> **说明**：分析时需结合 `engine_type` 判断 SQL 使用的执行引擎。HQE 类查询重点关注扫描量、内存、CPU 和执行计划；FixedQE 类查询（点查/点写）若耗时异常高，优先检查并发压力和锁竞争；PG 类查询（ANALYZE/系统表查询）耗时高通常与表数据量或元数据操作相关。

### 4、按用户分析
```sql
SELECT
  usename,
  COUNT(*) AS slow_sql_cnt,
  SUM(duration) AS total_duration,
  AVG(duration) AS avg_duration,
  SUM(read_bytes) AS total_read_bytes,
  SUM(cpu_time_ms) AS total_cpu_time_ms,
  (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id,
  (array_agg(query ORDER BY duration DESC))[1] AS sample_query
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start <  TIMESTAMPTZ '{end_time}'
GROUP BY usename
ORDER BY total_duration DESC;
```

### 5、按应用分析
```sql
SELECT
  application_name,
  COUNT(*) AS slow_sql_cnt,
  SUM(duration) AS total_duration,
  AVG(duration) AS avg_duration,
  (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id,
  (array_agg(query ORDER BY duration DESC))[1] AS sample_query
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start <  TIMESTAMPTZ '{end_time}'
GROUP BY application_name
ORDER BY total_duration DESC;
```

### 6、按 SQL 类型分析
```sql
SELECT
  command_tag,
  COUNT(*) AS cnt,
  SUM(duration) AS total_duration,
  AVG(duration) AS avg_duration,
  SUM(read_bytes) AS total_read_bytes,
  SUM(cpu_time_ms) AS total_cpu_time_ms,
  (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id,
  (array_agg(query ORDER BY duration DESC))[1] AS sample_query
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start <  TIMESTAMPTZ '{end_time}'
GROUP BY command_tag
ORDER BY total_duration DESC;
```

### 7、按读表分析
```sql
SELECT
  t.table_name,
  COUNT(*) AS slow_sql_cnt,
  SUM(l.duration) AS total_duration,
  AVG(l.duration) AS avg_duration,
  SUM(l.read_bytes) AS total_read_bytes,
  SUM(l.cpu_time_ms) AS total_cpu_time_ms,
  (array_agg(l.query_id ORDER BY l.duration DESC))[1] AS sample_query_id,
  (array_agg(l.query ORDER BY l.duration DESC))[1] AS sample_query
FROM hologres.hg_query_log l
CROSS JOIN LATERAL unnest(l.table_read) AS t(table_name)
WHERE l.query_start >= TIMESTAMPTZ '{start_time}'
  AND l.query_start <  TIMESTAMPTZ '{end_time}'
GROUP BY t.table_name
ORDER BY total_duration DESC
LIMIT 20;
```

### 8、按写表分析
```sql
SELECT
  table_write,
  COUNT(*) AS slow_sql_cnt,
  SUM(duration) AS total_duration,
  AVG(duration) AS avg_duration,
  SUM(affected_rows) AS total_affected_rows,
  SUM(affected_bytes) AS total_affected_bytes,
  (array_agg(query_id ORDER BY duration DESC))[1] AS sample_query_id,
  (array_agg(query ORDER BY duration DESC))[1] AS sample_query
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start <  TIMESTAMPTZ '{end_time}'
  AND table_write IS NOT NULL
GROUP BY table_write
ORDER BY total_duration DESC;
```

### 9、扫描量最大的 SQL
```sql
SELECT
  query_id,
  digest,
  duration,
  read_rows,
  read_bytes,
  result_rows,
  result_bytes,
  query
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start <  TIMESTAMPTZ '{end_time}'
ORDER BY read_bytes DESC
LIMIT 20;
```

### 10、内存消耗最高的 SQL
```sql
SELECT
  query_id,
  digest,
  duration,
  memory_bytes,
  cpu_time_ms,
  query
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start <  TIMESTAMPTZ '{end_time}'
ORDER BY memory_bytes DESC, duration DESC
LIMIT 20;
```

### 11、异常状态分析（主要分析错误 SQL）
```sql
-- 提取错误码并按类型汇总
SELECT
  ltrim(split_part(message, ': ', 2), ' ') AS error_code,
  count(*) AS error_count,
  min(query_start) AS first_seen,
  max(query_start) AS last_seen,
  count(DISTINCT usename) AS affected_users
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start < TIMESTAMPTZ '{end_time}'
  AND status = 'FAILED'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;
```

```sql
-- 按错误码分类查看具体错误 SQL
SELECT
  query_id,
  digest,
  ltrim(split_part(message, ': ', 2), ' ') AS error_code,
  duration,
  status,
  message,
  query
FROM hologres.hg_query_log
WHERE query_start >= TIMESTAMPTZ '{start_time}'
  AND query_start < TIMESTAMPTZ '{end_time}'
  AND status <> 'success'
ORDER BY query_start DESC;
```

### 12、按 query_id 查询单条 SQL 详情
```sql
SELECT
  query_id,
  digest,
  usename,
  application_name,
  client_addr,
  status,
  command_tag,
  duration,
  query_start,
  query_end,
  read_rows,
  read_bytes,
  result_rows,
  result_bytes,
  cpu_time_ms,
  memory_bytes,
  shuffle_bytes,
  physical_reads,
  table_read,
  table_write,
  query,
  plan,
  statistics,
  agg_stats,
  query_detail,
  query_extinfo,
  extended_info,
  visualization_info,
  extended_cost
FROM hologres.hg_query_log
WHERE query_id = '{query_id}';
```

---

# 优先优化规则

当没有提供 `query_id` 时，建议按以下顺序判断"最该优先优化的 SQL"：

### 第一优先
- `duration` 高
- `read_bytes` 高
- `memory_bytes` 高
- `cpu_time_ms` 高
- `physical_reads` 高

### 第二优先
- 按 `digest` 聚合后 `SUM(duration)` 高
- 执行频次高
- 总资源消耗高

### 第三优先
- `read_rows / result_rows` 比值很高
- 扫描很多、返回很少

### 第四优先
- 反复出现在 `table_read` 中的热点表
- 慢 SQL 集中访问的重点表

---

# 慢因判断规则

- 扫描过大
    - `read_rows`、`read_bytes` 很高
- 过滤不够好
    - `read_rows / result_rows` 很高
- 内存压力大
    - `memory_bytes` 很高
- IO 压力大
    - `physical_reads` 很高
- CPU 压力大
    - `cpu_time_ms` 很高
- 热点表问题
    - 某些表在 `table_read` 中高频出现
- SQL 写法问题
    - 过滤条件不足、返回列太多、Join 顺序不合理、子查询过重
- 执行计划问题
    - 需要重点看 `plan`、`statistics`、`query_detail`、`extended_info`

---

# 输出要求

## 实例级整体慢 Query 诊断文档规范

### 标题规范
- 实例级分析标题统一为：`Hologres 实例级整体慢 Query 诊断`
- 不出现"报告"二字

### 分析人规范
- 分析人字段必须写实际执行诊断 SQL 的 `current_user`（如 `<current_user>`）
- 不写固定值如"QoderWork"或"AI助手"

### 引擎类型分析规范
- digest 聚合和单次最慢 SQL 分析时，必须一并查询并分析 `engine_type`
- `engine_type` 字段为数组类型，聚合查询中需使用 `engine_type::text` 进行转换
- **Fixed Plan（FixedQE）类 SQL**：以点查/点写为主，性能特征与 HQE 分析型查询不同，在慢 SQL 诊断中无需作为重点分析对象，可简要提及执行频次和总耗时即可
- **HQE 类 SQL**：为分析型查询主引擎，需重点分析扫描量、内存、CPU、执行计划等
- **PQE 类 SQL**：说明有部分算子未走 HQE，需判断是否可改写回 HQE
- **PG 类 SQL**：多为系统表查询或 DDL，ANALYZE 等后台任务走此引擎属正常

## 实例整体分析输出建议包含
1. 分析时间范围
2. SQL 总量、成功数量、失败数量总结
3. 慢 SQL 总体情况总结
4. TOP 慢 SQL 总结
5. TOP 总耗时 SQL 模板总结
6. 主要用户 / 应用总结
7. 主要涉及表总结
8. 资源瓶颈总结
9. 错误 SQL 总结
10. 优先优化清单总结
11. 每项诊断结果总结
12. 最终优化建议总结

## 单条 SQL 分析输出建议包含
1. `query_id`
2. SQL 原文
3. 执行耗时总结
4. 扫描与返回特征总结
5. 资源消耗总结
6. 读写表总结
7. 执行计划摘要总结
8. 慢因总结
9. 优化建议总结

---

# 输出模板总则

每个诊断项都必须采用以下固定格式输出：
```
【诊断项名称】
- 指标口径：{统计口径说明}
- 关键结果：{核心数值或Top对象}
- 现象总结：{现象描述}
- 原因判断：{原因分析}
- 建议：{优化建议}
- 结论：{一句话总结}
```
