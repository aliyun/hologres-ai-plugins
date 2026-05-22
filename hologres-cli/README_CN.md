# Hologres CLI

面向 AI Agent 的 Hologres 数据库命令行工具，内置安全防护机制，支持结构化 JSON 输出。

## 特性

- **Profile 多环境管理**：通过 `~/.hologres/config.json` 管理多个连接配置，支持交互式配置向导
- **结构化输出**：所有命令默认返回 JSON 格式，便于解析
- **安全防护**：行数限制保护、写操作拦截、危险 SQL 检测
- **多种输出格式**：支持 JSON、表格（table）、CSV、JSONL
- **双连接模式**：JDBC（psycopg）连接优先，JDBC 不可用时自动回退到 OpenAPI `ExecuteStatement` 方式
- **Dynamic Table 管理**：Dynamic Table 全生命周期管理（V3.1+）
- **敏感数据脱敏**：自动对手机号、邮箱、密码等字段进行脱敏
- **审计日志**：所有操作记录到 `~/.hologres/sql-history.jsonl`

## 备注
- schema.py 是老的实现无需继续更新，新的实现迁移到 table.py 中

## 安装

需要 Python 3.11+

```bash
pip install hologres-cli
```

安装指定版本：

```bash
pip install hologres-cli==0.1.0
```

使用 `uv`：

```bash
uv pip install hologres-cli
```

### 开发安装

从源码安装用于本地开发：

```bash
git clone https://github.com/aliyun/hologres-ai-plugins.git
cd hologres-ai-plugins/hologres-cli
pip install -e ".[dev]"
```

## 配置

CLI 使用基于 **Profile** 的配置方式，配置文件存储在 `~/.hologres/config.json`。每个 Profile 包含地域、实例、认证信息、数据库和计算组等连接参数。

### 快速配置

运行交互式配置向导：

```bash
hologres config
```

向导将提示输入：
- **地域**（如 `cn-hangzhou`、`cn-shanghai`）
- **实例 ID**（如 `hgprecn-cn-xxx`）
- **网络类型**：`internet` / `intranet` / `vpc`
- **认证方式**：`basic`（用户名/密码）或 `ram`（AccessKey）
- **数据库名**
- **计算组**（Warehouse）
- **Endpoint**（可选，自动根据 instance_id + region_id + nettype 构建）
- **端口**（默认：`80`）

### Endpoint 自动构建

如果未指定自定义 Endpoint，将根据 `nettype` 自动构建：

| nettype | Host 模式 |
|---------|-----------|
| internet | `{instance_id}-{region_id}.hologres.aliyuncs.com` |
| intranet | `{instance_id}-{region_id}-internal.hologres.aliyuncs.com` |
| vpc | `{instance_id}-{region_id}-vpc-st.hologres.aliyuncs.com` |

### Profile 管理

```bash
hologres config                       # 交互式配置向导
hologres config list                   # 列出所有 Profile
hologres config show                   # 查看当前 Profile 详情
hologres config current                # 查看当前 Profile 名称
hologres config switch <name>          # 切换当前 Profile
hologres config set <key> <value>      # 设置配置项
hologres config get <key>              # 获取配置项
hologres config delete <name> --confirm  # 删除 Profile
```

### Profile 解析优先级

1. **命令行参数**：`hologres --profile <name> status`
2. **当前 Profile**：通过 `config switch` 设置的活跃 Profile
3. **报错提示**：引导运行 `hologres config`

### 配置文件结构

```json
{
  "current": "default",
  "profiles": [
    {
      "name": "default",
      "region_id": "cn-hangzhou",
      "instance_id": "hgprecn-cn-xxx",
      "nettype": "internet",
      "auth_mode": "basic",
      "username": "BASIC$myuser",
      "password": "mypassword",
      "database": "mydb",
      "warehouse": "default_warehouse",
      "endpoint": "",
      "port": 80,
      "output_format": "json",
      "language": "zh",
      "connection_mode": "auto"
    }
  ]
}
```

