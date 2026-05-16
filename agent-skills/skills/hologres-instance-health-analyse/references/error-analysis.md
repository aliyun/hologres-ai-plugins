# 报错归类分析

所有 SQL 通过 `hologres sql run` 执行，返回结构化 JSON：`{"ok": true, "data": {"rows": [...], "count": N}}`

执行前设置 SQL tracking：

```bash
export HOLOGRES_SKILL=hologres-instance-health-analyse
```

## 报错归类统计

### 完整报错分类 CASE WHEN 逻辑

以下为 Hologres 专业报错分类规则，用于将 `hg_query_log.message` 归类为可读的错误类别：

```sql
CASE
  WHEN ltrim(split_part(message, ': ', 2),' ') != 'XX000'
       AND length(ltrim(split_part(message, ': ', 2),' ')) = 5
    THEN ltrim(split_part(message, ': ', 2),' ')
  WHEN (query LIKE '-- query row count from analyze table%'
        OR query LIKE '-- query from analyze table%')
    THEN 'AutoAnalyze-Failed'
  WHEN message LIKE '%canceling statement due to user request%'
    THEN 'User Cancelled'
  WHEN (message LIKE '%Total memory used by all existing queries exceeded memory limitation%'
        OR message LIKE '%query exceed per query memory limitation%')
    THEN 'OOM'
  WHEN message LIKE '%WriteLogRecord is not allowed in readonly mode%'
    THEN 'READONLY'
  WHEN message LIKE '%query next from foreign table executor failed%'
    THEN 'queryNext Foreign table Failed'
  WHEN message LIKE '%SERVER_INTERNAL_ERROR%query next from pg executor failed from%'
    THEN 'queryNext PQE Failed'
  WHEN (message LIKE '%Exceeds the scan limitation%'
        OR message LIKE '%Exceeds the partition limitation%')
    THEN 'Exceed Odps Scan Limit'
  WHEN message LIKE '%internal error: Invalid table id%'
    THEN 'Invalid TableId'
  WHEN (message LIKE '%failed to get foregin table split:ERPC_ERROR_CONNECTION_CLOSED%'
        OR message LIKE '%failed to import foregin schema:ERPC_ERROR_CONNECTION_CLOSED%')
    THEN 'Foreign Split Or Schema Connection Closed'
  WHEN message LIKE '%transaction kind not supported%'
    THEN 'TransactionKindUnsupported'
  WHEN message LIKE '%OPERATION_EXPIRED%is not found or it was expired and cancelled.%'
    THEN 'OPERATION EXPIRED'
  WHEN message LIKE '%internal error: query is cancelled.%'
    THEN 'Query Is Cancelled'
  WHEN message LIKE '%nested transaction not supported%'
    THEN 'Nested Transaction Unsupported'
  WHEN (message LIKE '%failed to import foregin schema:Table not found%'
        OR message LIKE '%failed to get foregin table split:Table not found%'
        OR message LIKE '%Failed to get odps table:Not enable acid table%'
        OR message LIKE '%failed to get foregin table split:% not found%')
    THEN 'Import Foreign Table Not Found'
  WHEN message LIKE '%internal error: Cannot acquire lock in time, current owners%'
    THEN 'Cannot Acquire Lock In Time'
  WHEN (message LIKE '%permission denied%'
        OR message LIKE '%Build desc failed: failed to check permission%')
    THEN 'permission denied'
  WHEN message LIKE '%violates not-null constraint%'
    THEN 'not-null constraint'
  WHEN message LIKE '%violates partition constraint%'
    THEN 'partition constraint'
  WHEN message LIKE '%duplicate key value violates%'
    THEN 'pk violates'
  WHEN message LIKE '%division by zero%'
    THEN 'division by zero'
  WHEN (message LIKE 'invalid input syntax' OR message LIKE 'invalid value'
        OR message LIKE '%invalid definition%' OR message LIKE '%invalid%name%'
        OR message LIKE '%invalid%column%')
    THEN 'invalid input'
  WHEN message LIKE '%does not exist%'
    THEN 'does not exist'
  WHEN (message LIKE '%already exist%' OR message LIKE '%is already a%')
    THEN 'already exist'
  WHEN (message LIKE '%no need to%' OR message LIKE '%must be a subset of%'
        OR message LIKE '%invalid%property key%' OR message LIKE '%only%can be used%'
        OR message LIKE '%is already set%' OR message LIKE '%must follow create%'
        OR message LIKE '%Build query failed: can''t find%' OR message LIKE '%is for management%'
        OR message LIKE '%Full key is required%'
        OR message LIKE '%scanning a non-binlog table%'
        OR message LIKE '%number of read rows%exceeds limit%'
        OR message LIKE '%SET_TABLE_PROPERTY and CREATE TABLE statement are not in the same transaction%')
    THEN 'Usage Problem'
  WHEN (message LIKE '%can support just one%' OR message LIKE '%not supported option%'
        OR message LIKE '%is not supported for%'
        OR message LIKE '%Dynamic partition selector is not supported%'
        OR message LIKE '%Not support%')
    THEN 'Unsupported Feature'
  WHEN message LIKE '%Build desc failed: failed to get foregin table split:Can''t find file system factory: jdbc:postgresql%'
    THEN 'PG System Factory Not Found'
  WHEN message LIKE '%unmatched data row schema number%'
    THEN 'Unmatched Data Row Schema Number'
  WHEN message LIKE '%Datasets has different schema Schema%'
    THEN 'Dataset Schema Not Match'
  WHEN message LIKE '%babysitter actor not ready%'
    THEN 'Babysitter Actor Not Ready'
  WHEN message LIKE '%code: kActorNotExist%'
    THEN 'Actor Not Exist'
  WHEN message LIKE '%SERVER_INTERNAL_ERROR%internal error: query is closed.%'
    THEN 'Internal query Is Closed'
  WHEN message LIKE '%babysitter not ready, req:name%'
    THEN 'Some Server Role Not Ready'
  WHEN message LIKE '%internal error: Connect timeout, err: std_exception: Connection refused%'
    THEN 'Connection Refused'
  WHEN message LIKE '%kActorInvokeError%'
    THEN 'Actor Invoke Error'
  WHEN message LIKE '%IO error: Failed to execute pangu open normal file%'
    THEN 'Pangu IO Error'
  WHEN message LIKE '%Operation failed. Try again.: kTimedOut: ERPC_ERROR_TIMEOUT%'
    THEN 'ERPC_ERROR_TIMEOUT'
  WHEN message LIKE '%ERPC_ERROR_CONNECTION_CLOSED%'
    THEN 'ERPC_ERROR_CONNECTION_CLOSED'
  WHEN message LIKE '%kConnectError: channel is empty%'
    THEN 'Connect Error Channel Empty'
  WHEN message LIKE '%foreign meta fetcher, internal error%'
    THEN 'Foreign Meta Fetcher Internal Error'
  WHEN message LIKE '%internal error: Connect timeout, err: std_exception: Semaphore timedout%'
    THEN 'Semaphore Timeout'
  WHEN message LIKE '%mismatches the version of the table%'
    THEN 'Table Version Mismatch'
  WHEN message LIKE '%internal error: kUpdate is not allowed without original row%'
    THEN 'Missing Original Row On Update'
  WHEN message LIKE '%Build desc failed: Unexpected expr type in array expr%'
    THEN 'Unexpected Expr Type'
  WHEN message LIKE '%Failed to execute fixed request : ERPC_ERROR_RPCCALL_MISMATCH%'
    THEN 'FIXEDREQ_ERPC_ERROR_RPCCALL_MISMATCH'
  WHEN message LIKE '%Internal error%'
    THEN 'Other Internal Errors'
  ELSE 'OTHER'
END AS error_category
```

