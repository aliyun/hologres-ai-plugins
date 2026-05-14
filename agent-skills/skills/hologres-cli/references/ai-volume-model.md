# Hologres CLI — AI / Volume / Model Commands

AI content generation, OSS volume management, and model registry commands.

## ai

AI commands (text generation, etc.).

### ai gen

Generate text using Hologres AI function `ai_gen()`.

```bash
# Use server default model
hologres ai gen "介绍下 hologres"

# Specify a model
hologres ai gen "写一首关于数据库的诗" --model qwen-max
hologres ai gen "hello" -m qwen-plus
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PROMPT` | The text prompt to send to the AI function (required) |

**Options:**

| Option | Description |
|--------|-------------|
| `--model, -m` | AI model name (optional, uses server default if not specified) |

**Output (JSON, no model specified):**
```json
{
  "ok": true,
  "data": {
    "text": "Hologres 是一款实时数仓..."
  }
}
```

**Output (JSON, with --model):**
```json
{
  "ok": true,
  "data": {
    "text": "Hologres 是一款实时数仓...",
    "model": "qwen-max"
  }
}
```

Non-JSON formats (table/csv/jsonl) output the generated text directly.

### ai image-gen

Generate images using Hologres AI function `ai_gen()` with a JSON request body. Images are saved directly to an OSS volume via `to_file()`. A volume must be configured first (see `hologres volume create`).

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

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PROMPT` | The text prompt for image generation (required) |

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

**Output (JSON, success):**
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

When response JSON cannot be parsed or has no `image_oss_paths`, falls back to:
```json
{
  "ok": true,
  "data": {
    "raw_result": "..."
  }
}
```

Non-JSON formats output volume paths, one per line.

### ai t2v

Generate video from text prompt. Video generation is asynchronous and typically takes 1-5 minutes.

```bash
hologres ai t2v "一只猫在草地上奔跑" -o volume://my_vol/output
hologres ai t2v "日落" --resolution 720P --ratio 9:16 --duration 10 -o volume://my_vol/output
hologres ai t2v "一只猫" --model happyhorse-2.0-t2v -o volume://my_vol/output
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PROMPT` | Text prompt for video generation (required) |

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

### ai i2v

Generate video from a first-frame image.

```bash
hologres ai i2v "一只猫在奔跑" --img-url volume://my_vol/frame.png -o volume://my_vol/output
hologres ai i2v "猫" --img-url oss://bucket/frame.png --resolution 720P -o volume://my_vol/output

# With local file (requires --upload-volume)
hologres ai i2v "猫" --img-url ./frame.png --upload-volume my_vol -o volume://my_vol/output
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PROMPT` | Text prompt for video generation (required) |

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

### ai r2v

Generate video from reference images. Prompt can embed `oss://` paths to reference materials.

```bash
hologres ai r2v "女性在花园漫步" --reference-url volume://my_vol/girl.png -o volume://my_vol/output
hologres ai r2v "人物oss://b/girl.png在跑步" \
  --reference-url oss://b/girl.png --reference-url volume://my_vol/fan.png \
  -o volume://my_vol/output

# With local file (requires --upload-volume)
hologres ai r2v "女性在花园漫步" --reference-url ./girl.png --upload-volume my_vol -o volume://my_vol/output
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PROMPT` | Text prompt (required). Can embed `oss://` paths or index references (e.g. `图片1`) |

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

### ai video-edit

Edit video with text instructions. Supports style transfer, local replacement, etc.

```bash
hologres ai video-edit "转为动漫风格" --video volume://my_vol/input.mp4 -o volume://my_vol/output
hologres ai video-edit "让人物骑马" --video oss://b/train.mp4 \
  --reference-url volume://my_vol/char.png -o volume://my_vol/output

# With local files (requires --upload-volume)
hologres ai video-edit "转为动漫风格" --video ./input.mp4 --upload-volume my_vol -o volume://my_vol/output
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `PROMPT` | Text instructions for video editing (required) |

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

**Video Generation Output (all 4 subcommands):**
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

## volume

Manage local volume configurations for OSS file storage. Volumes are stored in `~/.hologres/config.json` under the current profile, not on the Hologres server. File operations (list-files, delete-file, download-file, upload-file) use OSS SDK with access-key/access-secret.

### volume create

Create a volume configuration in the current profile. Before saving, creates an OSS directory placeholder at the root path. If the OSS operation fails, the configuration is not saved.

```bash
hologres volume create my_vol \
  --endpoint oss-cn-hangzhou-internal.aliyuncs.com \
  --root oss://bucket/path/ \
  --rolearn acs:ram::123456:role/AliyunHologresDefaultRole \
  --access-key LTAI5tXxx --access-secret xxxx
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `VOLUME_NAME` | Volume name (required). Must start with a letter, only letters/digits/underscores, max 64 chars |

