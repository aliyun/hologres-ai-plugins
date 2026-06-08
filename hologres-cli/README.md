# Hologres CLI

AI-agent-friendly command-line interface for Hologres database with safety guardrails and structured JSON output.

## Features

- **Profile-Based Configuration**: Multi-profile management via `~/.hologres/config.json`, interactive wizard setup
- **Structured Output**: All commands return JSON by default for easy parsing
- **Safety Guardrails**: Row limits, write protection, dangerous operation blocking
- **Multiple Formats**: JSON, table, CSV, JSONL output formats
- **Dual Connection Mode**: JDBC (psycopg) with automatic OpenAPI `ExecuteStatement` fallback
- **Dynamic Table Management**: Full lifecycle management for Dynamic Tables (V3.1+)
- **Sensitive Data Masking**: Auto-masks phone, email, password fields
- **Audit Logging**: All operations logged to `~/.hologres/sql-history.jsonl`

## Notes
- schema.py是老的实现无需继续更新，新的实现迁移到 table.py 中

## Installation

Requires Python 3.11+

```bash
pip install hologres-cli
```

Or install a specific version:

```bash
pip install hologres-cli==0.1.0
```

Using `uv`:

```bash
uv pip install hologres-cli
```

### Development Installation

For local development from source:

```bash
git clone https://github.com/aliyun/hologres-ai-plugins.git
cd hologres-ai-plugins/hologres-cli
pip install -e ".[dev]"
```

## Configuration

The CLI uses a **profile-based** configuration stored in `~/.hologres/config.json`. Each profile contains connection parameters including region, instance, auth credentials, database, and warehouse.

### Quick Setup

Run the interactive configuration wizard:

```bash
hologres config
```

The wizard will prompt for:
- **Region** (e.g., `cn-hangzhou`, `cn-shanghai`)
- **Instance ID** (e.g., `hgprecn-cn-xxx`)
- **Network type**: `internet` / `intranet` / `vpc`
- **Auth mode**: `basic` (username/password) or `ram` (AccessKey)
- **Database name**
- **Warehouse** (computing group)
- **Endpoint** (optional, auto-constructed from instance_id + region_id + nettype)
- **Port** (default: `80`)

### Endpoint Auto-Construction

If no custom endpoint is provided, the host is auto-constructed based on `nettype`:

| nettype | Host pattern |
|---------|-------------|
| internet | `{instance_id}-{region_id}.hologres.aliyuncs.com` |
| intranet | `{instance_id}-{region_id}-internal.hologres.aliyuncs.com` |
| vpc | `{instance_id}-{region_id}-vpc-st.hologres.aliyuncs.com` |

### Profile Management

```bash
hologres config                       # Interactive wizard (create/edit profile)
hologres config list                   # List all profiles
hologres config show                   # Show current profile details
hologres config current                # Show current profile name
hologres config switch <name>          # Switch active profile
hologres config set <key> <value>      # Set a configuration value
hologres config get <key>              # Get a configuration value
hologres config delete <name> --confirm  # Delete a profile
```

### Profile Resolution Priority

1. **CLI flag**: `hologres --profile <name> status`
2. **Current profile**: The active profile set via `config switch`
3. **Error**: Prompted to run `hologres config` if no profile found

### Config File Structure

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

### Connection Mode

The `connection_mode` field controls how the CLI connects to Hologres:

| Mode | Description |
|------|-------------|
| `auto` (default) | Try JDBC (PostgreSQL wire protocol) first; if connection fails, transparently fall back to OpenAPI `ExecuteStatement` |
| `jdbc` | Use JDBC only. Classic lazy-connect behaviour, no fallback |
| `api` | Use OpenAPI `ExecuteStatement` only. No JDBC attempt |

```bash
# Switch to API-only mode
hologres config set connection_mode api

# Switch back to auto (JDBC with fallback)
hologres config set connection_mode auto
```

**API mode prerequisites:**
- Profile must use RAM auth (`auth_mode: ram`) with `access_key_id` + `access_key_secret`
- Profile must have `instance_id` and `region_id` configured
- The instance must have `ExecuteStatement` enabled (see Instance Management commands below)
- The RAM account must have `hologram:ExecuteStatement` permission

> **When to use API mode:** The API fallback is useful when the PostgreSQL port (80/443) is firewalled, when connecting cross-region, or when the instance hasn't enabled the PostgreSQL wire-protocol gateway. In `auto` mode this happens transparently.

