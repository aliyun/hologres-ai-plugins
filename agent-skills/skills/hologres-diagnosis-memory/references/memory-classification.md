# 内存分类指标参考

## 云监控内存分类指标

内存分类初筛依赖云监控的内存细分指标，用于区分 Query Memory、Cache Memory、System/Meta Memory 等占用情况。

### 常用指标名称

> 指标前缀 `{prefix}` 由实例类型自动决定（如 `warehouse_`、`standard_`）。

| 指标名 | 说明 | 粒度 |
|--------|------|------|
| `{prefix}memory_usage` | 实例整体内存使用率 | 实例/Warehouse |
| `{prefix}memory_usage_by_worker` | 各 Worker 内存使用率 | Worker |
| `{prefix}memory_usage_detail` | 内存分类明细（按 memType 拆分：query / cache / meta / system 等） | 实例/Warehouse |
| `{prefix}qe_memory_used_percentage` | QE 引擎 Query 内存使用率 | 实例/Warehouse |
| `{prefix}cpu_usage` | CPU 使用率（辅助判断） | 实例/Warehouse |

> 注：`{prefix}` 含尾下划线（如 `warehouse_`），故完整指标名为 `warehouse_memory_usage`。

### 指标发现

如果不确定具体指标名，使用以下命令搜索：

```bash
# 搜索所有内存相关指标
hologres metric list --search memory

# 搜索 QE 相关内存指标
hologres metric list --search query_memory

# 搜索 SE 相关指标
hologres metric list --search storage
```

### 判断逻辑

| 分类 | 判定条件 | 后续路由 |
|------|----------|----------|
| Query 内存占比高 | Query Memory 占比 > 60-70% | → Query 主线排查 |
| Cache/System 内存占比高 | 非 Query 类内存占比高或持续累积 | → System/后台侧排查 |
| 无明显分类异常 | 无法明确区分 | → 全量排查 |

### 注意事项

1. 用户侧云监控指标较粗，可能无法精确区分 Query/Cache/System
2. 若云监控无法区分，可结合内存技术大盘或 PG 系统表辅助判断
3. 当无法明确分类时，默认进入全量排查模式（三条主线都走）
4. 内存技术大盘需要内部访问权限，外部用户通常不可见
