---
name: hologres-ad-campaign
description: 通过 Hologres AI Function 生成广告素材并模拟投放效果分析。适用于广告视频生成、素材转视频、虚拟投放模拟及 ROI 分析场景。
version: 2.1.0
---

# Hologres 广告素材生成与投放分析

本 Skill 指导用户通过 Hologres AI Function，使用 hologres-cli 从 OSS 上的原始素材出发，通过全 SQL 链路完成广告视频生成、虚拟投放模拟和实时 ROI 分析。

## 适用场景
当用户提到广告视频生成、宣传视频制作、素材转视频、Hologres AI Function 生成视频、虚拟投放模拟、ROI 分析、投放效果分析、广告素材生成等场景时使用。

## 前提条件

每次使用本 Skill 时，启动 CLI 前必须执行以下两条命令：

```bash
pip install hologres-cli
export HOLOGRES_SKILL=hologres-ad-campaign
```

此外还需满足：
- 已配置 `~/.hologres/config.json`，包含有效的 profile（endpoint、port、database、access_key_id、access_key_secret、region_id、instance_id）
- 已准备好百炼 API Key（用于部署模型）
- Hologres 实例 V3.2+

所有 SQL 均通过 hologres-cli 执行，命令格式如下：
- 查询：`hologres --profile <name> sql run "<SQL>"`
- 写入（DDL/DML）：`hologres --profile <name> sql run --write "<SQL>"`

## 第一步：验证并部署模型

通过 hologres-cli 查询当前实例已部署的模型，如果缺少所需模型则自动部署。

**1.1 查询已部署模型**

```bash
hologres --profile <name> sql run "SELECT model_name, model_type, model_provider, task FROM list_external_models();"
```

**1.2 确认默认模型（用户可自定义）**

| 用途 | 默认模型名 | 模型类型（task） | 可自定义 |
|------|-----------|-----------------|----------|
| 图像生成 | `qwen-image-2.0-pro` | `image-generation` | 是 |
| 文本生成 | `qwen3.6-plus` | `chat/completions` | 是 |
| 视频生成 | `wan2.7-i2v` | `video-generation` | 是 |

如果用户没有指定模型，使用上表默认值；如果用户指定了其他模型，替换对应位置即可。

**1.3 部署缺失模型**

若查询结果中缺少任一模型，使用 SQL 注册模型：

```bash
hologres --profile <name> sql run --write "CALL register_external_model('<model_name>', '<model_type>', 'bailian', '{\"api_key\": \"<bailian_api_key>\"}', '<task>')"
```

注意：`model_name` 不能包含点号（`.`），如有需要用下划线替换（例如 `wan2.7-i2v` 需改为 `wan2_7_i2v`）。

注册后验证：

```bash
hologres --profile <name> model list
```

## 第二步：收集信息

在生成 SQL 之前，向用户收集以下信息（已提供的跳过）。最后需要用户确认所有参数。

### 2.1 模型名称（可选）

默认部署如下模型。如果客户有其他模型需求，可以更换模型名称；若没有指定，默认使用：

- **图像生成模型**：默认 `qwen-image-2.0-pro`
- **文本生成模型**：默认 `qwen3.6-plus`
- **视频生成模型**：默认 `wan2.7-i2v`

### 2.2 产品信息

| 信息项 | 说明 | 示例 |
|--------|------|------|
| 产品名称 | 产品/游戏/服务名称 | "箭塔守汉中" |
| 产品介绍 | 2-3 句话描述 | "一款轻松休闲的策略塔防游戏" |
| 用户动机 | 核心卖点/吸引用户的点 | "策略塔防，拖拽放置防御塔" |
| 视觉风格 | 画面风格描述 | "中国风" |

### 2.3 行业类型

- 游戏 / 电商 / 教育 / 应用 / 其他

### 2.4 OSS 配置

| 信息项 | 说明 | 示例 |
|--------|------|------|
| OSS Bucket | 存储素材的 OSS Bucket | "<your-bucket>" |
| OSS Region | OSS 所在区域内网 Endpoint | "<oss-internal-endpoint>" |
| RAM Role ARN | 访问 OSS 的 RAM 角色 | "<ram-role-arn>" |