### 连接模式

`connection_mode` 字段控制 CLI 如何连接 Hologres：

| 模式 | 说明 |
|------|------|
| `auto`（默认） | 优先尝试 JDBC（PostgreSQL 协议），如果连接失败则自动回退到 OpenAPI `ExecuteStatement` |
| `jdbc` | 仅使用 JDBC，经典懒连接模式，无回退 |
| `api` | 仅使用 OpenAPI `ExecuteStatement`，不尝试 JDBC |

```bash
# 切换到 API 模式
hologres config set connection_mode api

# 切换回自动模式（JDBC + 回退）
hologres config set connection_mode auto
```

**API 模式前置条件：**
- Profile 必须使用 RAM 认证（`auth_mode: ram`），配置 `access_key_id` + `access_key_secret`
- Profile 必须配置 `instance_id` 和 `region_id`
- 实例必须已开启 `ExecuteStatement`（参见下方实例管理命令）
- RAM 账号必须有 `hologram:ExecuteStatement` 权限

> **何时使用 API 模式：** 当 PostgreSQL 端口（80/443）被防火墙拦截、跨地域访问、或实例未开启 PostgreSQL 网关时，API 回退非常有用。在 `auto` 模式下这一切自动透明完成。

## 命令

### 连接状态

```bash
hologres status                        # 检查连接状态和版本
hologres --profile prod status         # 指定 Profile 检查
```

### 实例信息

```bash
hologres instance <instance_name>
```

### 计算组（Warehouse）

```bash
hologres warehouse                    # 列出所有计算组
hologres warehouse <warehouse_name>   # 查询指定计算组
```

### Schema 查看

```bash
hologres schema tables                      # 列出所有表
hologres schema describe <table_name>       # 查看表结构
hologres schema dump <schema.table>         # 导出 DDL
hologres schema size <schema.table>         # 查看表存储大小
```

### 表管理

```bash
# 列出所有表
hologres table list

# 列出指定 Schema 下的表
hologres table list --schema public
hologres table list -s myschema

# 创建表（兼容 CALL set_table_property 语法）
hologres table create --name public.orders \
  --columns "order_id BIGINT NOT NULL, user_id INT, amount DECIMAL(10,2), created_at TIMESTAMPTZ" \
  --primary-key order_id --orientation column \
  --distribution-key order_id --clustering-key "created_at:asc" \
  --ttl 7776000 --dry-run

# 创建物理分区表
hologres table create --name public.events \
  --columns "event_id BIGINT NOT NULL, ds TEXT NOT NULL, payload JSONB" \
  --primary-key "event_id,ds" --partition-by ds \
  --orientation column --dry-run

# 创建逻辑分区表（V3.1+，使用 WITH 语法）
hologres table create --name public.logs \
  --columns "a TEXT, b INT, ds DATE NOT NULL" \
  --primary-key "b,ds" --partition-by ds \
  --partition-mode logical --orientation column \
  --distribution-key b \
  --partition-expiration-time "30 day" \
  --partition-keep-hot-window "15 day" \
  --partition-require-filter true \
  --binlog replica --binlog-ttl 86400 --dry-run

# 导出 DDL
hologres table dump <schema.table>

# 查看表结构（列、类型、是否可空、默认值、主键、注释）
hologres table show <table_name>

# 查看表存储大小
hologres table size <schema.table>

# 查看表属性（存储格式、分布键、聚簇键、TTL 等）
hologres table properties <table_name>

# 删除表（默认 dry-run，使用 --confirm 执行）
hologres table drop my_table              # dry-run，展示 SQL
hologres table drop my_table --confirm    # 实际删除
hologres table drop my_table --if-exists --confirm
hologres table drop my_table --cascade --confirm

# 清空表数据（默认 dry-run，使用 --confirm 执行）
hologres table truncate my_table              # dry-run
hologres table truncate my_table --confirm    # 实际清空
```