## Commands

### Status

```bash
hologres status                        # Check connection and version
hologres --profile prod status         # Check with specific profile
```

### Instance Information

```bash
hologres instance <instance_name>
```

### Warehouse (Computing Group)

```bash
hologres warehouse                    # List all warehouses
hologres warehouse <warehouse_name>   # Query specific warehouse
```

### Schema Inspection

```bash
hologres schema tables                      # List all tables
hologres schema describe <table_name>       # Describe table structure
hologres schema dump <schema.table>         # Export DDL
hologres schema size <schema.table>         # Get table storage size
```

### Table Management

```bash
# List all tables
hologres table list

# List tables in a specific schema
hologres table list --schema public
hologres table list -s myschema

# Create a table (uses compatible syntax with CALL set_table_property)
hologres table create --name public.orders \
  --columns "order_id BIGINT NOT NULL, user_id INT, amount DECIMAL(10,2), created_at TIMESTAMPTZ" \
  --primary-key order_id --orientation column \
  --distribution-key order_id --clustering-key "created_at:asc" \
  --ttl 7776000 --dry-run

# Create a physical partition table
hologres table create --name public.events \
  --columns "event_id BIGINT NOT NULL, ds TEXT NOT NULL, payload JSONB" \
  --primary-key "event_id,ds" --partition-by ds \
  --orientation column --dry-run

# Create a logical partition table (V3.1+, uses WITH syntax)
hologres table create --name public.logs \
  --columns "a TEXT, b INT, ds DATE NOT NULL" \
  --primary-key "b,ds" --partition-by ds \
  --partition-mode logical --orientation column \
  --distribution-key b \
  --partition-expiration-time "30 day" \
  --partition-keep-hot-window "15 day" \
  --partition-require-filter true \
  --binlog replica --binlog-ttl 86400 --dry-run

# Create a logical partition table with two partition keys
hologres table create --name public.events_2pk \
  --columns "a TEXT, b INT, yy TEXT NOT NULL, mm TEXT NOT NULL" \
  --partition-by "yy, mm" --partition-mode logical \
  --orientation column --partition-require-filter true --dry-run

# Export DDL using hg_dump_script()
hologres table dump <schema.table>
hologres table dump public.my_table

# Show table structure (columns, types, nullable, defaults, primary key, comments)
hologres table show <table_name>
hologres table show public.my_table

# Get table storage size
hologres table size <schema.table>
hologres table size public.my_table

# Show table properties (orientation, distribution_key, clustering_key, TTL, etc.)
hologres table properties <table_name>
hologres table properties public.my_table

# Drop a table (dry-run by default, use --confirm to execute)
hologres table drop my_table              # dry-run, shows SQL
hologres table drop my_table --confirm    # actually drops
hologres table drop my_table --if-exists --confirm
hologres table drop my_table --cascade --confirm

# Truncate (empty) a table (dry-run by default, use --confirm to execute)
hologres table truncate my_table              # dry-run, shows SQL
hologres table truncate my_table --confirm    # actually truncates
```

### Alter Table

```bash
# Add a column
hologres table alter my_table --add-column "age INT"

# Add multiple columns
hologres table alter my_table --add-column "a INT" --add-column "b TEXT"

# Rename a column
hologres table alter my_table --rename-column "old_col:new_col"

# Modify TTL
hologres table alter my_table --ttl 3600

# Update dictionary encoding columns
hologres table alter my_table --dictionary-encoding-columns "a:on,b:auto"

# Update bitmap index columns
hologres table alter my_table --bitmap-columns "a:on,b:off"

# Change table owner
hologres table alter my_table --owner new_user

# Rename table
hologres table alter my_table --rename new_table

# Modify logical partition table properties
hologres table alter my_table --partition-expiration-time "60 day"
hologres table alter my_table --partition-require-filter true --dry-run
hologres table alter my_table --binlog replica --binlog-ttl 86400

# Modify multiple logical partition table properties (wrapped in transaction)
hologres table alter my_table --partition-expiration-time "60 day" --partition-keep-hot-window "30 day"

# Dry-run (preview SQL without executing)
hologres table alter my_table --ttl 3600 --dry-run

# Multiple options (wrapped in transaction)
hologres table alter my_table --add-column "age INT" --ttl 3600
```