### 2.5 素材路径

- 原始素材在 OSS 中的路径，如 `oss://bucket/game/hero1.png`
- 若提供多个素材，可放入数组

### 2.6 生成参数（可选，有默认值）

| 信息项 | 默认值 | 可选范围 |
|--------|--------|----------|
| 风格数量 | 1 种 | 最多 4 种 |
| 视频时长 | 10 秒 | 5 / 10 / 15 / 30 |
| 每个风格生成数量 | 1 个 | — |

**输出目录规范**：生成的图片和视频放在素材路径的同一父级目录下：
- 素材路径：`oss://game/base_images/hero1.png`
- 生成图片输出：`oss://game/generated_images/<style_name>/`
- 生成视频输出：`oss://game/generated_videos/<style_name>/`

### 2.7 用户确认

收集完以上信息后，向用户复述确认：

> 请确认以下参数：
> 1. **模型名称**：图像=`xxx`，文本=`xxx`，视频=`xxx`
> 2. **产品信息**：名称=`xxx`，介绍=`xxx`，动机=`xxx`，风格=`xxx`
> 3. **行业类型**：xxx
> 4. **OSS 配置**：Bucket=`xxx`，Region=`xxx`，RAM Role=`xxx`
> 5. **素材路径**：`xxx`
> 6. **生成参数**：风格数量=x，视频时长=x秒
>
> 确认无误后，我将开始执行完整的广告视频生成链路。

## 第三步：创建业务表并初始化数据

### 3.1 创建 product_info 表

```bash
hologres --profile <name> table create -n product_info \
  -c "name TEXT NOT NULL, intro TEXT, motivation TEXT, art_style TEXT, material_list TEXT[]" \
  --primary-key name --if-not-exists
```

### 3.2 插入产品信息

```bash
hologres --profile <name> sql run --write "
INSERT INTO product_info (name, intro, motivation, art_style, material_list)
VALUES (
    '产品名称',
    '产品介绍',
    '用户动机',
    '视觉风格',
    ARRAY['素材路径1']
)
ON CONFLICT (name) DO UPDATE SET
    intro = EXCLUDED.intro,
    motivation = EXCLUDED.motivation,
    art_style = EXCLUDED.art_style,
    material_list = EXCLUDED.material_list;
"
```

### 3.3 创建 video_style 表

```bash
hologres --profile <name> table create -n video_style \
  -c "name TEXT NOT NULL, prompt TEXT" \
  --primary-key name --if-not-exists
```

### 3.4 根据行业类型插入风格

根据行业类型从模板中随机抽取「风格数量」种风格：

**游戏行业**（4 种可选）：
- 北境枭雄：厚重黑色毛领金属铠甲，冷峻蓝调光线，史诗级电影感
- 云海剑仙：月白色宽袖道袍，水墨山水暗纹，儒雅仙侠气质
- 幽冥夜行：哑光黑色贴身夜行衣，神秘暗影刺客
- 黄金铠甲：华丽黄金铠甲，猩红丝绸斗篷

**电商行业**（4 种可选）：
- 户外使用：户外自然环境，真实光照，产品特写
- 居家场景：温馨居家环境，暖色调，生活气息
- 商务办公：现代化办公环境，简洁专业感
- 运动健身：运动健身场景，活力动感

**教育行业**（4 种可选）：
- 课堂讲授：现代化教室，明亮互动氛围
- 在线学习：温馨书房环境，专注学习氛围
- 实验演示：实验室教学演示，专业科技感
- 户外研学：户外实地教学，自然环境互动

**应用/其他**（4 种可选）：
- 日常使用：日常场景使用应用，现代生活感
- 商务场景：商务办公环境使用，专业高效
- 社交分享：朋友分享应用内容，轻松愉快
- 创意展示：创意内容展示，艺术视觉冲击

```bash
hologres --profile <name> sql run --write "
INSERT INTO video_style VALUES
('风格1名称', '风格1提示词')
ON CONFLICT (name) DO UPDATE SET
    prompt = EXCLUDED.prompt;
"
```

### 3.5 创建 generated_images 表