### 修改表

```bash
# 添加列
hologres table alter my_table --add-column "age INT"

# 添加多列
hologres table alter my_table --add-column "a INT" --add-column "b TEXT"

# 重命名列
hologres table alter my_table --rename-column "old_col:new_col"

# 修改 TTL
hologres table alter my_table --ttl 3600

# 更新字典编码列
hologres table alter my_table --dictionary-encoding-columns "a:on,b:auto"

# 更新 bitmap 索引列
hologres table alter my_table --bitmap-columns "a:on,b:off"

# 修改表 Owner
hologres table alter my_table --owner new_user

# 重命名表
hologres table alter my_table --rename new_table

# 修改逻辑分区表属性
hologres table alter my_table --partition-expiration-time "60 day"
hologres table alter my_table --partition-require-filter true --dry-run
hologres table alter my_table --binlog replica --binlog-ttl 86400

# Dry-run（预览 SQL，不执行）
hologres table alter my_table --ttl 3600 --dry-run

# 多选项组合（包裹在事务中）
hologres table alter my_table --add-column "age INT" --ttl 3600
```

### 视图管理

```bash
# 列出所有视图
hologres view list

# 列出指定 Schema 下的视图
hologres view list --schema public

# 查看视图定义和结构
hologres view show <view_name>
hologres view show analytics.daily_stats
```

### 分区管理

```bash
# 列出逻辑分区表的分区列表
hologres partition list --table my_table
hologres partition list -t public.logs

# 表格格式输出
hologres partition list -t public.logs -f table

# 创建分区（逻辑分区表无需手动创建，INSERT 自动创建）
hologres partition create --table my_table

# 删除分区（默认 dry-run）
hologres partition drop --table my_table --partition "2025-04-01"

# 删除分区（实际执行）
hologres partition drop -t my_table --partition "2025-04-01" --confirm

# 多分区键删除
hologres partition drop -t public.events --partition "yy=2025,mm=04" --confirm

# 修改分区属性（仅逻辑分区表）
hologres partition alter -t my_table --partition "ds=2025-03-16" --set "keep_alive=TRUE" --dry-run
hologres partition alter -t my_table --partition "ds=2025-03-16" --set "keep_alive=TRUE" --set "storage_mode=hot"
```

> **说明：** 目前仅支持逻辑分区表。非逻辑分区表将返回 `NOT_LOGICAL_PARTITION` 错误。
> 逻辑分区表的分区在 INSERT 时自动创建。`partition drop` 删除匹配分区值的所有行。
>
> `partition alter` 可修改的分区属性：
>
> | 属性 | 取值 | 说明 |
> |------|------|------|
> | `keep_alive` | `TRUE` / `FALSE` | 分区是否免于自动清理 |
> | `storage_mode` | `hot` / `cold` | 强制分区存储类型 |
> | `generate_binlog` | `on` / `off` | 分区是否生成 binlog |

### 扩展管理

```bash
# 列出已安装扩展
hologres extension list

# 创建（安装）扩展
hologres extension create roaring_bitmap

# 使用 IF NOT EXISTS
hologres extension create postgis --if-not-exists
```

### GUC 参数管理

```bash
# 查看 GUC 参数当前值
hologres guc show optimizer_join_order

# 设置 GUC 参数（数据库级别，持久化）
hologres guc set optimizer_join_order query
hologres guc set statement_timeout '5min'
```

> **说明：** `guc set` 使用 `ALTER DATABASE` 在数据库级别设置参数，对所有新连接生效。

### SQL 执行

```bash
# 只读查询（超过 100 行需要 LIMIT）
hologres sql run "SELECT * FROM users LIMIT 10"

# 输出中包含列 Schema 信息
hologres sql run --with-schema "SELECT * FROM users LIMIT 10"

# 禁用行数限制检查
hologres sql run --no-limit-check "SELECT * FROM large_table"
```