### View Management

```bash
# List all views
hologres view list

# List views in a specific schema
hologres view list --schema public
hologres view list -s myschema

# Show view definition and structure
hologres view show <view_name>
hologres view show analytics.daily_stats
```

### Partition Management

```bash
# List partitions of a logical partition table
hologres partition list --table my_table
hologres partition list -t public.logs

# With table format output
hologres partition list -t public.logs -f table

# Create a partition (no-op for logical partition tables, returns notice)
hologres partition create --table my_table

# Drop a partition (dry-run by default)
hologres partition drop --table my_table --partition "2025-04-01"

# Drop a partition (actually execute)
hologres partition drop -t my_table --partition "2025-04-01" --confirm

# Drop a partition with multiple partition columns
hologres partition drop -t public.events --partition "yy=2025,mm=04" --confirm

# Alter partition properties (logical partition table only)
hologres partition alter -t my_table --partition "ds=2025-03-16" --set "keep_alive=TRUE" --dry-run
hologres partition alter -t public.events --partition "yy=2025,mm=04" --set "keep_alive=TRUE"
hologres partition alter -t my_table --partition "ds=2025-03-16" --set "keep_alive=TRUE" --set "storage_mode=hot"
```

> **Note:** Currently only logical partition tables are supported. Non-logical partition tables will return a `NOT_LOGICAL_PARTITION` error.
> For logical partition tables, partitions are created automatically on INSERT. The `partition create` command returns a notice.
> The `partition drop` command deletes all rows matching the partition value. The partition disappears automatically after data is removed.
>
> The `partition alter` command modifies properties of a specific partition in a logical partition table. Valid partition properties:
>
> | Property | Values | Description |
> |----------|--------|-------------|
> | `keep_alive` | `TRUE` / `FALSE` | Whether partition is exempt from auto-cleanup |
> | `storage_mode` | `hot` / `cold` | Force partition storage type |
> | `generate_binlog` | `on` / `off` | Whether partition generates binlog |
>
> **partition alter Options:**
>
> | Option | Description |
> |--------|-------------|
> | `--table, -t TABLE` | Table name `[schema.]table_name` (required) |
> | `--partition VALUE` | Partition value, format: `'col=value'` or `'col1=v1,col2=v2'` (required) |
> | `--set KEY=VALUE` | Set partition property. Repeatable. (required) |
> | `--dry-run` | Preview SQL without executing |

### Extension Management

```bash
# List installed extensions
hologres extension list

# Create (install) an extension
hologres extension create roaring_bitmap

# Create with IF NOT EXISTS
hologres extension create postgis --if-not-exists
```

### GUC Parameter Management

```bash
# Show current value of a GUC parameter
hologres guc show optimizer_join_order

# Set a GUC parameter at database level (persistent)
hologres guc set optimizer_join_order query
hologres guc set statement_timeout '5min'
```

> **Note:** `guc set` sets parameters at the database level using `ALTER DATABASE`, which persists across sessions and applies to all new connections.

### SQL Execution

```bash
# Read-only query (LIMIT required for >100 rows)
hologres sql run "SELECT * FROM users LIMIT 10"

# Include column schema in output
hologres sql run --with-schema "SELECT * FROM users LIMIT 10"

# Disable row limit check
hologres sql run --no-limit-check "SELECT * FROM large_table"
```

> **Note:** Write operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, etc.) are blocked for safety.

### SQL Explain

```bash
# Show execution plan
hologres sql explain "SELECT * FROM orders WHERE status = 'active'"
```

### Data Import/Export

```bash
# Export table to CSV
hologres data export my_table -f output.csv

# Export with custom query
hologres data export -q "SELECT * FROM users WHERE active=true" -f users.csv

# Export with custom delimiter
hologres data export my_table -f output.csv --delimiter '|'

# Import CSV to table
hologres data import my_table -f input.csv

# Import with truncate
hologres data import my_table -f input.csv --truncate

# Import with custom delimiter
hologres data import my_table -f input.csv --delimiter '|'

# Count rows
hologres data count my_table
hologres data count my_table --where "status='active'"
```

### Dynamic Table (V3.1+)

Full lifecycle management for Hologres Dynamic Tables using the V3.1+ new syntax.

#### Create

