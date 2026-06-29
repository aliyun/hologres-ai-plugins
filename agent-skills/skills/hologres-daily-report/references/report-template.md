# 日报标准模板

用此模板组装最终报告。每个占位符必须用真实数据填充，**不得编造**。若某节数据源不可用，标注 `数据不可用` 而非留空。`digest` / `query_id` / `query` 保留完整，不得截断。

## 报告标题规则

最终报告 **必须** 使用此标题格式（一级标题）：

```
# {instance_id}({instance_name})_运维日报_{YYYY-MM-DD-HH:mm:ss}
```

- `{instance_id}` —— 如 `hgprecn-cn-xxx`
- `{instance_name}` —— `hologres instance-manage get` 返回的 `data.Instance.InstanceName`
- 时间 —— **报告生成时间**（北京时间 `Asia/Shanghai`），精确到秒，格式 `YYYY-MM-DD-HH:mm:ss`（日期与时间用 `-` 连接）

示例：`# hgprecn-cn-2r42t2fxj001(my-prod-instance)_运维日报_2026-06-10-14:35:02`

## Markdown Body

```markdown
# {instance_id}({instance_name})_运维日报_{generated_at}
- 实例：{instance_name} / {region}
- 日期：{report_date}（{weekday}）
- 报告周期：{start_time} ~ {end_time}（北京时间）
- 健康评分：{score}/100（较昨日 {change}）
- 整体状态：{status} | 需关注：{attention} 项 | 可优化：{optimize} 项

## 一、今日摘要
- 整体状态：{summary}
- 关键风险：{top_risks}
- 关键变化：{important_changes}
- 明日预警：{tomorrow_warning}

## 二、实例整体健康状态（Q1）
### 结论
{health_conclusion}

### 关键事实
- 实例状态：{status}
- 实例版本：{version}，EOS 日期：{eos_date}（{version_status}）
- Worker 节点 CPU：{cpu_facts}
- Locks：{locks_facts}
- 连接数：{conn_facts}
- FE replay 延迟：{fe_replay_facts}
- Shard 多副本同步延迟：{shard_replica_facts}

### 分析
{health_analysis}

### 建议
- {health_suggestion_1}
- {health_suggestion_2}

## 三、可用性与稳定性（Q2）
### 结论
{availability_conclusion}

### 关键事实
- 实例自身：{instance_events}
- 平台运维事件：{ops_events}
- 版本升级：{upgrade_events}
- 控制台配置变更：{config_changes}

### 分析
{availability_analysis}

### 建议
- {availability_suggestion_1}

## 四、计算资源情况（Q3）
### 结论
{resource_conclusion}

### 关键事实
| 维度 | 指标 | 平均值 | P95 | 峰值 | 诊断阈值 | 状态 |
|------|------|--------|-----|------|----------|------|
| CPU | 利用率 | {cpu_avg} | {cpu_p95} | {cpu_peak} | 连续1h > 90% | {status} |
| 内存 | 利用率 | {mem_avg} | {mem_p95} | {mem_peak} | 连续1h > 90% | {status} |
| 连接 | 使用率 | {conn_avg} | {conn_p95} | {conn_peak} | 连续10min > 90% | {status} |
| 查询延迟 | P99 耗时 | {lat_avg} | {lat_p95} | {lat_peak} | 较前日上涨 > 50% | {status} |
| Query Queue | 队列长度/排队时间 | {queue_avg} | {queue_p95} | {queue_peak} | 有排队且 > 500ms | {status} |

### 分析
{resource_analysis}

### 建议
- {resource_suggestion_1}
- {resource_suggestion_2}

## 五、任务与 SQL（Q4）
### 结论
{sql_conclusion}

### 关键事实
- SQL 总数：{sql_total}
- 慢 SQL 数（> 10s）：{slow_sql_count}
- 失败查询数：{failed_sql_count}
- Dynamic Table 刷新状态：{dt_status}

### Top 慢 SQL
| 排名 | 查询摘要 | 耗时 | 执行次数 | 根因诊断 | 优化建议 |
|------|----------|------|----------|----------|----------|
| 1 | {top1_sql} | {top1_time} | {top1_count} | {top1_reason} | {top1_suggest} |
| 2 | {top2_sql} | {top2_time} | {top2_count} | {top2_reason} | {top2_suggest} |
| 3 | {top3_sql} | {top3_time} | {top3_count} | {top3_reason} | {top3_suggest} |

### 失败查询
| 错误类型 | 数量 | 首次出现 | 最后出现 | 建议 |
|----------|------|----------|----------|------|
| {err_type} | {err_count} | {first_seen} | {last_seen} | {err_suggest} |

### 分析
{sql_analysis}

### 建议
- {sql_suggestion_1}
- {sql_suggestion_2}

## 六、成本治理（Q5）
### 结论
{cost_conclusion}

### 关键事实
| 维度 | 当前值 | 昨日 | 环比 | 状态 |
|------|--------|------|------|------|
| 存储使用率 | {storage_now} | {storage_yesterday} | {storage_change} | {status} |
| 冷数据 | {cold_data} | — | — | {status} |

- 存储增长来源：{growth_sources}
- 冷数据（30 天未访问）：{cold_data_tables}

### 分析
{cost_analysis}

### 建议
- {cost_suggestion_1}
- {cost_suggestion_2}

## 七、容量预测与风险预警（Q6）
### 结论
{capacity_conclusion}

### 关键事实
| 资源 | 当前使用率 | 预计达 80% 时间 | 风险等级 |
|------|------------|-----------------|----------|
| 存储 | {storage_rate} | {storage_forecast} | {risk} |
| 连接 | {conn_rate} | {conn_forecast} | {risk} |
| CPU | {cpu_rate} | {cpu_forecast} | {risk} |
| 表数量 | {table_rate} | {table_forecast} | {risk} |

### 分析
{capacity_analysis}

### 建议
- {capacity_suggestion_1}
- {capacity_suggestion_2}

## 八、今日治理建议汇总
### 立即处理（P0）
- {action_p0_1}
- {action_p0_2}

### 近期治理（P1）
- {action_p1_1}
- {action_p1_2}

### 规划优化（P2）
- {action_p2_1}
- {action_p2_2}
```