> **说明：** 写操作（INSERT、UPDATE、DELETE、DROP、CREATE、ALTER、TRUNCATE 等）默认被拦截。

### SQL 执行计划

```bash
hologres sql explain "SELECT * FROM orders WHERE status = 'active'"
```

### 数据导入/导出

```bash
# 导出表到 CSV
hologres data export my_table -f output.csv

# 自定义查询导出
hologres data export -q "SELECT * FROM users WHERE active=true" -f users.csv

# 自定义分隔符
hologres data export my_table -f output.csv --delimiter '|'

# 从 CSV 导入
hologres data import my_table -f input.csv

# 导入前清空表
hologres data import my_table -f input.csv --truncate

# 统计行数
hologres data count my_table
hologres data count my_table --where "status='active'"
```

### Dynamic Table（V3.1+）

使用 V3.1+ 新语法进行 Dynamic Table 全生命周期管理。

#### 创建

```bash
# 最小化创建
hologres dt create -t my_dt --freshness "10 minutes" \
  -q "SELECT col1, SUM(col2) FROM src GROUP BY col1"

# 带分区和 Serverless 计算
hologres dt create -t ads_report --freshness "5 minutes" --refresh-mode auto \
  --logical-partition-key ds --partition-active-time "2 days" \
  --computing-resource serverless --serverless-cores 32 \
  -q "SELECT repo_name, COUNT(*) AS events, ds FROM src GROUP BY repo_name, ds"

# Dry-run 预览 SQL
hologres dt create -t my_dt --freshness "10 minutes" -q "SELECT 1" --dry-run
```

关键选项：`--refresh-mode`（auto/full/incremental）、`--auto-refresh/--no-auto-refresh`、`--cdc-format`（stream/binlog）、`--computing-resource`（local/serverless/warehouse）、`--orientation`、`--distribution-key`、`--clustering-key`、`--ttl` 等。使用 `hologres dt create --help` 查看完整选项。

#### 列表与详情

```bash
hologres dt list                    # 列出所有 Dynamic Table
hologres dt show public.my_dt       # 查看属性
hologres dt list -f table           # 表格格式
```

#### DDL

```bash
hologres dt ddl public.my_dt        # 查看建表语句
```

#### 血缘关系

```bash
hologres dt lineage public.my_dt    # 查看单表血缘
hologres dt lineage --all           # 查看所有 Dynamic Table 血缘
hologres dt lineage my_dt -f table  # 表格格式
```

#### 存储与状态

```bash
hologres dt storage public.my_dt      # 查看存储明细
hologres dt state-size public.my_dt   # 查看状态表大小（增量刷新）
```

#### 刷新

```bash
hologres dt refresh my_dt                                                    # 触发刷新
hologres dt refresh my_dt --overwrite --partition "ds = '2025-04-01'" --mode full  # 覆盖分区
hologres dt refresh my_dt --dry-run                                          # 预览 SQL
```

#### 修改

```bash
hologres dt alter my_dt --freshness "30 minutes"
hologres dt alter my_dt --no-auto-refresh
hologres dt alter my_dt --refresh-mode full --computing-resource serverless
hologres dt alter my_dt --refresh-guc timezone=GMT-8:00 --dry-run
```

#### 删除

```bash
hologres dt drop my_dt               # 默认 dry-run（安全模式）
hologres dt drop my_dt --confirm     # 实际删除
hologres dt drop my_dt --if-exists --confirm
```

#### 转换（V3.0 → V3.1）

```bash
hologres dt convert my_old_dt          # 转换单表
hologres dt convert --all              # 转换所有 V3.0 表
hologres dt convert my_old_dt --dry-run
```

### 历史与 AI Guide

```bash
hologres history          # 查看最近命令历史
hologres history -n 50    # 查看最近 50 条
hologres ai-guide         # 生成 AI Agent 使用指南
```

### 实例管理

通过 Hologram OpenAPI 管理 Hologres 实例。需要 RAM 认证（`access_key_id` + `access_key_secret`）。