```bash
# Minimal creation
hologres dt create -t my_dt --freshness "10 minutes" \
  -q "SELECT col1, SUM(col2) FROM src GROUP BY col1"

# With partitioning and serverless computing
hologres dt create -t ads_report --freshness "5 minutes" --refresh-mode auto \
  --logical-partition-key ds --partition-active-time "2 days" \
  --partition-time-format YYYY-MM-DD \
  --computing-resource serverless --serverless-cores 32 \
  -q "SELECT repo_name, COUNT(*) AS events, ds FROM src GROUP BY repo_name, ds"

# Dry-run to preview SQL
hologres dt create -t my_dt --freshness "10 minutes" -q "SELECT 1" --dry-run
```

Key options: `--refresh-mode` (auto/full/incremental), `--auto-refresh/--no-auto-refresh`, `--cdc-format` (stream/binlog), `--computing-resource` (local/serverless/warehouse), `--orientation`, `--distribution-key`, `--clustering-key`, `--ttl`, etc. Use `hologres dt create --help` for full details.

#### List & Show

```bash
hologres dt list                    # List all Dynamic Tables
hologres dt show public.my_dt       # Show properties of a Dynamic Table
hologres dt list -f table           # List in table format
```

#### DDL (Table Structure)

```bash
hologres dt ddl public.my_dt        # Show CREATE statement via hg_dump_script()
```

#### Lineage (Blood Lineage)

```bash
hologres dt lineage public.my_dt    # View lineage for a single table
hologres dt lineage --all           # View lineage for all Dynamic Tables
hologres dt lineage my_dt -f table  # Table format output
```

base_table_type mapping: `r` = ordinary table, `v` = view, `m` = materialized view, `f` = foreign table, `d` = Dynamic Table.

#### Storage & State

```bash
hologres dt storage public.my_dt      # View storage size breakdown
hologres dt state-size public.my_dt   # View state table size (incremental refresh)
```

#### Refresh

```bash
hologres dt refresh my_dt                                                    # Trigger refresh
hologres dt refresh my_dt --overwrite --partition "ds = '2025-04-01'" --mode full  # Overwrite partition
hologres dt refresh my_dt --dry-run                                          # Preview SQL
```

#### Alter

```bash
hologres dt alter my_dt --freshness "30 minutes"
hologres dt alter my_dt --no-auto-refresh
hologres dt alter my_dt --refresh-mode full --computing-resource serverless
hologres dt alter my_dt --refresh-guc timezone=GMT-8:00 --dry-run
```

#### Drop

```bash
hologres dt drop my_dt               # Dry-run by default (safety)
hologres dt drop my_dt --confirm     # Actually drop
hologres dt drop my_dt --if-exists --confirm
```

#### Convert (V3.0 → V3.1)

```bash
hologres dt convert my_old_dt          # Convert single table
hologres dt convert --all              # Convert all V3.0 tables
hologres dt convert my_old_dt --dry-run
```

### History & AI Guide

```bash
hologres history          # Show recent command history
hologres history -n 50    # Show last 50 entries
hologres ai-guide         # Generate AI agent guide
```

### Instance Management

Manage Hologres instances via the Hologram OpenAPI. Requires RAM auth (`access_key_id` + `access_key_secret`).

```bash
# List all instances
hologres instance-manage list

# Get instance details
hologres instance-manage get
hologres instance-manage get --instance-id hgprecn-cn-xxx

# Stop / Resume / Restart
hologres instance-manage stop
hologres instance-manage resume
hologres instance-manage restart

# Rename
hologres instance-manage rename --instance-name new-name

# Scale
hologres instance-manage scale --scale-type UPGRADE --cpu 64
```

#### ExecuteStatement API Management

These commands control whether the OpenAPI `ExecuteStatement` SQL execution feature is enabled for the instance. This is required for `connection_mode = api` or the auto-fallback.

```bash
# Enable ExecuteStatement (required for API-mode connections)
hologres instance-manage enable-execute-statement
hologres instance-manage enable-execute-statement --instance-id hgprecn-cn-xxx

# Disable ExecuteStatement
hologres instance-manage disable-execute-statement

# Check if ExecuteStatement is enabled
hologres instance-manage get-execute-statement-enabled
```

> **Note:** Once enabled, RAM accounts with the `hologram:ExecuteStatement` permission can execute SQL through the OpenAPI. This is the same mechanism the CLI uses when `connection_mode` falls back to `api`.

### AI