```bash
hologres --profile <name> table create -n generated_images \
  -c "product_name TEXT, style_name TEXT, style_desc TEXT, material1 TEXT, material2 TEXT" \
  --primary-key "product_name,style_name" --if-not-exists
```

## 第四步：AI 素材生成（CLI 方式）

hologres-cli 提供了专门的 AI 子命令（`hologres ai image-gen` / `hologres ai gen` / `hologres ai i2v` / `hologres ai r2v` / `hologres ai t2v`），相比 SQL `ai_gen` 更稳定、参数更直观。图片和视频生成必须使用 CLI 方式执行。

**前置步骤：创建 OSS Volume**

CLI 的 AI 命令要求输出目录使用 `volume://` 格式，需先创建 volume 配置：

```bash
hologres --profile <name> volume create <volume_name> --type oss \
  --endpoint <oss-internal-endpoint> \
  --root oss://<bucket>/ \
  --rolearn <ram-role-arn> \
  --access-key <your-oss-access-key> \
  --access-secret <your-oss-access-secret>
```

示例：

```bash
hologres --profile <name> volume create <volume_name> --type oss \
  --endpoint <oss-internal-endpoint> \
  --root oss://<bucket>/ \
  --rolearn <ram-role-arn> \
  --access-key <your-oss-access-key> \
  --access-secret <your-oss-access-secret>
```

> **注意**：`--root` 只需指定到 bucket 根目录（如 `oss://bucket/`），不要包含过深的子路径，否则可能因 OSS ACL 权限导致创建失败。

### 4.1 生成主题图片（hologres ai image-gen）

逐个风格执行：

```bash
hologres --profile <name> ai image-gen "<风格提示词>" \
  --reference-url oss://<bucket>/<素材路径> \
  -o volume://<volume_name>/generated_images/<style_name>/ \
  -m <图像模型名> \
  --size "1280*720" \
  -n 1 \
  --watermark false \
  --net intranet
```

示例（云海剑仙风格）：

```bash
hologres --profile <name> ai image-gen "月白色宽袖道袍，水墨山水暗纹，儒雅仙侠气质" \
  --reference-url oss://<bucket>/<素材路径> \
  -o volume://<volume_name>/generated_images/<style_name>/ \
  -m qwen_image_2_0_pro \
  --size "1280*720" \
  -n 1 \
  --watermark false \
  --net intranet
```

执行成功后，CLI 会返回生成图片的 OSS 路径。提取 `oss_path` 保存到 `generated_images` 表：

```bash
hologres --profile <name> sql run --write "
INSERT INTO generated_images (product_name, style_name, style_desc, material1, material2)
VALUES ('产品名称', '风格名称', '风格描述', '生成的图片OSS路径', '原始素材路径')
ON CONFLICT (product_name, style_name) DO UPDATE SET
    style_desc = EXCLUDED.style_desc,
    material1 = EXCLUDED.material1,
    material2 = EXCLUDED.material2;
"
```

**提示**：每个风格单独执行一次。若有 N 个风格，重复上述命令 N 次。

### 4.2 生成分镜脚本（hologres ai gen）

使用文本模型生成分镜脚本：

```bash
hologres --profile <name> ai gen "你的任务是为游戏行业生成一份用于投放广告的5秒视频素材文案。

<产品名称>箭塔守汉中</产品名称>
<产品介绍>一款休闲的策略塔防游戏。</产品介绍>
<用户动机>策略塔防，拖拽放置防御塔</用户动机>
<画面风格>中国风</画面风格>
<图片物料>oss://<bucket>/generated_images/<文件名>.png oss://<bucket>/<素材路径></图片物料>

视频素材结构：
1. 开场2秒：选取一张图片，显示产品名称，展示视觉亮点。
2. 中段1秒：展示1个核心特性/玩法，选取2张图片，描述画面内容和效果。
3. 结尾2秒：所有元素登场，使用行动号召。

要求：围绕用户动机展开，脚本不超过5秒，使用图片全路径。" \
  -m <文本模型名>
```

将生成的脚本保存到 `generated_scripts` 表（或变量中用于下一步视频生成）：