### 按分类归类统计（过去7天，精简版）

SKILL.md 中使用的精简版（覆盖最常见的 12 种分类）：

```bash
hologres sql run --no-limit-check "SELECT error_category, warehouse_name, count(1) AS error_count, min(query_start) AS first_seen, max(query_start) AS last_seen FROM (SELECT *, CASE WHEN ltrim(split_part(message, ': ', 2),' ') != 'XX000' and length(ltrim(split_part(message, ': ', 2),' ')) = 5 THEN ltrim(split_part(message, ': ', 2),' ') WHEN (query LIKE '-- query row count from analyze table%' or query LIKE '-- query from analyze table%') THEN 'AutoAnalyze-Failed' WHEN message LIKE '%canceling statement due to user request%' THEN 'User Cancelled' WHEN (message LIKE '%Total memory used by all existing queries exceeded memory limitation%' OR message LIKE '%query exceed per query memory limitation%') THEN 'OOM' WHEN message LIKE '%WriteLogRecord is not allowed in readonly mode%' THEN 'READONLY' WHEN message LIKE '%query next from foreign table executor failed%' THEN 'queryNext Foreign table Failed' WHEN message LIKE '%SERVER_INTERNAL_ERROR%query next from pg executor failed from%' THEN 'queryNext PQE Failed' WHEN (message LIKE '%Exceeds the scan limitation%' OR message LIKE '%Exceeds the partition limitation%') THEN 'Exceed Odps Scan Limit' WHEN message LIKE '%permission denied%' THEN 'permission denied' WHEN message LIKE '%duplicate key value violates%' THEN 'pk violates' WHEN message LIKE '%does not exist%' THEN 'does not exist' WHEN message LIKE '%Internal error%' THEN 'Other Internal Errors' ELSE 'OTHER' END AS error_category, warehouse_name, query_start FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '7 days' AND message IS NOT NULL) t GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 50"
```