```bash
# Generate text using Hologres AI function (uses server default model)
hologres ai gen "介绍下 hologres"

# Specify a model
hologres ai gen "写一首关于数据库的诗" --model qwen-max
hologres ai gen "hello" -m qwen-plus
```

**Output (JSON):**
```json
{
  "ok": true,
  "data": {
    "text": "Hologres 是一款..."
  }
}
```

When `--model` is specified, the response also includes `"model": "qwen-max"`.

Non-JSON formats (table/csv/jsonl) output plain text directly.

### AI Image Generation

Images are generated by Hologres AI function and saved directly to an OSS volume via `to_file()`. A volume must be configured first (see `hologres volume create`).

```bash
# Generate an image (save to OSS volume)
hologres ai image-gen "生成一只可爱的猫" -o volume://my_vol/images

# Specify a model
hologres ai image-gen "生成一只猫" --model qwen-image-2.0 -o volume://my_vol/images

# With options
hologres ai image-gen "短剧男主" --negative-prompt "低画质" -n 2 --size "1280*720" -o volume://my_vol/output

# With reference image
hologres ai image-gen "参照人物风格生成Q版" --reference-url volume://my_vol/images/ref.png -o volume://my_vol/output

# Multiple reference images (mixed volume:// and oss://)
hologres ai image-gen "融合两张参考图" --reference-url volume://my_vol/img1.png --reference-url oss://bucket/path/img2.png -o volume://my_vol/output

# With local file (requires --upload-volume)
hologres ai image-gen "参照人物风格生成Q版" --reference-url ./ref.png --upload-volume my_vol -o volume://my_vol/output
```

**Options:**

| Option | Description |
|--------|-------------|
| `--output-dir, -o` | Output directory in `volume://volume_name[/sub_path]` format (required) |
| `--model, -m` | AI model name (e.g. qwen-image-2.0) |
| `--negative-prompt` | Negative prompt, max 500 chars |
| `--size` | Output image size, e.g. `1280*720` |
| `-n` | Number of images to generate (1-6) |
| `--prompt-extend` | Enable/disable prompt rewriting (`true`/`false`) |
| `--watermark` | Add watermark to image (`true`/`false`) |
| `--seed` | Random seed [0, 2147483647] |
| `--reference-url` | Reference image URL (`volume://vol/path`, `oss://path`, or local file path). Repeatable for multiple images |
| `--upload-volume` | Volume name for uploading local files (required when using local file paths) |
| `--net` | Network type for file upload: `internet` (default) / `intranet` |

**Output (JSON):**
```json
{
  "ok": true,
  "data": {
    "images": [
      {
        "oss_path": "oss://bucket/path/images/c58b7714-b147.png",
        "volume_path": "volume://my_vol/images/c58b7714-b147.png"
      }
    ],
    "usage": {"height": 720, "image_count": 1, "width": 1280}
  }
}
```

When `--model` is specified, the response also includes `"model": "qwen-image-2.0"`.

Non-JSON formats output volume paths, one per line.

**Underlying SQL:**
```sql
-- With model
SELECT ai_gen('qwen-image-2.0', '<json_request>', to_file('<volume_root>', '<endpoint>', '<rolearn>'));

-- Without model
SELECT ai_gen('<json_request>', to_file('<volume_root>', '<endpoint>', '<rolearn>'));
```

### AI Video Generation

Videos are generated by Hologres AI function and saved to an OSS volume via `to_file()`. A volume must be configured first (see `hologres volume create`). Video generation is asynchronous and typically takes 1-5 minutes.

Four subcommands cover different video generation scenarios:

#### t2v — Text to Video

```bash
hologres ai t2v "一只猫在草地上奔跑" -o volume://my_vol/output
hologres ai t2v "日落" --resolution 720P --ratio 9:16 --duration 10 -o volume://my_vol/output
hologres ai t2v "一只猫" --model happyhorse-2.0-t2v -o volume://my_vol/output
```

**Options:**

| Option | Description |
|--------|-------------|
| `--output-dir, -o` | Output directory in `volume://volume_name[/sub_path]` format (required) |
| `--model, -m` | AI model name (default: `happyhorse-1.0-t2v`) |
| `--resolution` | Video resolution: `720P` / `1080P` (default: 1080P) |
| `--ratio` | Aspect ratio: `16:9` (default), `9:16`, `1:1`, `4:3`, `3:4` |
| `--duration` | Video duration in seconds, 3-15 (default: 5) |
| `--watermark` | Add watermark: `true` (default) / `false` |
| `--seed` | Random seed [0, 2147483647] |

