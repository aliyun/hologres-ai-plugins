# 内存诊断报告模板

第四阶段将此 Markdown 报告**直接作为对话消息输出**给用户 —— 不要生成独立文档文件（如 `memory_diagnosis_report_xxx.md`）。报告较长时也整体在对话中输出，不要转存为文件。**每个占位符必须用真实查询结果填充，不得编造。** `query` / `query_id` / `digest` 保留完整，不得截断。

```markdown
# Hologres 内存使用率诊断

- **实例 ID**：`{instance_id}`（通用型/计算组型） / `{region}`
- **诊断时段**：`{start_time}` ~ `{end_time}`（北京时间）
- **涉及计算组**：{affected_clusters} (仅当检测到单组异常时显示)
- **健康评分**：`{score}`/100 | **整体状态**：`{status}` (正常 / 警告 / 异常)

## 一、今日摘要

> **核心结论**：`{summary_conclusion}`
> **根因归类**：`{root_cause_category}`

- **关键风险**：`{top_risks}` (例如：OOM 风险极高、新查询可能被 Reject、潜在内存泄漏)
- **推荐动作**：`{action_top_1}`, `{action_top_2}`

---

## 二、Q1: 内存水位总览

### 1. 结论
`{q1_conclusion}`

### 2. 关键事实数据

| 维度 | 指标 | 当前值/峰值 | 基线/预期值 | 波动幅度 | 状态判定 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **整体水位** | 实例内存使用率 (Max) | `{mem_max_pct}%` | `{mem_baseline_pct}%` | `{mem_diff}%` | **高危** |
| **稳定性** | OOM 事件次数 | `{oom_count}` | 0 | - | **异常** |
| **回落情况** | 低峰期最小水位 | `{min_mem_pct}%` | `{base_min_pct}%` | - | **未回落/倾斜** |
| **影响面** | 高水位 Worker 占比 | `{high_worker_pct}%` | - | - | `{scope_status}` |

### 3. 分析与建议
- **分析**：`{q1_analysis}` (基于形态判断：全体高 vs 局部高 vs 不回落)
- **建议**：根据形态进入后续 Q2-Q5 专项排查。

---

## 三、Q2: Worker 内存分布分析

### 1. 结论
`{q2_conclusion}`

### 2. 关键事实数据

| 维度 | 最大值 (Max) | 最小值 (Min) | 平均值 (Avg) | 偏差状态 |
| :--- | :--- | :--- | :--- | :--- |
| **Worker 内存 P95** | `{max_worker_mem}%` | `{min_worker_mem}%` | `{avg_worker_mem}%` | `{skew_flag}` |

- **倾斜详情**：
    - 热点 Worker：`{hot_worker_id}`
    - 疑似热点表/Shard：`{skewed_table_name}` (Dist Key: `{dist_key}`)
    - Shard 分配检查：`{shard_distribution_status}`

### 3. 分析与建议
- **分析**：`{q2_analysis}`
- **建议**：`{q2_suggestion}` (如：发现热点 Dist Key，建议调整分布键)

---

## 四、Q3: 高内存查询分析

### 1. 结论
`{q3_conclusion}`

### 2. 关键事实数据：Top 内存消耗 SQL

| 排名 | SQL 摘要 | 内存累加 (MB)* | Shuffle (GB) | CPU 时间 (s) | 算子类型 | 根因推测 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 1 | `{top1_sql}` | `{top1_mem}` | `{top1_spill}` | `{top1_cpu}` | `{top1_op}` | `{top1_reason}` |
| 2 | `{top2_sql}` | `{top2_mem}` | `{top2_spill}` | `{top2_cpu}` | `{top2_op}` | `{top2_reason}` |

*\*注：`memory_bytes` 为各节点峰值内存的累加值，仅供参考相对大小*

- **负载关联分析**：
    - 当时 QPS/RPS：`{current_qps}` / `{current_rps}`
    - QE 内存水位：`{qe_mem_pct}%`

### 3. 分析与建议
- **根因判断**：`{q3_conclusion}` (例如：Query ID 123456789 为内存主要消耗者，单次执行峰值内存达 20GB)
- **关键证据**：
  - Problematic Query ID: `{top1_query_id}`
  - 内存峰值: `{top1_mem}`
  - Shuffle 量: `{top1_spill}`
  - 关联算子: `{top1_op}` (如 HashJoin, Sort)
- **后续行动建议**：对问题 SQL 进行优化分析。

---

## 五、Q4: 系统与后台内存分析

### 1. 结论
`{q4_conclusion}`

### 2. 关键事实数据

| 组件类型 | 估值/计数 | 阈值/基线 | 状态 | 数据源参考 |
| :--- | :--- | :--- | :--- | :--- |
| **Meta Objects** | `{table_partition_count}` | < 10,000 | `{meta_status}` | hg_table_info |
| **Long Transactions** | `{long_txn_count}` | 0 | `{txn_status}` | pg_stat_activity |
| **Background Mem** | `{bg_mem_pct}%` | < 5% | `{bg_status}` | CloudMonitor |

### 3. 分析与建议
- **分析**：`{q4_analysis}`
- **建议**：`{q4_suggestion}`
    - 若是元数据：清理无效分区/表，合并小分区。
    - 若是长事务：`SELECT pg_terminate_backend({txn_pid});`
    - 若疑似泄漏：经 internal-tools（OOM/Jeprof/Coredump）确认后提单研发，重启可临时恢复。

---

## 六、Q5: 治理行动清单 (Action Plan)

### P0 - 立即处理 (阻断性风险)
- [ ] `{action_p0_1}` (例如：终止高内存消耗 Query xxx，释放内存)
- [ ] `{action_p0_2}` (例如：处理长事务 PID xxx)

### P1 - 近期优化 (性能提升)
- [ ] `{action_p1_1}` (例如：对 Top 3 大查询 SQL 进行优化分析)
- [ ] `{action_p1_2}` (例如：清理无效分区/表，合并小分区)

### P2 - 长期规划 (容量与架构)
- [ ] `{action_p2_1}` (例如：扩容 Warehouse / 拆分读写流量)
- [ ] `{action_p2_2}` (例如：建立内存与 OOM 联合告警阈值)
```