**Options:**

| Option | Description |
|--------|-------------|
| `--type` | Volume type (default: `oss`, currently only `oss` supported) |
| `--endpoint` | OSS internal endpoint (required, must contain `-internal`). A public endpoint is auto-generated |
| `--root` | OSS root path, e.g. `oss://bucket/path/` (required, must start with `oss://`) |
| `--rolearn` | RAM role ARN for Hologres service (required) |
| `--access-key` | OSS AccessKey ID for SDK operations (required) |
| `--access-secret` | OSS AccessKey Secret for SDK operations (required) |

**Output:**
```json
{
  "ok": true,
  "data": {
    "volume": "my_vol",
    "created": true
  }
}
```

**Error (duplicate name):**
```json
{
  "ok": false,
  "error": {"code": "ALREADY_EXISTS", "message": "Volume 'my_vol' already exists in profile 'default'."}
}
```

**Error (OSS directory creation failed):**
```json
{
  "ok": false,
  "error": {"code": "OSS_ERROR", "message": "Failed to create OSS directory placeholder: ..."}
}
```

### volume list

List all volumes in the current profile.

```bash
hologres volume list
hologres -f table volume list
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"name": "my_vol", "type": "oss", "endpoint": "oss-cn-hangzhou-internal.aliyuncs.com", "root": "oss://bucket/path/"}
    ],
    "count": 1
  }
}
```

### volume delete

Delete a volume from the current profile.

```bash
hologres volume delete my_vol
```

**Output:**
```json
{
  "ok": true,
  "data": {
    "volume": "my_vol",
    "deleted": true
  }
}
```

**Error (not found):**
```json
{
  "ok": false,
  "error": {"code": "NOT_FOUND", "message": "Volume 'my_vol' not found in profile 'default'."}
}
```

### volume list-files

List files in a volume via OSS SDK.

```bash
hologres volume list-files --volume my_vol
hologres volume list-files --volume my_vol --prefix data/ --max-count 50
hologres volume list-files --volume my_vol --net intranet
```

**Options:**

| Option | Description |
|--------|-------------|
| `--volume` | Volume name (required) |
| `--prefix` | Filter files by prefix (default: empty) |
| `--max-count` | Max files to list (default: 100) |
| `--net` | Network type: `internet` (default, public endpoint) or `intranet` (internal endpoint) |

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"name": "report.csv", "volume_path": "volume://my_vol/report.csv", "oss_path": "oss://bucket/path/report.csv", "size": 1024, "last_modified": "2026-05-01T18:00:00+08:00"}
    ],
    "count": 1
  }
}
```

### volume delete-file

Delete a file from OSS volume. **Defaults to dry-run for safety.**

```bash
hologres volume delete-file --volume my_vol --file data/report.csv
hologres volume delete-file --volume my_vol --file data/report.csv --confirm
```

**Options:**

| Option | Description |
|--------|-------------|
| `--volume` | Volume name (required) |
| `--file` | File path relative to volume root (required) |
| `--confirm` | Confirm deletion. Without this, only dry-run is shown |
| `--net` | Network type: `internet` (default) or `intranet` |

**Dry-run output:**
```json
{
  "ok": true,
  "data": {
    "action": "DELETE oss://bucket/path/data/report.csv",
    "volume_path": "volume://my_vol/data/report.csv",
    "oss_path": "oss://bucket/path/data/report.csv",
    "dry_run": true
  }
}
```

**Executed output:**
```json
{
  "ok": true,
  "data": {
    "file": "data/report.csv",
    "volume_path": "volume://my_vol/data/report.csv",
    "oss_path": "oss://bucket/path/data/report.csv",
    "deleted": true
  }
}
```

### volume download-file

Download a file from OSS volume to local directory.

```bash
hologres volume download-file --volume my_vol --file report.csv -d ./output
hologres volume download-file --volume my_vol --file data/file.csv -d /tmp --net intranet
```

**Options:**

| Option | Description |
|--------|-------------|
| `--volume` | Volume name (required) |
| `--file` | File path relative to volume root (required) |
| `--download-dir, -d` | Local directory to save file (required, auto-created if missing) |
| `--net` | Network type: `internet` (default) or `intranet` |

**Output:**
```json
{
  "ok": true,
  "data": {
    "file": "report.csv",
    "volume_path": "volume://my_vol/report.csv",
    "oss_path": "oss://bucket/path/report.csv",
    "local_path": "./output/report.csv",
    "downloaded": true
  }
}
```

### volume upload-file

Upload a local file to OSS volume.

```bash
hologres volume upload-file --volume my_vol --local-file ./data.csv --target-file data/data.csv
hologres volume upload-file --volume my_vol --local-file ./img.png --target-file images/img.png --net intranet
```

**Options:**

| Option | Description |
|--------|-------------|
| `--volume` | Volume name (required) |
| `--local-file` | Local file path to upload (required) |
| `--target-file` | Target file path relative to volume root (required) |
| `--net` | Network type: `internet` (default) or `intranet` |

**Output:**
```json
{
  "ok": true,
  "data": {
    "local_file": "./data.csv",
    "target_file": "data/data.csv",
    "volume_path": "volume://my_vol/data/data.csv",
    "oss_path": "oss://bucket/path/data/data.csv",
    "uploaded": true
  }
}
```

**Error (local file not found):**
```json
{
  "ok": false,
  "error": {"code": "FILE_NOT_FOUND", "message": "Local file './nonexistent.csv' not found."}
}
```

### volume view

Download a file from volume to a temp directory and open it with the system default viewer. Supports any file type (images, CSV, PDF, etc.).

```bash
hologres volume view volume://my_vol/images/photo.png
hologres volume view volume://my_vol/data/report.csv --net intranet
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `URI` | Volume file URI in `volume://volume_name/path/to/file` format (required) |

