# Preconditions（hologres-cli 执行）

本 skill 所有 SQL 通过 `hologres sql run` 执行，云监控指标通过 `hologres metric query` / `hologres metric latest` 执行，实例信息通过 `hologres instance-manage get` 获取。无需 openapi-mcp / `aliyun` CLI。

## 1. 安装与连接

```bash
pip install hologres-cli         # 云监控需额外依赖：pip install 'hologres-cli[cms]'
hologres config                  # 交互式向导，配置 region_id / instance_id / database / 认证
hologres status                  # 验证连通；连哪个实例/库由当前 profile 决定
```

- 连接哪个实例 / 数据库由活跃 profile（`~/.hologres/config.json`）的 `instance_id` / `database` 决定；用 `hologres --profile <name> ...` 临时切换，或 `hologres config set database <db>` 永久切换。
- `hologres-cli` 默认 JDBC 直连（`connection_mode=auto`，JDBC 失败时回退 OpenAPI ExecuteStatement）。JDBC 模式下无需开启实例的 OpenAPI ExecuteStatement；仅当强制 `connection_mode=api` 时才需要，可用 `hologres instance-manage get-execute-statement-enabled` 查询、`hologres instance-manage enable-execute-statement` 开启。

## 2. 云监控凭证

```bash
# 推荐：为 metric 命令单独配置 AK/SK（与 Hologres 连接凭证互不影响）
hologres metric config --access-key-id <ak> --access-key-secret <sk>
```

凭证解析优先级：`hologres metric config` 专用 AK/SK > `hologres config` 通用 AK/SK（profile 的 `access_key_id` / `access_key_secret`）> 环境变量 `ALIBABA_CLOUD_ACCESS_KEY_ID/SECRET` > SDK 凭证文件 > ECS RAM 角色。STS 模式（`auth_mode=sts`）下与 SQL 链路一致复用 STS 解析，无需单独 `hologres metric config`。

## 3. RAM / PG 权限

- Hologres 侧：Superuser 或 `pg_read_all_stats`（读取 `hologres.hg_query_log`、`hologres.hg_worker_info`、`pg_stat_activity`、`pg_locks` 等）。
- 云监控侧：账号具备 `cms:DescribeMetricList` / `cms:DescribeMetricLast` 调用权限。

快速自检：

```bash
hologres sql run "SELECT current_user, usesuper FROM pg_user WHERE usename = current_user"
```

## 4. SQL Tracking

```bash
export HOLOGRES_SKILL=hologres-diagnosis-cpu
```

所有诊断 SQL 会带上 `application_name = "hologres-cli/hologres-diagnosis-cpu"`，便于事后审计。连接层已自动 `SET hg_computing_resource = 'serverless'`，无需在 SQL 内手写 `SET ...`。

## 5. 指标前缀判定（InstanceType → {prefix}）

云监控指标名 = `{prefix}<metric>`（如 `warehouse_cpu_usage`）。`hologres metric` **不会**自动加前缀，需先判定实例类型：

```bash
hologres instance-manage get
```

从返回 JSON 的 `data.Instance.InstanceType` 映射：

| InstanceType | Prefix | 示例 |
|--------------|--------|------|
| Warehouse | `warehouse_` | `warehouse_cpu_usage` |
| Standard | `standard_` | `standard_cpu_usage` |
| Follower | `follower_` | `follower_cpu_usage` |
| Serverless | `serverless_` | `serverless_cpu_usage` |
| Shared | `shared_` | `shared_cpu_usage` |

也可用 `hologres metric list --search cpu` 查看实际可用指标名。

## 6. 时间格式

`hologres metric query --start-time / --end-time` 接受 ISO-8601（`2025-05-19T10:00:00`）或 epoch 毫秒。无时区的 ISO 串按 **UTC** 解析；分析北京时间时请显式带 epoch 毫秒，或注意 +08:00 时区换算。元仓 SQL 中的 `query_start` 谓词用 ISO 字符串（如 `'2025-05-19 10:00:00'`），且不要套 `to_char(...)` 等表达式（无法走索引）。
