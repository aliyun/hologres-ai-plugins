---
name: hologres-ad-campaign
description: >
  通过 Hologres AI Function 生成广告素材并模拟投放效果分析。当用户提到广告视频生成、宣传视频制作、素材转视频、Hologres AI Function 生成视频、虚拟投放模拟、ROI 分析、投放效果分析、广告素材生成等场景时使用。全 SQL 链路覆盖从素材管理、主题图片生成、分镜脚本、视频合成、虚拟投放到实时 ROI 分析的完整闭环。
---

## Prerequisites

This skill requires **hologres-cli** to be installed first:

```bash
pip install hologres-cli
```

All SQL execution and Dynamic Table operations depend on `hologres-cli` commands (`hologres sql run --write`, `hologres dt create`).

# Hologres 广告素材生成与投放分析

全 SQL 链路：从 OSS 原始素材到广告视频生成、虚拟投放模拟和实时 ROI 分析。

## 核心流程

```
素材准备 → 主题图片 → 分镜脚本 → 视频合成 → 虚拟投放 → 实时ROI → 策略建议
(SQL)     (AI)       (AI)       (AI)       (SQL)      (DT)      (AI)
```

**使用模型**：

| 模型类型 | task 字段 | 用途 | 模型名 |
|----------|-----------|------|--------|
| 图像生成 | `image-generation` | 主题风格图片 | `qwen-image-2_0-pro` |
| 文本生成 | `chat/completions` | 分镜脚本 | `qwen3_5-plus` |
| 视频生成 | `video-generation` | 广告视频 | `wan2_6-r2v-flash` |

**前提条件**：
- Hologres 实例 V3.2+，已部署上述 AI 模型
- OSS Bucket 存储素材，已配置 RAM 角色授权
- 原始素材（产品图、角色图等）已上传到 OSS

## 第一步：验证模型

```sql
SELECT model_name, model_type, model_provider, task FROM list_external_models();
```

确认存在 `image-generation`、`chat/completions`、`video-generation` 三种 task 类型的模型。

## 第二步：收集信息

向用户收集以下信息（已提供的跳过）：

| 信息项 | 说明 | 示例 |
|--------|------|------|
| 产品名称 | 产品/游戏/服务名称 | "箭塔守汉中" |
| 产品介绍 | 2-3 句话描述 | "一款轻松休闲的三国塔防游戏..." |
| 用户动机 | 核心卖点 | "策略塔防" |
| 视觉风格 | 画面风格描述 | "扁平、中国风、简约小人" |
| 行业类型 | 游戏/电商/教育/应用/其他 | 游戏 |
| OSS Bucket | 存储素材的 Bucket | "hologres-dataclaw-oss" |
| OSS Region | 区域 endpoint | "oss-cn-hangzhou-internal.aliyuncs.com" |
| RAM Role ARN | 访问 OSS 的角色 | "acs:ram::role/xxx" |
| 素材路径列表 | OSS 中的素材路径 | `oss://bucket/game/hero1.png` |
| 风格数量 | 生成几种风格（默认1，最多4） | 1 |
| 视频时长 | 秒数（默认10，可选5/10/15/30） | 10 |

**输出目录规范**：
- 素材路径：`oss://game/base_images/hero1.png`
- 生成图片：`oss://game/generated_images/<style_name>/`
- 生成视频：`oss://game/generated_videos/<style_name>/`

## 第三步：生成 SQL 并执行

### 3.1 创建业务物料表

```sql
CREATE TABLE IF NOT EXISTS product_info(
    name TEXT PRIMARY KEY,
    intro TEXT,
    motivation TEXT,
    art_style TEXT,
    material_list TEXT[]
);

INSERT INTO product_info (name, intro, motivation, art_style, material_list)
VALUES ('产品名称', '产品介绍', '用户动机', '视觉风格',
        ARRAY['素材路径1', '素材路径2'])
ON CONFLICT (name) DO UPDATE SET
    intro = EXCLUDED.intro, motivation = EXCLUDED.motivation,
    art_style = EXCLUDED.art_style, material_list = EXCLUDED.material_list;
```

### 3.2 创建风格提示词表

根据行业类型选取风格，详见 [references/style-templates.md](references/style-templates.md)。