```bash
hologres --profile <name> table create -n generated_scripts \
  -c "product_name TEXT, style_name TEXT, script TEXT, material1 TEXT, material2 TEXT, created_at TIMESTAMP DEFAULT now()" \
  --primary-key "product_name,style_name" --if-not-exists
```

### 4.3 合成广告视频（hologres ai i2v / r2v / t2v）

根据模型类型选择对应的 CLI 命令：

| 模型类型 | CLI 命令 | 关键参数 |
|----------|----------|----------|
| I2V（首帧图生视频） | `hologres ai i2v` | `--img-url <首帧图片>` |
| R2V（参考图生视频） | `hologres ai r2v` | `--reference-urls <url1,url2>` |
| T2V（纯文本生视频） | `hologres ai t2v` | 仅需 prompt |

**I2V 示例（wan2.7-i2v）**：

```bash
hologres --profile <name> ai i2v "<分镜脚本或视频描述>" \
  --img-url oss://<bucket>/generated_images/<图片文件名>.png \
  -o volume://<volume_name>/generated_videos/ \
  -m <视频模型名> \
  --duration <5|10|15> \
  --resolution <720p|1080p> \
  --watermark true \
  --net intranet
```

实际执行示例：

```bash
hologres --profile <name> ai i2v "Chinese martial arts tower defense game advertisement, a hero in white robes standing on a castle tower, dragging and placing defense towers to stop enemy waves, epic cinematic battle scene" \
  --img-url oss://<bucket>/generated_images/<图片文件名>.png \
  -o volume://<volume_name>/generated_videos/ \
  -m wan2_7_i2v \
  --duration 5 \
  --resolution 720p \
  --watermark true \
  --net intranet
```

执行成功后，CLI 返回 JSON 包含：
- `video.oss_path`：视频 OSS 路径
- `video.volume_path`：volume 路径
- `task_status`：SUCCEEDED / FAILED

将结果保存到 `generated_videos` 表：

```bash
hologres --profile <name> sql run --write "
INSERT INTO generated_videos (video_id, product_name, style_name, video_url, script)
VALUES ('vid_xxx', '产品名称', '风格名称', '视频完整URL（含签名）', '脚本内容')
ON CONFLICT (video_id) DO UPDATE SET
    video_url = EXCLUDED.video_url,
    script = EXCLUDED.script,
    created_at = EXCLUDED.created_at;
"
```

**多版本生成**：若用户要求每个风格生成 N 个视频，重复执行上述 CLI 命令 N 次，每次因模型随机性产生不同内容。

**视频 URL 签名**：CLI 返回的视频 URL 是带签名的 OSS 临时链接，展示时必须保持完整参数。

**耗时说明**：`hologres ai i2v` 调用云端视频模型通常需要 1-3 分钟，CLI 会自动维持连接，不会出现 SQL `ai_gen` 的连接超时问题。

## 第六步：虚拟投放模拟

### 6.1 创建渠道配置表

```bash
hologres --profile <name> table create -n channel_config \
  -c "channel TEXT NOT NULL, base_cpm DECIMAL(10,2), base_ctr DECIMAL(5,4), base_cvr DECIMAL(5,4), avg_order_value DECIMAL(10,2)" \
  --primary-key channel --if-not-exists
```

```bash
hologres --profile <name> sql run --write "
INSERT INTO channel_config VALUES
('wechat', 50.00, 0.025, 0.08, 150.00),
('douyin', 80.00, 0.015, 0.05, 200.00),
('xiaohongshu', 60.00, 0.030, 0.06, 180.00),
('bilibili', 40.00, 0.020, 0.04, 120.00)
ON CONFLICT (channel) DO NOTHING;
"
```

### 6.2 创建投放日志表

```bash
hologres --profile <name> table create -n ad_campaign_logs \
  -c "log_id BIGINT NOT NULL, event_time TIMESTAMP, video_id TEXT, style_name TEXT, channel TEXT, event_type TEXT, cost DECIMAL(10,2), revenue DECIMAL(10,2), user_profile JSON" \
  --primary-key log_id --if-not-exists
```

### 6.3 执行虚拟投放模拟