### 按分类归类统计（过去7天，完整版 50+ 分类）

```bash
hologres sql run --no-limit-check "SELECT error_category, warehouse_name, count(1) AS error_count, min(query_start) AS first_seen, max(query_start) AS last_seen FROM (SELECT *, CASE WHEN ltrim(split_part(message, ': ', 2),' ') != 'XX000' and length(ltrim(split_part(message, ': ', 2),' ')) = 5 THEN ltrim(split_part(message, ': ', 2),' ') WHEN (query LIKE '-- query row count from analyze table%' or query LIKE '-- query from analyze table%') THEN 'AutoAnalyze-Failed' WHEN message LIKE '%canceling statement due to user request%' THEN 'User Cancelled' WHEN (message LIKE '%Total memory used by all existing queries exceeded memory limitation%' OR message LIKE '%query exceed per query memory limitation%') THEN 'OOM' WHEN message LIKE '%WriteLogRecord is not allowed in readonly mode%' THEN 'READONLY' WHEN message LIKE '%query next from foreign table executor failed%' THEN 'queryNext Foreign table Failed' WHEN message LIKE '%SERVER_INTERNAL_ERROR%query next from pg executor failed from%' THEN 'queryNext PQE Failed' WHEN (message LIKE '%Exceeds the scan limitation%' OR message LIKE '%Exceeds the partition limitation%') THEN 'Exceed Odps Scan Limit' WHEN message LIKE '%internal error: Invalid table id%' THEN 'Invalid TableId' WHEN (message LIKE '%failed to get foregin table split:ERPC_ERROR_CONNECTION_CLOSED%' OR message LIKE '%failed to import foregin schema:ERPC_ERROR_CONNECTION_CLOSED%') THEN 'Foreign Split Or Schema Connection Closed' WHEN message LIKE '%transaction kind not supported%' THEN 'TransactionKindUnsupported' WHEN message LIKE '%OPERATION_EXPIRED%is not found or it was expired and cancelled.%' THEN 'OPERATION EXPIRED' WHEN message LIKE '%internal error: query is cancelled.%' THEN 'Query Is Cancelled' WHEN message LIKE '%nested transaction not supported%' THEN 'Nested Transaction Unsupported' WHEN (message LIKE '%failed to import foregin schema:Table not found%' OR message LIKE '%failed to get foregin table split:Table not found%' OR message LIKE '%Failed to get odps table:Not enable acid table%' OR message LIKE '%failed to get foregin table split:% not found%') THEN 'Import Foreign Table Not Found' WHEN message LIKE '%internal error: Cannot acquire lock in time, current owners%' THEN 'Cannot Acquire Lock In Time' WHEN (message LIKE '%permission denied%' OR message LIKE '%Build desc failed: failed to check permission%') THEN 'permission denied' WHEN message LIKE '%violates not-null constraint%' THEN 'not-null constraint' WHEN message LIKE '%violates partition constraint%' THEN 'partition constraint' WHEN message LIKE '%duplicate key value violates%' THEN 'pk violates' WHEN message LIKE '%division by zero%' THEN 'division by zero' WHEN (message LIKE 'invalid input syntax' OR message LIKE 'invalid value' OR message LIKE '%invalid definition%' OR message LIKE '%invalid%name%' OR message LIKE '%invalid%column%') THEN 'invalid input' WHEN message LIKE '%does not exist%' THEN 'does not exist' WHEN (message LIKE '%already exist%' OR message LIKE '%is already a%') THEN 'already exist' WHEN (message LIKE '%no need to%' OR message LIKE '%must be a subset of%' OR message LIKE '%invalid%property key%' OR message LIKE '%only%can be used%' OR message LIKE '%is already set%' OR message LIKE '%must follow create%' OR message LIKE '%is for management%' OR message LIKE '%Full key is required%' OR message LIKE '%scanning a non-binlog table%' OR message LIKE '%number of read rows%exceeds limit%') THEN 'Usage Problem' WHEN (message LIKE '%can support just one%' OR message LIKE '%not supported option%' OR message LIKE '%is not supported for%' OR message LIKE '%Dynamic partition selector is not supported%' OR message LIKE '%Not support%') THEN 'Unsupported Feature' WHEN message LIKE '%babysitter actor not ready%' THEN 'Babysitter Actor Not Ready' WHEN message LIKE '%code: kActorNotExist%' THEN 'Actor Not Exist' WHEN message LIKE '%kActorInvokeError%' THEN 'Actor Invoke Error' WHEN message LIKE '%IO error: Failed to execute pangu open normal file%' THEN 'Pangu IO Error' WHEN message LIKE '%Operation failed. Try again.: kTimedOut: ERPC_ERROR_TIMEOUT%' THEN 'ERPC_ERROR_TIMEOUT' WHEN message LIKE '%ERPC_ERROR_CONNECTION_CLOSED%' THEN 'ERPC_ERROR_CONNECTION_CLOSED' WHEN message LIKE '%kConnectError: channel is empty%' THEN 'Connect Error Channel Empty' WHEN message LIKE '%mismatches the version of the table%' THEN 'Table Version Mismatch' WHEN message LIKE '%Internal error%' THEN 'Other Internal Errors' ELSE 'OTHER' END AS error_category, warehouse_name, query_start FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '7 days' AND message IS NOT NULL) t GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 50"
```

