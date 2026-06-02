# OOM / Jeprof / Coredump 内部工具使用参考

当内存分类不明、水位不回落、无大 SQL 时，需要使用内部高阶工具排查内存泄漏和底层故障。

## OOM List

### 命令

```bash
holo oncall common oom {instance_id}
```

### 输出字段

| 字段 | 说明 |
|------|------|
| 时间 | OOM 触发时间 |
| 进程 | 被 OOM Killer 杀死的进程 |
| 节点 | 发生 OOM 的 Worker 节点 |
| 上下文 | OOM 前的内存使用快照 |

### 判断逻辑

- OOM List 频繁触发且无对应大 Query → 容量不足或异常泄漏
- OOM 伴随特定 Query → Query 内存消耗过大
- OOM 仅在特定 Worker → 可能存在数据倾斜

## Jeprof Result List

### 命令

```bash
holo oncall common coredumps {instance_id}
# Jeprof 结果通常也通过 coredumps/oom 接口获取
# 或通过 ABM 诊断页查看：https://abm.alibaba-inc.com/abm/#/holo/analyse/
```

### 输出字段

| 字段 | 说明 |
|------|------|
| 对象类型 | Java Heap 中占用最大的对象类 |
| 增长趋势 | 是否随时间线性增长 |
| 占用大小 | 当前堆内存占用 |
| 调用栈 | 分配该对象的热点调用链 |

### 判断逻辑

- 某类 Java Heap 对象随时间线性增长且不释放 → 确认内存泄漏
- 需要提单研发修复，重启实例可临时恢复

## Coredump List

### 命令

```bash
holo oncall common coredumps {instance_id}
```

### 输出字段

| 字段 | 说明 |
|------|------|
| 时间 | Coredump 发生时间 |
| 进程 | 崩溃进程名 |
| 信号 | 触发 Coredump 的信号（如 SIGSEGV、SIGABRT） |
| 堆栈 | 崩溃时的调用栈 |

### 判断逻辑

- Coredump 存在 → 分析崩溃现场，区分代码 Bug 还是硬件/OS 故障
- Coredump 伴随 OOM → 可能是 OOM 导致进程崩溃
- 需要进一步 GDB 分析时，使用 `codex-gdb-online-coredump-analyze` skill

## 综合排查流程

```
1. 检查 OOM List → 确认 OOM 时间点与进程
2. 检查 Jeprof → 分析堆内存对象分布与增长趋势
3. 检查 Coredump List → 确认是否有 Crash
4. 综合判断：
   - 泄漏 → 提单研发，重启临时恢复
   - 容量不足 → 扩容
   - Crash → GDB 分析 + 提单
```

## 注意事项

1. 内部工具需要相应权限配置，部分接口可能仅限内部访问
2. Jeprof 分析结果通常需要人工解读，诊断报告中给出摘要即可
3. Coredump 文件位于 `/cloud/data/corefile/`，GDB 分析需在 holo 目录下执行
4. OOM/Jeprof/Coredump 属于 P2 疑难杂症排查，通常在前面的主线排查无果后才进入