**Options:**

| Option | Description |
|--------|-------------|
| `--net` | Network type: `internet` (default) or `intranet` |

**Output (success):**
```json
{
  "ok": true,
  "data": {
    "file": "images/photo.png",
    "volume_path": "volume://my_vol/images/photo.png",
    "oss_path": "oss://bucket/path/images/photo.png",
    "local_path": "/tmp/hologres_view_xxx/photo.png",
    "opened": true
  }
}
```

**Output (open failed, e.g. headless server):**
```json
{
  "ok": true,
  "data": {
    "file": "images/photo.png",
    "volume_path": "volume://my_vol/images/photo.png",
    "oss_path": "oss://bucket/path/images/photo.png",
    "local_path": "/tmp/hologres_view_xxx/photo.png",
    "opened": false,
    "open_error": "xdg-open: not found"
  }
}
```

**Cross-platform behavior:**
- macOS: uses `open`
- Linux: uses `xdg-open`
- Windows: uses `os.startfile()`

## model

AI model management commands.

### model list

List registered external AI models via `list_external_models()`.

```bash
hologres model list
hologres model list --task embedding
hologres model list --model-type qwen3-vl-embedding
hologres model list --search happy
hologres model list --task video-generation --search happy
hologres -f table model list
```

**Options:**

| Option | Description |
|--------|-------------|
| `--task, -t` | Filter by task type (e.g. `embedding`, `video-generation`). Exact match |
| `--model-type` | Filter by model type (e.g. `qwen3-vl-embedding`). Exact match |
| `--search` | Substring match on `model_name` OR `model_type` (case-insensitive). Combined with `--task` / `--model-type` as AND |

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"model_name": "embed11", "model_type": "qwen3-vl-embedding", "model_provider": "bailian", "task": "embedding"}
    ],
    "count": 1
  }
}
```

**Notes:**
- Filtering is done client-side since `list_external_models()` does not support WHERE clauses
- All filters combine with AND semantics
- `--search` matches when the needle (case-insensitive) appears in either `model_name` or `model_type` (OR across these two fields)

### model catalog

List supported AI model types from the bundled catalog (`models.json`). Reads
the static catalog shipped with the CLI; does **not** require a database
connection. Complementary to `model list`: use `catalog` before registering to
see which model types are supported, and `list` afterwards to see what is
already registered on the instance.

```bash
hologres model catalog
hologres model catalog --task embedding
hologres model catalog --task video-generation
hologres model catalog --search happy
hologres model catalog --task video-generation --search happy
hologres -f table model catalog
```

**Options:**

| Option | Description |
|--------|-------------|
| `--task, -t` | Filter by task type (e.g. `embedding`, `video-generation`, `chat/completions`, `image-generation`, `translation`, `speech-to-text`) |
| `--search` | Substring match on `model_type` (case-insensitive). Combined with `--task` as AND |

**Output:**
```json
{
  "ok": true,
  "data": {
    "rows": [
      {"model_type": "qwen3-max", "model_provider": "bailian", "task": "chat/completions"},
      {"model_type": "qwen-image-2.0", "model_provider": "bailian", "task": "image-generation"}
    ],
    "count": 2
  }
}
```

**Notes:**
- Output columns are `model_type / model_provider / task` — there is no
  `model_name` here because the user-assigned name only exists once a model is
  registered (it is part of `model list`).
- Filtering is done client-side.
- `--search` matches on `model_type` only (substring, case-insensitive). When
  combined with `--task`, both filters apply (AND).
- The catalog is bundled with the CLI; updates ship with new CLI releases.

### model create

Register an external AI model on the live Hologres instance. The user provides
three values: `--name` (the name you will reference in `ai_gen()` / embedding
calls), `--type` (the model type — look up supported values via
`hologres model catalog`), and `--api-key` (the provider API key).

```bash
hologres model create --name my_chat --type qwen3-max --api-key sk-xxx
hologres model create -n my_embed -t text-embedding-v3 --api-key sk-xxx
hologres model create -n my_video -t happyhorse-1.0-t2v --api-key sk-xxx

