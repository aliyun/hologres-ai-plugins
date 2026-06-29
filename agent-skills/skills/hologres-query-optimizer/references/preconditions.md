# Preconditions（hologres-cli 执行）

本 skill 慢日志 / SQL 经 `hologres sql run` / `hologres sql explain` 执行，GUC 经 `hologres guc` 操作。无需 openapi-mcp / `aliyun` CLI。

## 1. 安装与连接

```bash
pip install hologres-cli
hologres config                  # 配置 region_id / instance_id / database / 认证
hologres status                  # 验证连通
```

- 连接哪个实例 / 数据库由活跃 profile 的 `instance_id` / `database` 决定；换库用 `hologres config set database <db>` 或 `--profile <name>`。
- 默认 JDBC 直连（`connection_mode=auto`）。本 skill 仅用 `EXPLAIN` / `EXPLAIN ANALYZE` / 慢日志查询 / GUC，均走 JDBC 即可。

## 2. 权限

- Hologres 侧：Superuser 或 `pg_read_all_stats`（读取 `hologres.hg_query_log`、相关系统表，并能跑 `EXPLAIN` / `EXPLAIN ANALYZE`）。

快速自检：

```bash
hologres sql run "SELECT current_user, usesuper FROM pg_user WHERE usename = current_user"
```

## 3. SQL Tracking

```bash
export HOLOGRES_SKILL=hologres-query-optimizer
```

所有诊断 SQL 会带上 `application_name = "hologres-cli/hologres-query-optimizer"`。连接层已自动 `SET hg_computing_resource = 'serverless'`，无需手写 `SET ...`。

## 4. GUC 作用域

| 作用域 | SQL 语法 | hologres-cli 等价 |
|--------|----------|-------------------|
| 会话级（单次 SQL 内） | `SET param = value;`（写在 `hologres sql run` 的多语句里） | `hologres sql run --no-limit-check "SET optimizer_join_order = 'query'; <your query>"` |
| 库级（持久，对新连接生效） | `ALTER DATABASE db SET param = value;` | `hologres guc set <param> <value>` |
| 库级重置 | `ALTER DATABASE db RESET param;` | `hologres guc reset <param>` |
| 查看单个 | `SHOW param;` | `hologres guc show <param>` |
| 列出常用 | — | `hologres guc list [--filter <keyword>]` |

完整 GUC 目录见 [guc-parameters.md](guc-parameters.md)。
