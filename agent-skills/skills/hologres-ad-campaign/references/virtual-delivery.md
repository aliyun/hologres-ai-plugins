# 虚拟投放模拟与 ROI 分析

## 渠道配置

### 创建渠道配置表

```sql
CREATE TABLE IF NOT EXISTS channel_config (
    channel TEXT PRIMARY KEY,
    base_cpm DECIMAL(10,2),
    base_ctr DECIMAL(5,4),
    base_cvr DECIMAL(5,4),
    avg_order_value DECIMAL(10,2)
);
```

### 插入渠道数据

```sql
INSERT INTO channel_config VALUES
('wechat', 50.00, 0.025, 0.08, 150.00),
('douyin', 80.00, 0.015, 0.05, 200.00),
('xiaohongshu', 60.00, 0.030, 0.06, 180.00),
('bilibili', 40.00, 0.020, 0.04, 120.00)
ON CONFLICT (channel) DO NOTHING;
```

**渠道参数说明**：

| 渠道 | CPM(元) | CTR | CVR | 客单价(元) |
|------|---------|-----|-----|------------|
| 微信 | 50 | 2.5% | 8% | 150 |
| 抖音 | 80 | 1.5% | 5% | 200 |
| 小红书 | 60 | 3.0% | 6% | 180 |
| B站 | 40 | 2.0% | 4% | 120 |

## 投放日志表

```sql
CREATE TABLE IF NOT EXISTS ad_campaign_logs (
    log_id BIGINT PRIMARY KEY,
    event_time TIMESTAMP,
    video_id TEXT,
    style_name TEXT,
    channel TEXT,
    event_type TEXT,
    cost DECIMAL(10,2),
    revenue DECIMAL(10,2),
    user_profile JSON
);
```

**event_type 枚举**：`impression`（曝光）、`click`（点击）、`conversion`（转化）

## 执行虚拟投放模拟

参数说明：
- `target_video_id`：`'ALL'` 或具体 video_id
- `simulation_days`：模拟天数（默认 7）
- `volume_multiplier`：流量放大倍数（默认 1）

```sql
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
    -- 生成曝光事件
    SELECT 
        md5(random()::text || now()::text || seq::text)::bigint as log_id,
        now() - (random() * interval '7 days') as event_time,
        video_id, style_name, channel,
        'impression' as event_type,
        (base_cpm / 1000.0) as cost,
        0 as revenue,
        json_build_object('age', floor(random()*5+1)) as user_profile
    FROM simulation_params
    
    UNION ALL
    
    -- 生成点击事件 (基于 CTR)
    SELECT 
        md5(random()::text || now()::text || seq::text || '_c')::bigint,
        now() - (random() * interval '7 days'),
        video_id, style_name, channel,
        'click',
        (base_cpm / 1000.0 / base_ctr) as cost,
        0,
        json_build_object('age', floor(random()*5+1))
    FROM simulation_params
    WHERE random() < base_ctr 
    
    UNION ALL
    
    -- 生成转化事件 (基于 CVR)
    SELECT 
        md5(random()::text || now()::text || seq::text || '_v')::bigint,
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
```

## 实时 ROI 分析

### 创建 Dynamic Table

```sql
CREATE DYNAMIC TABLE IF NOT EXISTS dt_campaign_performance 
WITH (
    auto_refresh_enable = true,
    freshness = '1 minutes',
    refresh_mode = 'incremental'
) 
AS 
SELECT 
    channel,
    style_name,
    COUNT(CASE WHEN event_type = 'impression' THEN 1 END) as impressions,
    COUNT(CASE WHEN event_type = 'click' THEN 1 END) as clicks,
    COUNT(CASE WHEN event_type = 'conversion' THEN 1 END) as conversions,
    SUM(cost) as total_cost,
    SUM(revenue) as total_revenue,
    CASE 
        WHEN SUM(cost) > 0 THEN ROUND(SUM(revenue) / SUM(cost), 2) 
        ELSE 0 
    END as roi,
    CASE 
        WHEN COUNT(CASE WHEN event_type = 'impression' THEN 1 END) > 0 
        THEN ROUND(COUNT(CASE WHEN event_type = 'click' THEN 1 END)::DECIMAL / COUNT(CASE WHEN event_type = 'impression' THEN 1 END), 4) 
        ELSE 0 
    END as ctr,
    CASE 
        WHEN COUNT(CASE WHEN event_type = 'click' THEN 1 END) > 0 
        THEN ROUND(COUNT(CASE WHEN event_type = 'conversion' THEN 1 END)::DECIMAL / COUNT(CASE WHEN event_type = 'click' THEN 1 END), 4) 
        ELSE 0 
    END as cvr
FROM ad_campaign_logs
GROUP BY channel, style_name;
```

### 查询实时指标

```sql
SELECT * FROM dt_campaign_performance ORDER BY roi DESC;
```

**注意**：Dynamic Table 有最多 1 分钟延迟，如果刚执行完模拟查询结果为空，请稍等 1 分钟后再查询。

### 按渠道汇总

```sql
SELECT 
    channel,
    SUM(impressions) as total_impressions,
    SUM(clicks) as total_clicks,
    SUM(conversions) as total_conversions,
    SUM(total_cost) as cost,
    SUM(total_revenue) as revenue,
    CASE WHEN SUM(total_cost) > 0 
         THEN ROUND(SUM(total_revenue)/SUM(total_cost), 2) 
         ELSE 0 END as channel_roi
FROM dt_campaign_performance
GROUP BY channel
ORDER BY channel_roi DESC;
```

### 按风格汇总

```sql
SELECT 
    style_name,
    SUM(impressions) as total_impressions,
    SUM(clicks) as total_clicks,
    SUM(conversions) as total_conversions,
    SUM(total_cost) as cost,
    SUM(total_revenue) as revenue,
    CASE WHEN SUM(total_cost) > 0 
         THEN ROUND(SUM(total_revenue)/SUM(total_cost), 2) 
         ELSE 0 END as style_roi
FROM dt_campaign_performance
GROUP BY style_name
ORDER BY style_roi DESC;
```