```sql
CREATE TABLE IF NOT EXISTS video_style(
    name TEXT PRIMARY KEY,
    prompt TEXT
);

INSERT INTO video_style VALUES
('风格名称', '风格提示词...')
ON CONFLICT (name) DO UPDATE SET prompt = EXCLUDED.prompt;
```

### 3.3 生成主题图片

详细 SQL 见 [references/sql-templates.md](references/sql-templates.md#生成主题图片)。

```sql
-- 每个风格单独执行，不要批量
-- 核心调用：ai_gen('qwen-image-2_0-pro', json_build_object(...))
-- 结果存入 generated_images 表
```

### 3.4 生成分镜脚本 + 合成视频

详细 SQL 见 [references/sql-templates.md](references/sql-templates.md#合成广告视频)。

```sql
-- 分镜 + 视频一次生成（每个风格单独执行）
-- 1. ai_gen('qwen3_5-plus', ...) 生成分镜脚本
-- 2. ai_gen('wan2_6-r2v-flash', ...) 合成视频
-- 视频 URL 在 video_result 的 output.video_url 字段
```

### 3.5 虚拟投放模拟

详细 SQL 见 [references/virtual-delivery.md](references/virtual-delivery.md)。

```sql
-- 1. 创建渠道配置表 channel_config（微信/抖音/小红书/B站）
-- 2. 创建投放日志表 ad_campaign_logs
-- 3. 执行虚拟投放：模拟曝光/点击/转化事件
```

### 3.6 实时 ROI 分析

```sql
-- 创建 Dynamic Table（自动刷新，延迟<1分钟）
CREATE DYNAMIC TABLE IF NOT EXISTS dt_campaign_performance
WITH (auto_refresh_enable = true, freshness = '1 minutes', refresh_mode = 'incremental')
AS SELECT channel, style_name,
    COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
    COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks,
    COUNT(CASE WHEN event_type = 'conversion' THEN 1 END) as conversions,
    SUM(cost) as total_cost, SUM(revenue) as total_revenue,
    CASE WHEN SUM(cost) > 0 THEN ROUND(SUM(revenue)/SUM(cost), 2) ELSE 0 END as roi
FROM ad_campaign_logs GROUP BY channel, style_name;

-- 查询实时指标
SELECT * FROM dt_campaign_performance ORDER BY roi DESC;
```

### 3.7 AI 策略建议

详细 SQL 见 [references/sql-templates.md](references/sql-templates.md#AI分析报告)。

```sql
-- 调用 qwen3_5-plus 分析投放数据，输出：
-- 1. ROI 冠军组合
-- 2. 潜力股分析
-- 3. 止损建议
-- 4. 预算分配建议
```

## 执行指导

**⚠️ 限流警告**：`ai_gen` 调用云端模型容易被限流，图片和视频生成必须逐个调用。

**⚠️ 工具隔离**：DDL 和 DML 不能在同一工具调用中执行，必须分开。

**执行顺序**：
1. `execute_hg_ddl_sql`: CREATE TABLE → `execute_hg_dml_sql`: INSERT
2. 逐个风格生成图片 → 逐个风格合成视频
3. 创建投放表 → 执行虚拟投放
4. 创建 Dynamic Table → 等待1分钟 → 查询指标 → AI分析

## 参考文档

| 文档 | 内容 |
|------|------|
| [sql-templates.md](references/sql-templates.md) | 完整 SQL 模板（图片/视频/分析） |
| [virtual-delivery.md](references/virtual-delivery.md) | 虚拟投放模拟 + ROI 分析 |
| [style-templates.md](references/style-templates.md) | 行业风格提示词模板 |

## 注意事项

1. `ai_gen` 调用云端大模型，生成可能需要较长时间
2. `wan2_6-r2v-flash` 支持 5/10/15/30 秒多镜头视频，可带音频
3. 生成失败时检查：RAM 角色权限、OSS Bucket、模型部署状态
4. 模型名称可能因版本不同略有差异，以 `list_external_models()` 为准
5. 使用 `ON CONFLICT DO UPDATE` 实现幂等插入
6. 视频 URL 是带签名的 OSS 临时链接，展示时保持完整（含 Expires、Signature 参数）
7. Dynamic Table 有最多1分钟延迟，模拟后稍等再查询