```bash
# 列出所有实例
hologres instance-manage list

# 查看实例详情
hologres instance-manage get
hologres instance-manage get --instance-id hgprecn-cn-xxx

# 停止 / 恢复 / 重启
hologres instance-manage stop
hologres instance-manage resume
hologres instance-manage restart

# 重命名
hologres instance-manage rename --instance-name new-name

# 扩缩容
hologres instance-manage scale --scale-type UPGRADE --cpu 64
```

#### ExecuteStatement API 管理

以下命令控制实例是否开启 OpenAPI `ExecuteStatement` SQL 执行功能。这是 `connection_mode = api` 或 auto 回退的前置条件。

```bash
# 开启 ExecuteStatement（API 模式连接的前置条件）
hologres instance-manage enable-execute-statement
hologres instance-manage enable-execute-statement --instance-id hgprecn-cn-xxx

# 关闭 ExecuteStatement
hologres instance-manage disable-execute-statement

# 查询 ExecuteStatement 是否已开启
hologres instance-manage get-execute-statement-enabled
```

> **说明：** 开启后，拥有 `hologram:ExecuteStatement` 权限的 RAM 账号可以通过 OpenAPI 执行 SQL。这与 CLI 在 `connection_mode` 回退到 `api` 时使用的机制相同。

### AI

```bash
# 使用 Hologres AI 函数生成文本（使用服务端默认模型）
hologres ai gen "介绍下 hologres"

# 指定模型
hologres ai gen "写一首关于数据库的诗" --model qwen-max
hologres ai gen "hello" -m qwen-plus
```

### AI 图片生成

图片由 Hologres AI 函数生成，通过 `to_file()` 直接保存到 OSS Volume。需要先配置 Volume（参见 `hologres volume create`）。

```bash
# 生成图片（保存到 OSS Volume）
hologres ai image-gen "生成一只可爱的猫" -o volume://my_vol/images

# 指定模型
hologres ai image-gen "生成一只猫" --model qwen-image-2.0 -o volume://my_vol/images

# 带选项
hologres ai image-gen "短剧男主" --negative-prompt "低画质" -n 2 --size "1280*720" -o volume://my_vol/output

# 带参考图
hologres ai image-gen "参照人物风格生成Q版" --reference-url volume://my_vol/images/ref.png -o volume://my_vol/output

# 本地文件（需要 --upload-volume）
hologres ai image-gen "参照人物风格生成Q版" --reference-url ./ref.png --upload-volume my_vol -o volume://my_vol/output
```

**选项：**

| 选项 | 说明 |
|------|------|
| `--output-dir, -o` | 输出目录，格式 `volume://volume_name[/sub_path]`（必填） |
| `--model, -m` | AI 模型名称（如 qwen-image-2.0） |
| `--negative-prompt` | 反向提示词，最多 500 字符 |
| `--size` | 输出图片尺寸，如 `1280*720` |
| `-n` | 生成图片数量（1-6） |
| `--reference-url` | 参考图 URL（`volume://`、`oss://` 或本地文件路径），可重复 |
| `--upload-volume` | 上传本地文件所用 Volume 名称 |
| `--net` | 文件上传网络类型：`internet`（默认）/ `intranet` |

### AI 视频生成

视频由 Hologres AI 函数生成并保存到 OSS Volume。视频生成是异步的，通常需要 1-5 分钟。

四个子命令覆盖不同的视频生成场景：

#### t2v — 文生视频

```bash
hologres ai t2v "一只猫在草地上奔跑" -o volume://my_vol/output
hologres ai t2v "日落" --resolution 720P --ratio 9:16 --duration 10 -o volume://my_vol/output
```

#### i2v — 图生视频

```bash
hologres ai i2v "一只猫在草地上奔跑" --img-url volume://my_vol/frame.png -o volume://my_vol/output

# 本地文件
hologres ai i2v "猫" --img-url ./frame.png --upload-volume my_vol -o volume://my_vol/output
```