#### i2v — Image to Video

```bash
hologres ai i2v "一只猫在草地上奔跑" --img-url volume://my_vol/frame.png -o volume://my_vol/output
hologres ai i2v "猫" --img-url oss://bucket/frame.png --resolution 720P -o volume://my_vol/output

# With local file (requires --upload-volume)
hologres ai i2v "猫" --img-url ./frame.png --upload-volume my_vol -o volume://my_vol/output
```

**Options:**

| Option | Description |
|--------|-------------|
| `--img-url` | First-frame image URL: `volume://`, `oss://`, or local file path (required) |
| `--output-dir, -o` | Output directory (required) |
| `--model, -m` | AI model name (default: `happyhorse-1.0-i2v`) |
| `--resolution` | Video resolution: `720P` / `1080P` (default: 1080P) |
| `--duration` | Video duration in seconds, 3-15 (default: 5) |
| `--watermark` | Add watermark: `true` / `false` |
| `--seed` | Random seed [0, 2147483647] |
| `--upload-volume` | Volume name for uploading local files (required when using local file paths) |
| `--net` | Network type for file upload: `internet` (default) / `intranet` |

Note: No `--ratio` option — aspect ratio follows the first-frame image.

#### r2v — Reference to Video

```bash
hologres ai r2v "女性在花园漫步" --reference-url volume://my_vol/girl.png -o volume://my_vol/output
hologres ai r2v "人物oss://b/girl.png在跑步" \
  --reference-url oss://b/girl.png --reference-url volume://my_vol/fan.png \
  -o volume://my_vol/output

# With local file (requires --upload-volume)
hologres ai r2v "女性在花园漫步" --reference-url ./girl.png --upload-volume my_vol -o volume://my_vol/output
```

**Options:**

| Option | Description |
|--------|-------------|
| `--reference-url` | Reference image URL (1-9 images), `volume://`, `oss://`, or local file path. Repeatable. (required) |
| `--output-dir, -o` | Output directory (required) |
| `--model, -m` | AI model name (default: `happyhorse-1.0-r2v`) |
| `--resolution` | Video resolution: `720P` / `1080P` |
| `--ratio` | Aspect ratio: `16:9` (default), `9:16`, `1:1`, `4:3`, `3:4` |
| `--duration` | Video duration in seconds, 3-15 |
| `--watermark` | Add watermark: `true` / `false` |
| `--seed` | Random seed [0, 2147483647] |
| `--upload-volume` | Volume name for uploading local files (required when using local file paths) |
| `--net` | Network type for file upload: `internet` (default) / `intranet` |

Note: Prompt can embed `oss://` paths to reference materials (e.g. `人物oss://bucket/girl.png在跑步`). CLI does not modify prompt content.

#### video-edit — Video Editing

```bash
hologres ai video-edit "转为动漫风格" --video volume://my_vol/input.mp4 -o volume://my_vol/output
hologres ai video-edit "让人物骑马" --video oss://b/train.mp4 \
  --reference-url volume://my_vol/char.png -o volume://my_vol/output

# With local files (requires --upload-volume)
hologres ai video-edit "转为动漫风格" --video ./input.mp4 --upload-volume my_vol -o volume://my_vol/output
```

**Options:**

| Option | Description |
|--------|-------------|
| `--video` | Input video URL: `volume://`, `oss://`, or local file path (required) |
| `--output-dir, -o` | Output directory (required) |
| `--model, -m` | AI model name (default: `happyhorse-1.0-video-edit`) |
| `--reference-url` | Reference image URL (0-5 images), `volume://`, `oss://`, or local file path. Repeatable. |
| `--resolution` | Video resolution: `720P` / `1080P` |
| `--watermark` | Add watermark: `true` / `false` |
| `--seed` | Random seed [0, 2147483647] |
| `--audio-setting` | Audio control: `auto` (default) / `origin` (keep original audio) |
| `--upload-volume` | Volume name for uploading local files (required when using local file paths) |
| `--net` | Network type for file upload: `internet` (default) / `intranet` |

Note: No `--ratio` or `--duration` options for video editing.

