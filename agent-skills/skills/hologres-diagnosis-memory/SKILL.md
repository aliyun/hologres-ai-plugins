---
name: hologres-diagnosis-memory
depends: [hologres-cli]
description: >
  Hologres 实例内存使用率异常诊断技能。当用户提到内存打满、OOM、内存持续高位、Worker 内存不均、内存泄漏、内存倾斜、内存归因分析等场景时使用。
  以 instance_id + 时间窗口为输入，自动完成内存水位形态判定（全局高 / 局部倾斜 / 持续不回落）、业务指标对齐、内存分类初筛（Query vs System/Cache），
  并沿 Query 主线、倾斜主线、Write/后台主线、System/元数据主线四大归因维度自动下钻，输出结构化的 Markdown 诊断报告与治理行动清单。
  云监控数据通过 `hologres metric query` / `hologres metric latest` 获取；元仓与 PG 系统表数据通过 `hologres sql run` 获取；OOM/Jeprof/Coredump 通过 `holo oncall common` 获取。
---

> ⚠️ **执行前就绪检查（所有诊断步骤之前完成）**：
> 1. 已 `pip install hologres-cli`，且 `hologres status` 能连通目标实例（连接哪个实例 / 库由当前 profile 决定，可用 `--profile <name>` 切换）。
> 2. 云监控 AK/SK 已就绪（`hologres metric config` 专用配置，或 profile 通用 AK/SK，或默认凭证链）。
> 3. `export HOLOGRES_SKILL=hologres-diagnosis-memory`，便于事后审计。
>
> 完整就绪细节见 [references/preconditions.md](references/preconditions.md)。

# Hologres 内存使用率诊断

按「宏观水位形态 → 业务对齐 → 内存分类 → 四大主线归因」自动化定位 OOM / 持续高位 / 倾斜根因。**仅做根因诊断**：对于问题 Query 仅输出 ID 与资源指标，不输出 SQL 改写或优化建议。

## 输入参数

| 参数 | 必填 | 说明 |
|------|------|------|
| `instance_id` | 是 | Hologres 实例 ID，例如 `hgprecn-cn-xxx`（传给 `hologres metric` 的 `--instance-id`） |
| `start_time` | 是 | 诊断开始时间，ISO-8601（北京时间须带 `+08:00` 或显式 epoch ms）或 epoch ms |
| `end_time` | 是 | 诊断结束时间，格式同 `start_time` |
| `region` | 否 | 云监控 Region，默认从 profile 的 `region_id` 自动读取；可用 `--region` 覆盖 |

> 数据库由当前 profile 的 `database` 决定，无需也无法在命令上指定 `--db-name`；如需换库用 `hologres config set database <db>` 或 `--profile <name>`。

### 时间窗口约束

内存诊断只分析 **最近 30 天内、且跨度不超过 7 天** 的数据。校验规则（按顺序执行）：

1. **30 天有效期**：`start_time` 必须满足 `start_time >= current_time - 30d`（`hg_query_log` 默认保留 30 天）。若早于 30 天前，**拒绝执行**并提示：
   > ⚠️ 诊断时间范围超出 hg_query_log 保留期（30 天），请重新指定 start_time >= {30天前日期}。
2. **7 天跨度上限**：若 `end_time - start_time > 7天`，使用 `AskUserQuestion` 工具引导用户收窄（选项：最近 7 天 / 3 天 / 1 天）。按选择重设 `start_time = end_time - N天`；"Other" 自填则校验跨度 ≤ 7 天且 ≥ 30 天前。

> 时间窗口长度决定分支阈值：`<24h` 短周期，`>24h` 长周期。

## hologres-cli 约定

- 元仓 / PG 系统表查询统一用 `hologres sql run --no-limit-check "<SQL>"`。
- 云监控指标用 `hologres metric query <metric> --instance-id <id> --start-time <s> --end-time <e> --period <p>` / `hologres metric latest <metric> --instance-id <id> --period <p>`；`instanceId` 由 CLI 自动注入，无需手填 `--dimensions`。
- 指标名前缀（`standard_` / `warehouse_` / ...）需由「前置：实例类型判定」结果拼进 metric 名（见 preconditions §4）。
- 连接层已自动 `SET hg_computing_resource = 'serverless'`；来源标记由 `export HOLOGRES_SKILL` 注入，**无需** 手写 `SET ...` 前缀。
- 时间格式：`hologres metric` 接受 ISO-8601 或 epoch ms，无时区 ISO 串按 UTC 解析，北京时间显式带 epoch ms 或注意时区。
- 输出 `digest` / `query_id` / `query` 时必须保留完整内容，**禁止** 使用 `left()` / `substr()` / `::char(N)` / `...` 截断；长 SQL 换行展示。
- 独立的指标 / SQL 命令可在同一轮并行下发以加速。

## 诊断主流程

