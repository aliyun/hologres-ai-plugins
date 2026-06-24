# CPU 诊断 — 报告模板

Stage 3 套用此模板。每个占位符必须用真实查询结果填充，**不得编造**。输出 `query` / `query_id` / `digest` 保留完整内容，不得截断。

```markdown
# Hologres CPU 使用率异常诊断报告

- 实例 ID：{instance_id}
- 诊断时段：{start_time} ~ {end_time}
- 健康评分：{score}/100 | 整体状态：{🔴 持续打满 / 🟠 持续高位 / 🟢 安全平稳}

## 一、今日摘要

> 核心结论：{summary}
> 根因归类：{root_cause}（业务增长 / 大 Query / 锁竞争 / Shard 不均 / Compaction 干扰 / 复合）

- 关键风险：{risks}
- 推荐动作：{actions}

## 二、Q1：宏观定性

| 指标 | 当前窗口 | 同比基线 | 波动 | 是否异常 |
|------|----------|----------|------|----------|
| CPU 均值 | …% | …% | ±…% | … |
| QPS | … | … | ±…% | … |
| RPS | … | … | ±…% | … |
| SQL Latency P99 | … ms | … ms | ±…% | … |

定性结论：{业务增长 / 异常瓶颈 / 拥塞}

## 三、Q2：分布定位

| Worker | Shard 数 | CPU avg | CPU max | 偏差 |
|--------|----------|---------|---------|------|
| worker_0 | … | …% | …% | … |
| worker_1 | … | …% | …% | … |

分布结论：{全局高 / 局部高（Worker N）/ Shard 物理不均}

## 四、Q3：查询归因

### 4.1 Top 10 大 Query（按 CPU 时间）

| QueryID | Duration | CPU(ms) | Warehouse | Plan | SQL 样本 |
|---------|----------|---------|-----------|------|----------|
| … | … | … | … | Fixed/Adaptive | … |

### 4.2 长 Query / 锁源追踪

- 阻塞源 PID：{pid}（用户：{user}）
- 阻塞 SQL：{sql}
- 受阻 Query 数：{n}，最大等待时长：{duration}

## 五、Q4：后台干扰

- Compaction 状态：{正常 / 激增 ×N 倍}
- DDL 变更：{无 / 命中 bitmap_columns 调整 @ {timestamp}}
- 结论：{是否存在写放大干扰}

## 六、治理行动清单

### P0 立即处理
- [ ] {例如：取消阻塞源 PID xxx，释放锁}
- [ ] {例如：终止 Top1 大 Query，避免 CPU 100% 持续}

### P1 近期优化
- [ ] {例如：对 Top SQL 添加分区裁剪或 clustering key}
- [ ] {例如：调整 Compaction 时间窗到业务低峰}

### P2 长期规划
- [ ] {例如：扩容 Warehouse / 拆分读写流量}
- [ ] {例如：建立 CPU 与 Latency 联合告警阈值}
```