**Video Generation Output (JSON):**
```json
{
  "ok": true,
  "data": {
    "video": {
      "oss_path": "oss://bucket/output/xxx.mp4",
      "volume_path": "volume://my_vol/output/xxx.mp4"
    },
    "task_status": "SUCCEEDED",
    "usage": {"duration": 5, "output_video_duration": 5, "video_count": 1},
    "model": "happyhorse-1.0-t2v"
  }
}
```

Non-JSON formats output the volume path directly.

**Underlying SQL:**
```sql
SELECT ai_gen('<model>', '<json_request>'::text, to_file('<volume_root>', '<endpoint>', '<rolearn>'));
```

### Volume (Local Storage Configuration)

Manage local volume configurations for OSS file storage. Volumes are stored in `~/.hologres/config.json` under the current profile. When creating a volume, an OSS directory placeholder is created first; if this fails, the configuration is not saved.

```bash
# Create a volume
hologres volume create my_vol \
  --endpoint oss-cn-hangzhou-internal.aliyuncs.com \
  --root oss://bucket/path/ \
  --rolearn acs:ram::123456:role/AliyunHologresDefaultRole \
  --access-key LTAI5tXxx --access-secret xxxx

# List all volumes
hologres volume list

# Delete a volume
hologres volume delete my_vol

# List files in a volume
hologres volume list-files --volume my_vol
hologres volume list-files --volume my_vol --prefix data/ --max-count 50

# Delete a file from volume (dry-run by default)
hologres volume delete-file --volume my_vol --file data/report.csv
hologres volume delete-file --volume my_vol --file data/report.csv --confirm

# Download a file from volume
hologres volume download-file --volume my_vol --file report.csv -d ./output

# Upload a file to volume
hologres volume upload-file --volume my_vol --local-file ./data.csv --target-file data/data.csv

# View a file (download to temp dir and open with system viewer)
hologres volume view volume://my_vol/images/photo.png

# Use intranet endpoint (for VPC/ECS)
hologres volume list-files --volume my_vol --net intranet
```

**Create Options:**

| Option | Description |
|--------|-------------|
| `--type` | Volume type (default: `oss`, currently only `oss` supported) |
| `--endpoint` | OSS internal endpoint (required, must contain `-internal`). A public endpoint is auto-generated |
| `--root` | OSS root path, e.g. `oss://bucket/path/` (required) |
| `--rolearn` | RAM role ARN for Hologres service (required) |
| `--access-key` | OSS AccessKey ID for SDK operations (required) |
| `--access-secret` | OSS AccessKey Secret for SDK operations (required) |

**File Operation Options (list-files, delete-file, download-file, upload-file):**

| Option | Description |
|--------|-------------|
| `--volume` | Volume name (required) |
| `--net` | Network type: `internet` (default, public endpoint) or `intranet` (internal endpoint) |

**Naming Rules:**
- Must start with a letter
- Only letters, digits, and underscores allowed
- Maximum 64 characters
- Must be unique within the profile

**Output (JSON):**
```json
{
  "ok": true,
  "data": {
    "volume": "my_vol",
    "created": true
  }
}
```

### Model Management

```bash
# List all registered external AI models (queries the live instance)
hologres model list

# Filter by task type
hologres model list --task embedding

# Filter by model type (exact match)
hologres model list --model-type qwen3-vl-embedding

# Substring search on model_name OR model_type (case-insensitive)
hologres model list --search happy

# Combine filters (AND): video-generation models whose name/type contains "happy"
hologres model list --task video-generation --search happy

# Table format
hologres -f table model list

# Delete a registered external AI model (dry-run by default)
hologres model delete embed11               # shows SQL only
hologres model delete embed11 --confirm     # actually deletes
```

**`model list` Options:**

| Option | Description |
|--------|-------------|
| `--task, -t` | Filter by task type (e.g. `embedding`, `video-generation`). Exact match |
| `--model-type` | Filter by model type (e.g. `qwen3-vl-embedding`). Exact match |
| `--search` | Substring match on `model_name` OR `model_type` (case-insensitive). Combined with `--task` / `--model-type` as AND |

**`model delete` Options:**

| Option | Description |
|--------|-------------|
| `MODEL_NAME` | Name of the registered model (positional, required) |
| `--confirm` | [REQUIRED to execute] Without this flag, dry-run is performed (no DB action) |

