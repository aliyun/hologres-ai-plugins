# SQL 模板库

## 表结构定义

### product_info - 业务物料表

```sql
CREATE TABLE IF NOT EXISTS product_info(
    name TEXT PRIMARY KEY,
    intro TEXT,
    motivation TEXT,
    art_style TEXT,
    material_list TEXT[]
);
```

### video_style - 风格提示词表

```sql
CREATE TABLE IF NOT EXISTS video_style(
    name TEXT PRIMARY KEY,
    prompt TEXT
);
```

### generated_images - 生成图片结果表

```sql
CREATE TABLE IF NOT EXISTS generated_images(
    product_name TEXT,
    style_name TEXT,
    style_desc TEXT,
    material1 TEXT,
    material2 TEXT,
    PRIMARY KEY (product_name, style_name)
);
```

### prompts - 分镜提示词表

```sql
CREATE TABLE IF NOT EXISTS prompts (
    id BIGINT PRIMARY KEY,
    prompt TEXT
);
```

## 数据插入模板

### 插入产品信息

```sql
INSERT INTO product_info (name, intro, motivation, art_style, material_list)
VALUES (
    '{{产品名称}}',
    '{{产品介绍}}',
    '{{用户动机}}',
    '{{视觉风格}}',
    ARRAY['{{素材路径1}}', '{{素材路径2}}']
)
ON CONFLICT (name) DO UPDATE SET
    intro = EXCLUDED.intro,
    motivation = EXCLUDED.motivation,
    art_style = EXCLUDED.art_style,
    material_list = EXCLUDED.material_list;
```

### 插入风格提示词

```sql
INSERT INTO video_style VALUES
('{{风格名称}}', '{{风格提示词}}')
ON CONFLICT (name) DO UPDATE SET
    prompt = EXCLUDED.prompt;
```

## 生成主题图片

每个风格 **单独执行**，不要批量。

```sql
WITH material_prompt AS (
    SELECT product_info.name AS product_name,
           video_style.name AS style_name,
           material_list[1] AS material1,
           material_list[2] AS material2,
           prompt
    FROM product_info, video_style
    WHERE product_info.name = '{{产品名称}}'
),
gen_image AS (
    SELECT product_name, style_name, prompt AS style_desc,
        ai_gen('qwen-image-2_0-pro', json_build_object(
            'prompt', prompt,
            'reference_urls', array[material1],
            'parameters', json_build_object(
                'size', '1280*720',
                'n', 1,
                'watermark', false
            ),
            'output_dir', 'oss://{{BucketName}}/generated_images/'
        )::text, to_file(material1, '{{OSS Region}}', '{{RAM Role ARN}}')) AS obj1,
        ai_gen('qwen-image-2_0-pro', json_build_object(
            'prompt', prompt,
            'reference_urls', array[material2],
            'parameters', json_build_object(
                'size', '1280*720',
                'n', 1,
                'watermark', false
            ),
            'output_dir', 'oss://{{BucketName}}/generated_images/'
        )::text, to_file(material2, '{{OSS Region}}', '{{RAM Role ARN}}')) AS obj2
    FROM material_prompt
),
image_urls AS (
    SELECT product_name, style_name, style_desc,
           obj1::json->'image_oss_paths' ->> 0 AS material1,
           obj2::json->'image_oss_paths' ->> 0 AS material2
    FROM gen_image
)
INSERT INTO generated_images (product_name, style_name, style_desc, material1, material2)
SELECT product_name, style_name, style_desc, material1, material2
FROM image_urls
ON CONFLICT (product_name, style_name) DO UPDATE SET
    style_desc = EXCLUDED.style_desc,
    material1 = EXCLUDED.material1,
    material2 = EXCLUDED.material2;
```

## 分镜脚本提示词

```sql
INSERT INTO prompts VALUES (10,
'你的任务是为{{行业}}行业生成一份用于投放广告的{{时长}}秒视频素材文案。

<产品名称>{0}</产品名称>
<产品介绍>{1}</产品介绍>
<用户动机>{2}</用户动机>
<画面风格>{3}</画面风格>
<图片物料>{4} {5}</图片物料>

视频素材结构：
1. 开场2秒：选取一张图片，显示产品名称，展示视觉亮点。
2. 中段{{时长-4}}秒：展示1个核心特性/玩法，选取2张图片，描述画面内容和效果。
3. 结尾2秒：所有元素登场，使用行动号召。

要求：围绕用户动机展开，脚本不超过{{时长}}秒，使用图片全路径。')
ON CONFLICT (id) DO UPDATE SET
    prompt = EXCLUDED.prompt;
```

## 合成广告视频

分镜 + 视频一次生成，**每个风格单独执行**。

```sql
WITH product_material AS (
    SELECT * FROM product_info
    LEFT JOIN generated_images ON name = product_name
    WHERE product_name = '{{产品名称}}' AND style_name = '{{选择风格}}'
),
tmp_prompt AS (
    SELECT json_build_object(
        'prompt', prompt,
        'args', json_build_array(
            name, intro, motivation, art_style,
            to_file(material1, '{{OSS Region}}', '{{RAM Role ARN}}'),
            to_file(material2, '{{OSS Region}}', '{{RAM Role ARN}}')
        )
    ) AS prompt, material1, material2
    FROM product_material, prompts WHERE id = 10
),
story_script AS (
    SELECT ai_gen('qwen3_5-plus', prompt::text,
        to_file(material1, '{{OSS Region}}', '{{RAM Role ARN}}')) AS script,
        material1, material2
    FROM tmp_prompt
)
SELECT material1, material2,
    ai_gen('wan2_6-r2v-flash', json_build_object(
        'prompt', script,
        'reference_urls', array[material1, material2],
        'parameters', json_build_object(
            'size', '1280*720',
            'duration', {{时长}},
            'shot_type', 'multi',
            'audio', true,
            'watermark', true
        ),
        'output_dir', 'oss://{{BucketName}}/generated_videos/'
    )::text,
    to_file(material1, '{{OSS Region}}', '{{RAM Role ARN}}')) AS video_result,
    script
FROM story_script;
```

**多版本生成**：每个风格要 N 个视频，重复执行上述 SQL N 次，模型随机性产生不同内容。

**视频 URL 提取**：`video_result` 返回 JSON，视频 URL 位于 `output.video_url` 字段，含签名参数（Expires、OSSAccessKeyId、Signature），展示时保持完整。

## AI 分析报告

```sql
SELECT 
    ai_gen('qwen3_5-plus', 
        json_build_object(
            'prompt', 
            '你是一位资深广告投放专家。以下是某产品不同视频风格在不同渠道的实时投放数据（数据延迟<1分钟）：
            ' || json_agg(row_to_json(t)) || '
            
            请分析：
            1. **ROI 冠军**：哪个组合（渠道+风格）的 ROI 最高？具体数值是多少？
            2. **潜力股**：哪个组合 CTR 很高但 CVR 偏低？可能原因是什么？
            3. **止损建议**：哪个组合 ROI 低于 1.0？建议立即停止还是优化素材？
            4. **预算分配**：如果我有 10,000 元额外预算，你会如何分配给各渠道？为什么？
            
            请用 Markdown 格式输出，重点突出数据支撑的结论。',
            'parameters', json_build_object('temperature', 0.7)
        )::text
    ) as analysis_report
FROM (
    SELECT channel, style_name, roi, ctr, cvr, total_cost, total_revenue, impressions
    FROM dt_campaign_performance 
    WHERE total_cost > 0
    ORDER BY roi DESC
) t;
```