```bash
hologres --profile <name> sql run --write --no-limit-check "
WITH target_videos AS (
    SELECT video_id, style_name 
    FROM generated_videos 
    WHERE video_id = CASE WHEN 'ALL' = 'ALL' THEN video_id ELSE 'ALL' END
),
simulation_params AS (
    SELECT 
        v.video_id,
        v.style_name,
        c.channel,
        c.base_cpm,
        c.base_ctr,
        c.base_cvr,
        c.avg_order_value,
        generate_series(1, 10000) as seq
    FROM target_videos v
    CROSS JOIN channel_config c
),
events AS (
    SELECT 
        floor(random() * 9223372036854775807)::bigint as log_id,
        now() - (random() * interval '7 days') as event_time,
        video_id, style_name, channel,
        'impression' as event_type,
        (base_cpm / 1000.0) as cost,
        0 as revenue,
        json_build_object('age', floor(random()*5+1)) as user_profile
    FROM simulation_params
    
    UNION ALL
    
    SELECT 
        floor(random() * 9223372036854775807)::bigint,
        now() - (random() * interval '7 days'),
        video_id, style_name, channel,
        'click',
        (base_cpm / 1000.0 / base_ctr) as cost,
        0,
        json_build_object('age', floor(random()*5+1))
    FROM simulation_params
    WHERE random() < base_ctr 
    
    UNION ALL
    
    SELECT 
        floor(random() * 9223372036854775807)::bigint,
        now() - (random() * interval '7 days'),
        video_id, style_name, channel,
        'conversion',
        (base_cpm / 1000.0 / base_ctr / base_cvr) as cost,
        avg_order_value as revenue,
        json_build_object('age', floor(random()*5+1))
    FROM simulation_params
    WHERE random() < (base_ctr * base_cvr)
)
INSERT INTO ad_campaign_logs 
SELECT * FROM events
ON CONFLICT (log_id) DO NOTHING;
"
```

## 第七步：实时 ROI 分析

### 7.1 创建 Dynamic Table

```bash
hologres --profile <name> dt create -t dt_campaign_performance \
  --freshness "1 minutes" \
  --refresh-mode incremental \
  --auto-refresh \
  -q "SELECT channel, style_name, COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions, COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks, COUNT(CASE WHEN event_type = 'conversion' THEN 1 END) as conversions, SUM(cost) as total_cost, SUM(revenue) as total_revenue, CASE WHEN SUM(cost) > 0 THEN ROUND(SUM(revenue) / SUM(cost), 2) ELSE 0 END as roi, CASE WHEN COUNT(CASE WHEN event_type = 'impression' THEN 1 END) > 0 THEN ROUND(COUNT(CASE WHEN event_type = 'click' THEN 1 END)::DECIMAL / COUNT(CASE WHEN event_type = 'impression' THEN 1 END), 4) ELSE 0 END as ctr, CASE WHEN COUNT(CASE WHEN event_type = 'click' THEN 1 END) > 0 THEN ROUND(COUNT(CASE WHEN event_type = 'conversion' THEN 1 END)::DECIMAL / COUNT(CASE WHEN event_type = 'click' THEN 1 END), 4) ELSE 0 END as cvr FROM ad_campaign_logs GROUP BY channel, style_name"
```

### 7.2 查询实时指标

```bash
hologres --profile <name> sql run "
SELECT * FROM dt_campaign_performance ORDER BY roi DESC;
"
```

**注意**：Dynamic Table 有最多 1 分钟延迟，如果刚执行完模拟查询结果为空，请稍等 1 分钟后再执行。

### 7.3 获取 AI 分析报告

**方式 A：CLI 方式（推荐，更稳定）**

先查询 ROI 数据，然后传给 `hologres ai gen`：