### 按小时统计报错趋势

```bash
hologres sql run --no-limit-check "SELECT date_trunc('hour', query_start) AS hour, count(1) AS failed_count FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '1 day' AND message IS NOT NULL GROUP BY 1 ORDER BY 1"
```

输出解读：
- `failed_count` 突增的小时段为故障高峰

### 按用户统计报错

```bash
hologres sql run --no-limit-check "SELECT usename, warehouse_name, count(1) AS failed_count, min(query_start) AS first_seen, max(query_start) AS last_seen FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '7 days' GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20"
```

### 查看具体报错 SQL 示例

```bash
hologres sql run "SELECT query_id, usename, warehouse_name, query_start, left(message, 200) AS error_msg, left(query, 200) AS sql_snippet FROM hologres.hg_query_log WHERE status = 'FAILED' AND query_start >= now() - interval '1 day' ORDER BY query_start DESC LIMIT 20"
```

## 错误分类解决方案参考

| 分类 | 含义 | 解决方案 |
|------|------|----------|
| `57014` (PG错误码) | statement timeout | 优化 SQL 或调整 `statement_timeout` |
| `OOM` | 内存不足 | 减少并发、优化大查询、扩容 Warehouse |
| `User Cancelled` | 用户主动取消 | 通常无需处理 |
| `READONLY` | 只读模式写入 | 检查实例是否在维护中 |
| `AutoAnalyze-Failed` | 自动分析表失败 | 通常可忽略，检查表元数据 |
| `queryNext Foreign table Failed` | 外表查询失败 | 检查 MaxCompute 连通性和表权限 |
| `queryNext PQE Failed` | PG Executor 失败 | 重试，若持续则报障 |
| `Exceed Odps Scan Limit` | 超出 MaxCompute 扫描限制 | 添加分区过滤条件 |
| `Invalid TableId` | 表 ID 无效 | 表可能被删除后重建，重新查询 |
| `Foreign Split Or Schema Connection Closed` | 外表连接关闭 | 网络波动，重试即可 |
| `TransactionKindUnsupported` | 事务类型不支持 | 检查 SQL 事务用法 |
| `OPERATION EXPIRED` | 操作过期 | 长事务超时，拆分事务 |
| `Query Is Cancelled` | 查询被系统取消 | 可能 OOM 或超时触发 |
| `Nested Transaction Unsupported` | 不支持嵌套事务 | 改为单层事务 |
| `Import Foreign Table Not Found` | 外表引用的表不存在 | 检查 MaxCompute 表名 |
| `Cannot Acquire Lock In Time` | 获取锁超时 | 检查长事务占用的锁 |
| `permission denied` | 权限不足 | GRANT 相应权限 |
| `not-null constraint` | 非空约束违反 | 检查写入数据完整性 |
| `partition constraint` | 分区约束违反 | 数据不匹配目标分区值 |
| `pk violates` | 主键冲突 | 使用 INSERT ON CONFLICT 或去重 |
| `division by zero` | 除零错误 | 添加 NULLIF 保护 |
| `invalid input` | 非法输入/类型错误 | 检查数据类型匹配 |
| `does not exist` | 对象不存在 | 确认 schema、表名、列名 |
| `already exist` | 对象已存在 | 使用 IF NOT EXISTS |
| `Usage Problem` | 用法错误 | 检查 DDL/DML 语法和约束 |
| `Unsupported Feature` | 不支持的功能 | 换用支持的语法或功能 |
| `Babysitter Actor Not Ready` | 内部角色未就绪 | 等待后重试，可能实例启动中 |
| `Actor Not Exist` | Actor 不存在 | 系统级问题，重试或报障 |
| `Actor Invoke Error` | Actor 调用失败 | 系统级问题，重试 |
| `Pangu IO Error` | 存储 IO 错误 | 暂时性错误，重试 |
| `ERPC_ERROR_TIMEOUT` | RPC 超时 | 系统负载高，等待后重试 |
| `ERPC_ERROR_CONNECTION_CLOSED` | RPC 连接关闭 | 网络波动，重试 |
| `Connect Error Channel Empty` | 连接通道为空 | 系统瞬时故障，重试 |
| `Semaphore Timeout` | 信号量超时 | 系统资源争抢，降低并发 |
| `Table Version Mismatch` | 表版本不匹配 | DDL 变更后刷新元数据 |
| `Missing Original Row On Update` | 更新缺少原始行 | 检查 Binlog 表更新逻辑 |
| `Connection Refused` | 连接被拒绝 | 检查实例状态和网络 |
| `Other Internal Errors` | 其他内部错误 | 重试，若持续则报障 |
| `OTHER` | 未归类 | 查看具体 message 分析 |

## 诊断输出模板

```
报错分析汇总：

报错 1：{error_category}
报错次数：{error_count} 次
Warehouse：{warehouse_name}
发生时段：{first_seen} ~ {last_seen}
解决方案：{参考上表}

报错 2：{error_category}
...

总结：
- FAILED Query 总数：N 条（过去7天）
- 主要报错类型 Top 3：
  1. xxx（N 次）
  2. xxx（N 次）
  3. xxx（N 次）
- 建议优先处理报错次数最多的类型
```