```
前置：实例类型探测 → 自动确定指标前缀 {prefix}
    └ hologres instance-manage get → data.Instance.InstanceType → {prefix}（详见 references/preconditions.md §4）

第一阶段：内存水位采集 + 形态分级
    └ 详见 references/water-level-staging.md
    ├ 全局高 / 局部倾斜 / 持续不回落 → 第二阶段
    └ 安全平稳                      → 直接出具「健康」报告

第二阶段：内存分类下钻
    ├ Q1 内存水位总览（形态判定）
    ├ Q2 业务指标对齐：CMS {prefix}query_qps / {prefix}dml_rps（排除正常增长）
    └ Q3 分类初筛：CMS {prefix}memory_usage_detail / {prefix}qe_memory_used_percentage
       详见 references/memory-classification.md

第三阶段：四大主线深挖
    ├ 主线 A — Query 侧（high-memory SQL / Plan 失真 / 访问不均）
    │           详见 references/query-attribution.md
    ├ 主线 B — 倾斜侧（Shard 物理分布 + Worker 热点 + 热点 Key）
    │           详见 references/shard-skew-analysis.md
    ├ 主线 C — Write/后台侧（DML RPS 冲击 + 后台 memType 占比）
    │           详见 references/system-metadata.md §C
    └ 主线 D — System/元数据侧（元数据膨胀 + 长事务 + 泄漏/Coredump）
                详见 references/system-metadata.md §D 与 references/internal-tools.md

第四阶段：综合输出诊断报告（Markdown）— 直接在对话中输出
    └ 模板详见 references/report-template.md
    └ ⚠️ 报告内容必须作为对话消息直接输出给用户，不要生成独立文档文件
```

### Q2 / Q3 分流判断速查

| Q2 现象 | 结论 | 后续 |
|---------|------|------|
| 内存↑ + QPS/RPS/DML 同比例↑ + 无 OOM | 正常业务增长 | 评估扩容；可中止 |
| 内存飙升但业务量平稳/下降 | 异常瓶颈 | 继续 Q3 |
| 内存↑ + 伴随 Failed Query / OOM | 异常瓶颈 | Q3 + 对应主线 |

| Q3 分类 | 判定条件 | 路由 |
|---------|----------|------|
| Query 内存占比 > 60-70% | QE Query 主导 | 主线 A |
| Worker 间内存差 > 20% | 倾斜 | 主线 B |
| cache / system / meta 占比高或持续累积 | 后台 | 主线 C + D |
| 水位高但分类不明 | 全量排查 | A+B+C+D 都走 |
| 水位高且不回落、无大 Query | 疑似泄漏 | 主线 D（+ internal-tools） |

## References

| 主题 | 文件 |
|------|------|
| 环境 / 权限 / 会话 / 前缀 / 时间格式 / 错误处理 | [preconditions.md](references/preconditions.md) |
| Stage 1 内存水位采集 + 形态分级 | [water-level-staging.md](references/water-level-staging.md) |
| Q3 内存分类初筛 | [memory-classification.md](references/memory-classification.md) |
| 主线 A — Query 内存归因 SQL | [query-attribution.md](references/query-attribution.md) |
| 主线 B — Shard 分布 / Worker 热点 / 热点 Key | [shard-skew-analysis.md](references/shard-skew-analysis.md) |
| 主线 C+D — Write/后台 + System/元数据 / 长事务 | [system-metadata.md](references/system-metadata.md) |
| OOM / Jeprof / Coredump 内部工具（泄漏排查） | [internal-tools.md](references/internal-tools.md) |
| 阈值表 + 数据源映射 | [thresholds.md](references/thresholds.md) |
| 第四阶段报告模板 | [report-template.md](references/report-template.md) |

## 注意事项

1. `hologres.hg_query_log` 默认保留约一个月，单次最多返回 10000 条；查询必须带 `query_start` 范围条件，且不要用 `to_char(query_start,...)` 包裹（无法走索引）。
2. CMS `period` 推荐 60（细粒度）或 300（长周期 / >6h 跨度）。
3. `digest` 字段从 V2.2 起支持，低版本实例为空，需降级为按 `query` 文本聚合。
4. `memory_bytes` 为各节点峰值内存的累加值，仅供相对排序参考；可能为 0（轻量查询取整为零或 GUC 关闭），此时降级使用 CMS `{prefix}qe_memory_used_percentage` + `{prefix}memory_usage_detail`（query memType）做 Query 内存归因。
5. 计算组（Warehouse）实例：若单组异常显著高于其他组 → 锁定该组后续所有诊断；全部组都高 → 视为全局高。
6. 本技能仅做根因诊断定位；问题 Query 只输出 ID 与资源指标快照，不包含 SQL 优化建议或改写指导。
7. **当 `hologres metric` / `hologres sql run` 返回空结果（无数据）时，禁止自行修改参数重试或变通获取数据；直接跳过该步骤，在输出结果中标注「无数据」。**