**Notes:**
- `model_name` is restricted to letters, digits, underscore (`_`), hyphen (`-`), and dot (`.`).
- Dry-run output intentionally does not echo the underlying SQL.

## Output Formats

```bash
hologres -f json schema tables    # JSON (default)
hologres -f table schema tables   # Human-readable table
hologres -f csv schema tables     # CSV
hologres -f jsonl schema tables   # JSON Lines
```

### Response Structure

**Success:**
```json
{
  "ok": true,
  "data": {
    "rows": [...],
    "count": 10
  }
}
```

**Error:**
```json
{
  "ok": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message"
  }
}
```

## Safety Features

### Row Limit Protection

Queries without `LIMIT` that return more than 100 rows will fail with `LIMIT_REQUIRED` error.

```bash
# This will fail if table has >100 rows
hologres sql run "SELECT * FROM large_table"

# Add LIMIT to fix
hologres sql run "SELECT * FROM large_table LIMIT 50"

# Or disable check (use with caution)
hologres sql run --no-limit-check "SELECT * FROM large_table"
```

### Write Protection

Write operations (INSERT, UPDATE, DELETE, DROP, CREATE, ALTER, TRUNCATE, GRANT, REVOKE) require the `--write` flag:

```bash
# This will return WRITE_GUARD_ERROR
hologres sql run "INSERT INTO logs VALUES (1, 'test')"

# Use --write flag to allow write operations
hologres sql run --write "INSERT INTO logs VALUES (1, 'test')"

# DELETE/UPDATE without WHERE clause is blocked even with --write
hologres sql run --write "DELETE FROM users"
# Error: DANGEROUS_WRITE_BLOCKED - DELETE without WHERE clause is blocked

# DELETE/UPDATE with WHERE clause is allowed
hologres sql run --write "DELETE FROM users WHERE id = 1"
```

### Drop Safety

`hologres table drop` and `hologres table truncate` default to dry-run mode. Use `--confirm` to actually execute.

`hologres dt drop` also defaults to dry-run mode. Use `--confirm` to actually execute.

## Error Codes

| Code | Description |
|------|-------------|
| `CONNECTION_ERROR` | Failed to connect to database (JDBC and API fallback both failed) |
| `QUERY_ERROR` | SQL execution error |
| `LIMIT_REQUIRED` | Query needs LIMIT clause |
| `WRITE_GUARD_ERROR` | Write operation attempted without `--write` flag |
| `DANGEROUS_WRITE_BLOCKED` | DELETE/UPDATE without WHERE clause |
| `WRITE_BLOCKED` | Write operation not allowed |
| `NOT_FOUND` | Table or resource not found |
| `INVALID_INPUT` | Invalid identifier or input validation failed |
| `INVALID_ARGS` | Invalid or missing arguments |
| `NO_CHANGES` | No properties specified to alter |
| `EXPORT_ERROR` | Data export failed |
| `IMPORT_ERROR` | Data import failed |
| `VIEW_NOT_FOUND` | View not found |
| `NOT_LOGICAL_PARTITION` | Table is not a logical partition table |
| `INVALID_PARTITION_PROPERTY` | Invalid partition property name or value |
| `OSS_ERROR` | OSS operation failed (e.g. directory placeholder creation on volume create) |
| `NOT_SUPPORTED` | Command is not supported in current CLI version |
| `INTERNAL_ERROR` | Internal failure |

## Sensitive Data Masking

The CLI automatically masks sensitive fields based on column names:

| Pattern | Masking |
|---------|---------|
| phone, mobile, tel | `138****5678` |
| email | `j***@example.com` |
| password, secret, token | `********` |
| id_card, ssn | `110***********1234` |
| bank_card, credit_card | `***************0123` |

Disable with `--no-mask`:

```bash
hologres sql run --no-mask "SELECT * FROM users LIMIT 10"
```

## Testing

```bash
# Unit tests (no database required)
pytest tests/ --ignore=tests/integration

# Run specific test files
pytest tests/test_commands/test_dt.py                # DT command tests
pytest tests/test_commands/test_config.py            # Config command tests
pytest tests/test_config_store.py                    # Config store unit tests

# With coverage
pytest --cov=src/hologres_cli --cov-report=term-missing

# Integration tests (requires configured profile)
export TEST_PROFILE_NAME="default"
pytest -m integration
```

Integration tests (in `tests/integration/`) require a configured profile and are skipped by default.

## License

MIT