```bash
# 先导出 ROI 数据
DATA=$(hologres --profile <name> -f json sql run "SELECT channel, style_name, roi, ctr, cvr, total_cost, total_revenue, impressions FROM dt_campaign_performance WHERE total_cost > 0 ORDER BY roi DESC;")

# 生成 AI 分析报告
hologres --profile <name> ai gen "你是一位资深广告投放专家。以下是实时投放数据（JSON格式）：$DATA

请分析：
1. **ROI 冠军**：哪个组合（渠道+风格）的 ROI 最高？具体数值是多少？
2. **潜力股**：哪个组合 CTR 很高但 CVR 偏低？可能原因是什么？
3. **止损建议**：哪个组合 ROI 低于 1.0？建议立即停止还是优化素材？
4. **预算分配**：如果我有 10,000 元额外预算，你会如何分配给各渠道？为什么？

请用 Markdown 格式输出，重点突出数据支撑的结论。" \
  -m <文本模型名>
```

**方式 B：SQL 方式（备选）**

```bash
hologres --profile <name> sql run --no-limit-check "
SELECT 
    ai_gen('文本模型名', 
        json_build_object(
            'prompt', 
            '你是一位资深广告投放专家。以下是实时投放数据：
            ' || json_agg(row_to_json(t)) || '
            请分析 ROI 冠军、潜力股、止损建议和预算分配。',
            'parameters', json_build_object('temperature', 0.7)
        )::text
    ) as analysis_report
FROM (
    SELECT channel, style_name, roi, ctr, cvr, total_cost, total_revenue, impressions
    FROM dt_campaign_performance 
    WHERE total_cost > 0
    ORDER BY roi DESC
) t;
"
```

## 执行流程汇总

```
0. 启动前置：pip install hologres-cli && export HOLOGRES_SKILL=hologres-ad-campaign
1. 验证并部署模型（hologres model list / SQL register_external_model）
2. 收集信息并向用户确认所有参数
3. 创建 OSS volume（hologres volume create）
4. 创建 product_info / video_style / generated_images 等业务表并初始化数据
5. 逐个风格生成主题图片（hologres ai image-gen）
6. 生成分镜脚本（hologres ai gen）
7. 逐个风格合成广告视频（hologres ai i2v / r2v / t2v）
8. 保存图片/视频/脚本结果到对应业务表
9. 创建 channel_config 和 ad_campaign_logs 表
10. 执行虚拟投放模拟（SQL）
11. 创建 Dynamic Table dt_campaign_performance（hologres dt create）
12. 查询 ROI 指标并生成 AI 分析报告（hologres ai gen 或 SQL ai_gen）
```

## 坑点与注意

- **模型名称规范**：`register_external_model()` 的 model_name 参数不能包含点号（`.`），如有需要用下划线替换。
- **CLI vs SQL**：图片/文本/视频生成**必须使用 `hologres ai` CLI 子命令**，不要使用 SQL `ai_gen`。`ai_gen` 对 I2V/R2V 等模型的参数封装不完整，会导致 `Field required: input.media` 等错误。
- **Volume 创建**：`--root` 参数只需指定到 bucket 根目录（`oss://bucket/`），不要包含深层子路径，否则可能因 OSS ACL 权限失败。
- **限流**：`hologres ai` 调用云端模型容易被限流，图片和视频生成必须逐个调用，不能批量执行。
- **to_file 必须使用内网 Endpoint**：SQL 中的 `to_file` 若使用外网 Endpoint 会导致 494 错误；CLI 中通过 `--net intranet` 指定内网。
- **DDL/DML 分离**：hologres-cli 中 SQL 通过 `--write` 标志区分读写，AI 命令（image-gen / gen / i2v 等）不需要 `--write`。
- **URL 签名**：视频 URL 是带签名的 OSS 临时链接，展示时必须保持完整（包含 Expires、OSSAccessKeyId、Signature 参数）。
- **Dynamic Table 延迟**：Dynamic Table 有最多 1 分钟刷新延迟。

## 验证

- `hologres --profile <name> model list` 确认 3 个模型均已注册
- `hologres --profile <name> volume list` 确认 volume 已创建
- `hologres --profile <name> sql run "SELECT * FROM generated_images"` 确认图片已生成
- `hologres --profile <name> sql run "SELECT * FROM generated_videos"` 确认视频已生成
- `hologres --profile <name> sql run "SELECT * FROM dt_campaign_performance ORDER BY roi DESC"` 确认 ROI 数据非空