#### r2v — 参考生视频

```bash
hologres ai r2v "女性在花园漫步" --reference-url volume://my_vol/girl.png -o volume://my_vol/output

# 本地文件
hologres ai r2v "女性在花园漫步" --reference-url ./girl.png --upload-volume my_vol -o volume://my_vol/output
```

#### video-edit — 视频编辑

```bash
hologres ai video-edit "转为动漫风格" --video volume://my_vol/input.mp4 -o volume://my_vol/output

# 本地文件
hologres ai video-edit "转为动漫风格" --video ./input.mp4 --upload-volume my_vol -o volume://my_vol/output
```

### Volume（本地存储配置）

管理 OSS 文件存储的本地 Volume 配置。Volume 保存在当前 Profile 的 `~/.hologres/config.json` 中。

```bash
# 创建 Volume
hologres volume create my_vol \
  --endpoint oss-cn-hangzhou-internal.aliyuncs.com \
  --root oss://bucket/path/ \
  --rolearn acs:ram::123456:role/AliyunHologresDefaultRole \
  --access-key LTAI5tXxx --access-secret xxxx

# 列出所有 Volume
hologres volume list

# 删除 Volume
hologres volume delete my_vol

# 列出 Volume 中的文件
hologres volume list-files --volume my_vol
hologres volume list-files --volume my_vol --prefix data/ --max-count 50

# 删除文件（默认 dry-run）
hologres volume delete-file --volume my_vol --file data/report.csv
hologres volume delete-file --volume my_vol --file data/report.csv --confirm

# 下载文件
hologres volume download-file --volume my_vol --file report.csv -d ./output

# 上传文件
hologres volume upload-file --volume my_vol --local-file ./data.csv --target-file data/data.csv

# 查看文件（下载到临时目录并用系统默认程序打开）
hologres volume view volume://my_vol/images/photo.png

# 使用内网端点（VPC/ECS 环境）
hologres volume list-files --volume my_vol --net intranet
```

### 模型管理

```bash
# 列出已注册的外部 AI 模型
hologres model list

# 按 task 类型过滤
hologres model list --task embedding

# 按 model_type 过滤
hologres model list --model-type qwen3-vl-embedding

# 模糊搜索
hologres model list --search happy

# 表格格式
hologres -f table model list

# 删除模型（默认 dry-run）
hologres model delete embed11               # 仅展示 SQL
hologres model delete embed11 --confirm     # 实际删除
```

#### model catalog

列出 CLI 内置 catalog 中受支持的 AI 模型类型。与 `model list` 不同，`catalog` 不需要数据库连接。

```bash
hologres model catalog
hologres model catalog --task embedding
hologres model catalog --search happy
hologres -f table model catalog
```

#### model create

在 Hologres 实例上注册外部 AI 模型。

```bash
# 最小化（使用当前 Profile 的 region_id）
hologres model create --name my_chat --type qwen3-max --api-key sk-xxx

# Embedding / 视频生成模型同理
hologres model create -n my_embed -t text-embedding-v3 --api-key sk-xxx
hologres model create -n my_video -t happyhorse-1.0-t2v --api-key sk-xxx

# 传入额外配置
hologres model create -n my_chat -t qwen3-max --api-key sk-xxx --config '{"timeout": 30}'

# Dry-run
hologres model create -n my_chat -t qwen3-max --api-key sk-xxx --dry-run
```

## 输出格式

```bash
hologres -f json schema tables    # JSON（默认）
hologres -f table schema tables   # 可读表格
hologres -f csv schema tables     # CSV
hologres -f jsonl schema tables   # JSON Lines
```

### 响应结构

**成功：**
```json
{
  "ok": true,
  "data": {
    "rows": [...],
    "count": 10
  }
}
```

**错误：**
```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "可读的错误信息"
  }
}
```

## 安全特性

### 行数限制保护

没有 `LIMIT` 的查询如果返回超过 100 行，将报 `LIMIT_REQUIRED` 错误。

