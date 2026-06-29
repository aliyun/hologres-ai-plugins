# Preconditions（hologres-cli 执行）

本 skill 所有 SQL 通过 `hologres sql run` 执行，云监控指标通过 `hologres metric query` 执行，实例 / 计算组信息通过 `hologres instance-manage get` / `hologres warehouse` 获取。无需 openapi-mcp / `aliyun` CLI。

## 1. 安装与连接

```bash
pip install hologres-cli         # 云监控需额外依赖：pip install 'hologres-cli[cms]'
hologres config                  # 配置 region_id / instance_id / database / 认证
hologres status                  # 验证连通；连哪个实例/库由当前 profile 决定
```

- 连接哪个实例 / 数据库由活跃 profile（`~/.hologres/config.json`）的 `instance_id` / `database` 决定；用 `hologres --profile <name> ...` 临时切换，或 `hologres config set database <db>` 永久切换。
- 默认 JDBC 直连（`connection_mode=auto`，JDBC 失败回退 OpenAPI ExecuteStatement）。仅当强制 `connection_mode=api` 时才需开启实例 OpenAPI，可用 `hologres instance-manage get-execute-statement-enabled` / `enable-execute-statement`。

## 2. 云监控凭证

```bash
hologres metric config --access-key-id <ak> --access-key-secret <sk>
```

凭证优先级：`hologres metric config` 专用 AK/SK > `hologres config` 通用 AK/SK > 环境变量 `ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET` > SDK 凭证文件 > ECS RAM 角色。STS 模式与 SQL 链路一致复用 STS 解析。

## 3. RAM / PG 权限

- Hologres OpenAPI（实例 / 计算组管理）：`hologram:GetInstance`、`hologram:ListWarehouses`（或 `AliyunHologresReadOnlyAccess`）。
- 实例内：Superuser 或 `pg_read_all_stats`（读取 `hologres.hg_query_log`、`hologres.hg_table_info`、`pg_stat_activity`、`pg_locks` 等）。
- 云监控：`cms:DescribeMetricList` / `cms:DescribeMetricLast`。

快速自检：

```bash
hologres sql run "SELECT current_user, usesuper FROM pg_user WHERE usename = current_user"
```

## 4. SQL Tracking

```bash
export HOLOGRES_SKILL=hologres-daily-report
```

所有诊断 SQL 会带上 `application_name = "hologres-cli/hologres-daily-report"`。连接层已自动 `SET hg_computing_resource = 'serverless'`，无需手写 `SET ...`。

## 5. 指标前缀判定（InstanceType → {prefix}）

云监控指标名 = `{prefix}<metric>`（如 `standard_cpu_usage`）。`hologres metric` **不会**自动加前缀：

```bash
hologres instance-manage get
```

从 `data.Instance.InstanceType` 映射（`{prefix}` 含尾下划线）：

| InstanceType | Prefix |
|--------------|--------|
| Standard | `standard_` |
| Warehouse | `warehouse_` |
| Follower | `follower_` |
| Serverless | `serverless_` |
| Shared | `shared_` |

同时从 `data.Instance.InstanceName` 取实例名（用于报告标题）。部分指标无前缀（如 `storage_usage_percent`），且不存在 `warehouse_storage_usage`，热存储量需用 `warehouse_hot_storage_used` 替代。

## 6. 时间格式

`hologres metric query --start-time / --end-time` 接受 ISO-8601（`2025-05-19T00:00:00`）或 epoch 毫秒。无时区 ISO 串按 UTC 解析；日报基于北京时间，建议显式带 epoch 毫秒或 `+08:00`。元仓 SQL 的 `query_start` 谓词用带时区的 ISO 字符串，且不要套 `to_char(...)`（无法走索引）。