# Pass extra config (must be valid JSON; default is '{}')
hologres model create -n my_chat -t qwen3-max --api-key sk-xxx --config '{"timeout": 30}'

# Dry-run shows what would be registered without executing
hologres model create -n my_chat -t qwen3-max --api-key sk-xxx --dry-run
```

**Options:**

| Option | Description |
|--------|-------------|
| `--name, -n` | Model name to register (used as the identifier in `ai_gen()` / embedding calls) |
| `--type, -t` | Model type. Look up supported values with `hologres model catalog`. |
| `--api-key` | Provider API key. Never written to `~/.hologres/sql-history.jsonl`. |
| `--config` | Extra JSON config string; default `'{}'` |
| `--dry-run` | Show what would be registered without executing |

**Output (dry-run):**
```json
{
  "ok": true,
  "data": {
    "model_name": "my_chat",
    "model_type": "qwen3-max",
    "dry_run": true
  },
  "message": "Dry-run: model 'my_chat' was NOT registered. Re-run without --dry-run to execute."
}
```

**Output (executed):**
```json
{
  "ok": true,
  "data": {
    "model_name": "my_chat",
    "model_type": "qwen3-max",
    "created": true
  },
  "message": "Model 'my_chat' registered successfully"
}
```

**Errors:**

| Code | Trigger |
|------|---------|
| `INVALID_INPUT` | `--config` is not valid JSON |
| `MODEL_TYPE_NOT_SUPPORTED` | `--type` is not a key returned by `hologres model catalog` |
| `INVALID_ARGS` | Active profile lacks `region_id`, or `region_id` contains characters outside `[a-z0-9-]` |
| `QUERY_ERROR` | Backend rejected the registration (duplicate name, permission, etc.) |

**Notes:**
- `api_key` is never displayed in CLI output, audit logs, or dry-run output.
- Dry-run intentionally does not echo the underlying SQL.

### model delete

Delete a registered external AI model via `delete_external_model()`.

```bash
# Dry-run (default, shows what would be deleted)
hologres model delete embed11

# Actually delete
hologres model delete embed11 --confirm
```

**Options:**

| Option | Description |
|--------|-------------|
| `MODEL_NAME` | Name of the registered model (positional, required) |
| `--confirm` | [REQUIRED to execute] Without this flag, only a dry-run preview is shown |

**Output (dry-run):**
```json
{
  "ok": true,
  "data": {
    "model": "embed11",
    "dry_run": true
  },
  "message": "Dry-run: model 'embed11' was NOT deleted. Re-run with --confirm to execute."
}
```

**Output (executed):**
```json
{
  "ok": true,
  "data": {
    "model": "embed11",
    "deleted": true
  },
  "message": "Model 'embed11' deleted successfully"
}
```

**Notes:**
- `model_name` is restricted to letters, digits, underscore (`_`), hyphen (`-`), and dot (`.`).
- Dry-run output intentionally does not echo the underlying SQL.
- If the model does not exist, the server-side error is propagated as `QUERY_ERROR`.