```bash
# 超过 100 行将失败
hologres sql run "SELECT * FROM large_table"

# 添加 LIMIT
hologres sql run "SELECT * FROM large_table LIMIT 50"

# 或禁用检查（谨慎使用）
hologres sql run --no-limit-check "SELECT * FROM large_table"
```

### 写操作保护

写操作（INSERT、UPDATE、DELETE、DROP、CREATE、ALTER、TRUNCATE、GRANT、REVOKE）需要 `--write` 标志：

```bash
# 将返回 WRITE_GUARD_ERROR
hologres sql run "INSERT INTO logs VALUES (1, 'test')"

# 使用 --write 标志允许写操作
hologres sql run --write "INSERT INTO logs VALUES (1, 'test')"

# 没有 WHERE 子句的 DELETE/UPDATE 即使加了 --write 也会被拦截
hologres sql run --write "DELETE FROM users"
# Error: DANGEROUS_WRITE_BLOCKED

# 有 WHERE 子句的 DELETE/UPDATE 允许执行
hologres sql run --write "DELETE FROM users WHERE id = 1"
```

### 删除安全

`hologres table drop` 和 `hologres table truncate` 默认 dry-run 模式，使用 `--confirm` 实际执行。

`hologres dt drop` 同样默认 dry-run 模式。

## 错误码

| 错误码 | 说明 |
|--------|------|
| `CONNECTION_ERROR` | 连接数据库失败（JDBC 和 API 回退均失败） |
| `QUERY_ERROR` | SQL 执行错误 |
| `LIMIT_REQUIRED` | 查询需要 LIMIT 子句 |
| `WRITE_GUARD_ERROR` | 写操作未使用 `--write` 标志 |
| `DANGEROUS_WRITE_BLOCKED` | DELETE/UPDATE 缺少 WHERE 子句 |
| `WRITE_BLOCKED` | 写操作不允许 |
| `NOT_FOUND` | 表或资源未找到 |
| `INVALID_INPUT` | 无效标识符或输入校验失败 |
| `INVALID_ARGS` | 无效或缺失参数 |
| `NO_CHANGES` | 未指定要修改的属性 |
| `EXPORT_ERROR` | 数据导出失败 |
| `IMPORT_ERROR` | 数据导入失败 |
| `VIEW_NOT_FOUND` | 视图未找到 |
| `NOT_LOGICAL_PARTITION` | 表不是逻辑分区表 |
| `INVALID_PARTITION_PROPERTY` | 无效的分区属性名或值 |
| `OSS_ERROR` | OSS 操作失败 |
| `MODEL_TYPE_NOT_SUPPORTED` | `model create --type` 在内置 catalog 中不存在 |
| `INTERNAL_ERROR` | 内部错误 |

## 敏感数据脱敏

CLI 根据列名自动对敏感字段进行脱敏：

| 匹配模式 | 脱敏效果 |
|----------|----------|
| phone, mobile, tel | `138****5678` |
| email | `j***@example.com` |
| password, secret, token | `********` |
| id_card, ssn | `110***********1234` |
| bank_card, credit_card | `***************0123` |

禁用脱敏：

```bash
hologres sql run --no-mask "SELECT * FROM users LIMIT 10"
```

## 测试

```bash
# 单元测试（无需数据库连接）
pytest tests/ --ignore=tests/integration

# 运行特定测试文件
pytest tests/test_commands/test_dt.py                # Dynamic Table 命令测试
pytest tests/test_commands/test_config.py            # Config 命令测试
pytest tests/test_config_store.py                    # Config Store 单元测试

# 带覆盖率
pytest --cov=src/hologres_cli --cov-report=term-missing

# 集成测试（需要已配置的 Profile）
export TEST_PROFILE_NAME="default"
pytest -m integration
```

集成测试（位于 `tests/integration/`）需要已配置的 Profile，默认跳过。

## 许可证

MIT
