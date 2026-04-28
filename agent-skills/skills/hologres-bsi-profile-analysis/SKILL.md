---
name: hologres-bsi-profile-analysis
description: |
  Hologres BSI（位切片索引）画像分析 Skill，用于用户画像和标签计算。
  适用于 BSI 表设计、数据导入、属性标签+行为标签联合人群圈选、
  GMV 分析、标签分布统计、Top K 查询、分桶并行计算等场景。
  Triggers: "BSI", "位切片索引", "画像分析", "用户画像", "标签计算", "人群圈选", "行为标签",
  "bsi_build", "bsi_sum", "bsi_filter", "bsi_stat", "bsi_topk", "roaring bitmap profile",
  "标签圈人", "分桶计算"
---

# Hologres BSI 画像分析

> **参考文档**: [使用BSI进行画像分析中的标签计算](https://help.aliyun.com/zh/hologres/use-cases/profile-analysis-bsi-optimization-beta)

基于 BSI（Bit-sliced Index，位切片索引）的 Hologres 用户画像分析方案，支持对行为标签（GMV、PV、观看时长等）与属性标签（省份、性别等）进行高效联合计算。

**方案架构**: `Hologres 实例 + Roaring Bitmap 扩展 + BSI 扩展 + UID 字典编码 + 属性标签 Bitmap + 行为标签 BSI`

## ⚠️ CLI / 代码自动化限制总览

以下表格总结了本方案中各步骤的自动化可行性：

| 步骤 | 可自动化？ | 说明 |
|------|-----------|------|
| 安装扩展（`CREATE EXTENSION`） | ⚠️ CLI 需 `--write` 标志 | 需要 DDL 写权限：`hologres sql run --write "CREATE EXTENSION ..."` |
| 建表（`CREATE TABLE`） | ⚠️ CLI 需 `--write` 标志 | 需要 DDL 写权限：`hologres sql run --write "CREATE TABLE ..."` |
| UID 字典编码初始化 | ⚠️ CLI 需 `--write` 标志 | 通过 SQL INSERT 完成；增量维护由用户自行管理 |
| 源数据准备 | ❓ 需用户指定 | 用户必须提供属性标签源表和行为标签源表名称。若未指定，需要求用户提供 |
| 数据导入（INSERT INTO rb_tag/bsi_gmv） | ⚠️ CLI 需 `--write` 标志 | 需要 DML 写权限：`hologres sql run --write "INSERT INTO ..."` |
| BSI/RB 查询分析 | ✅ 完全可自动化 | 所有只读查询均可通过 `hologres sql run "SELECT ..."` 执行 |
| 分桶数选择 | ❌ 不可自动化 | 取决于集群规模和数据量，需要领域知识和性能调优 |
| 增量维护 | ❌ 由用户自行管理 | 可通过 DataWorks 等调度工具实现定时增量导入 |

# 背景

Roaring Bitmap 在用户画像场景中广泛用于属性标签索引，但存在两个关键局限：

1. **多标签联合查询问题**：Roaring Bitmap 仅适用于固定的分类型"属性标签"。对于量值类"行为标签"（如 GMV、订单金额、观看时长），只能回溯明细表进行关联查询。
2. **高基数标签问题**：当某标签去重值数量（基数）很大时，Roaring Bitmap 存储会膨胀，查询性能下降。

BSI 解决了上述两个问题：
- 对量值类行为标签进行预计算，以 BSI 压缩格式存储，可与属性标签的 Roaring Bitmap 直接联合分析，无需回溯明细表。
- 通过位切片索引，最多生成 32 个位切片即可存储 INT 范围内的所有行为标签值，实现压缩存储和低延迟查询。

## 前提条件

- Hologres 实例已安装 `roaringbitmap` 扩展
- 已安装 BSI 扩展

```sql
-- 安装所需扩展
CREATE EXTENSION IF NOT EXISTS roaringbitmap;
CREATE EXTENSION IF NOT EXISTS bsi;
```

> ⚠️ **CLI 写操作**：安装扩展需要 `--write` 标志：
> ```bash
> hologres sql run --write "CREATE EXTENSION IF NOT EXISTS roaringbitmap"
> hologres sql run --write "CREATE EXTENSION IF NOT EXISTS bsi"
> ```

## 快速开始

### 1. 建表

```sql
-- 用户属性标签表
CREATE TABLE dws_userbase (
    uid int NOT NULL PRIMARY KEY,
    province text,
    gender text
) WITH (distribution_key = 'uid');

-- UID 字典编码表（Roaring Bitmap / BSI 必需）
CREATE TABLE dws_uid_dict (
    encode_uid serial,
    uid int PRIMARY KEY
);

-- 用户行为标签表
CREATE TABLE usershop_behavior (
    uid int NOT NULL,
    gmv int
) WITH (distribution_key = 'uid');

-- Roaring Bitmap 属性标签表（tag_name + tag_val 复合主键）
CREATE TABLE rb_tag (
    tag_name text NOT NULL,
    tag_val text NOT NULL,
    bitmap roaringbitmap,
    PRIMARY KEY (tag_name, tag_val)
);

-- BSI 行为标签表（GMV）
CREATE TABLE bsi_gmv (
    gmv_bsi bsi
);
```

> ⚠️ **CLI 写操作**：建表需要 `--write` 标志：
> ```bash
> hologres sql run --write "CREATE TABLE ..."
> ```

### 2. 数据导入

```sql
-- 构建属性标签 Roaring Bitmap
INSERT INTO rb_tag
SELECT 'province', province, rb_build_agg(b.encode_uid) AS bitmap
FROM dws_userbase a JOIN dws_uid_dict b ON a.uid = b.uid
GROUP BY province;

-- 构建行为标签 BSI（注意：bsi_build 接收 integer[] 和 bigint[] 数组，gmv 需转换为 bigint）
INSERT INTO bsi_gmv
SELECT bsi_build(array_agg(b.encode_uid), array_agg(a.gmv::bigint)) AS bitmap
FROM usershop_behavior a JOIN dws_uid_dict b ON a.uid = b.uid;
```

> ⚠️ **CLI 写操作**：数据导入需要 `--write` 标志：
> ```bash
> hologres sql run --write "INSERT INTO ..."
> ```

> ⚠️ **UID 字典维护**：`dws_uid_dict` 必须在 BSI/Roaring Bitmap 导入前完成填充。
> - **初始化**：通过 SQL INSERT 完成
> - **增量维护**：由用户自行管理（可通过 DataWorks 等调度工具实现定时增量导入）

### 3. 查询示例

```sql
-- 查询“广东”+“男性”用户的 GMV 总值和人均 GMV
SELECT
    sum(kv[1]) AS total_gmv,
    sum(kv[1]) / sum(kv[2]) AS avg_gmv
FROM (
    SELECT bsi_sum(t1.gmv_bsi, t2.crowd) AS kv
    FROM bsi_gmv t1,
    (SELECT rb_and(a.bitmap, b.bitmap) AS crowd FROM
        (SELECT bitmap FROM rb_tag WHERE tag_name = 'gender' AND tag_val = 'Male') a,
        (SELECT bitmap FROM rb_tag WHERE tag_name = 'province' AND tag_val = '广东') b
    ) t2
) t;
```

This query can be executed via CLI:
```bash
hologres sql run "SELECT sum(kv[1]) AS total_gmv, sum(kv[1])/sum(kv[2]) AS avg_gmv FROM (SELECT bsi_sum(t1.gmv_bsi, t2.crowd) AS kv FROM bsi_gmv t1, (SELECT rb_and(a.bitmap,b.bitmap) AS crowd FROM (SELECT bitmap FROM rb_tag WHERE tag_name='gender' AND tag_val='Male') a, (SELECT bitmap FROM rb_tag WHERE tag_name='province' AND tag_val='广东') b) t2) t"
```

## 表设计

### 基础版（无分桶）

| 表名 | 字段 | 说明 |
|------|------|------|
| `dws_userbase` | `(uid int, province text, gender text)` | 用户属性标签源表 |
| `dws_uid_dict` | `(encode_uid serial, uid int)` | UID 字典编码表 |
| `usershop_behavior` | `(uid int, gmv int)` | 用户行为标签源表 |
| `rb_tag` | `(tag_name text, tag_val text, bitmap roaringbitmap)` PK=(tag_name, tag_val) | 属性标签 Roaring Bitmap 表 |
| `bsi_gmv` | `(gmv_bsi bsi)` | 行为标签 BSI 表 |

### 进阶版（分桶并行计算）

不分桶时，所有 BSI/Roaring Bitmap 数据集中在少数节点上。分桶可将数据分布到集群各节点，实现并行计算。

| 表名 | 字段 | 说明 |
|------|------|------|
| `dws_userbase` | `(uid int, province text, gender text)` | 用户属性标签源表 |
| `dws_uid_dict` | `(encode_uid serial, uid int)` | UID 字典编码表 |
| `usershop_behavior` | `(uid int, category text, gmv int, ds date)` | 用户行为标签源表（含分类、日期） |
| `rb_tag` | `(tag_name text, tag_val text, bucket int, bitmap roaringbitmap)` PK=(tag_name, tag_val, bucket) | 带分桶的属性标签 Roaring Bitmap 表 |
| `bsi_gmv` | `(ds text, category text, bucket int, gmv_bsi bsi)` | 带分桶、分类、日期的行为标签 BSI 表 |

关键区别：增加 `bucket` 字段，并设置 `distribution_key = 'bucket'` 确保数据均匀分布。

```sql
-- 分桶 Roaring Bitmap 属性标签表（复合主键）
CREATE TABLE rb_tag (
    tag_name text NOT NULL,
    tag_val text NOT NULL,
    bucket int NOT NULL,
    bitmap roaringbitmap,
    PRIMARY KEY (tag_name, tag_val, bucket)
) WITH (distribution_key = 'bucket');

-- 分桶 BSI 行为标签表
CREATE TABLE bsi_gmv (
    category text,
    bucket int,
    gmv_bsi bsi,
    ds date
) WITH (distribution_key = 'bucket');
```

## 常用查询模式

### 模式一：人群圈选 + 行为标签分析

**求和与均值**：查询圈选人群的 GMV 总值和人均 GMV。

```sql
-- 基础版：广东+男性用户的 GMV 总值和均值
SELECT
    sum(kv[1]) AS total_gmv,
    sum(kv[1]) / sum(kv[2]) AS avg_gmv
FROM (
    SELECT bsi_sum(t1.gmv_bsi, t2.crowd) AS kv
    FROM bsi_gmv t1,
    (SELECT rb_and(a.bitmap, b.bitmap) AS crowd FROM
        (SELECT bitmap FROM rb_tag WHERE tag_name = 'gender' AND tag_val = 'Male') a,
        (SELECT bitmap FROM rb_tag WHERE tag_name = 'province' AND tag_val = '广东') b
    ) t2
) t;

-- 分桶版：广东+男性用户、3C 品类、昨日的 GMV 总值和均值
SELECT
    sum(kv[1]) AS total_gmv,
    sum(kv[1]) / sum(kv[2]) AS avg_gmv
FROM (
    SELECT bsi_sum(t1.gmv_bsi, t2.crowd) AS kv, t1.bucket
    FROM (SELECT gmv_bsi, bucket FROM bsi_gmv WHERE category = '3C' AND ds = CURRENT_DATE - interval '1 day') t1
    JOIN
    (SELECT rb_and(a.bitmap, b.bitmap) AS crowd, a.bucket FROM
        (SELECT bitmap, bucket FROM rb_tag WHERE tag_name = 'gender' AND tag_val = 'Male') a
     JOIN
        (SELECT bitmap, bucket FROM rb_tag WHERE tag_name = 'province' AND tag_val = '广东') b
     ON a.bucket = b.bucket
    ) t2
    ON t1.bucket = t2.bucket
) t;
```

**分布统计**：按指定边界值统计 GMV 分布。

```sql
-- 基础版：按边界值 [100, 300, 500] 统计 GMV 分布
SELECT bsi_stat('{100,300,500}', filter_bsi)
FROM (
    SELECT bsi_filter(t1.gmv_bsi, t2.crowd) AS filter_bsi
    FROM bsi_gmv t1,
    (SELECT rb_and(a.bitmap, b.bitmap) AS crowd FROM
        (SELECT bitmap FROM rb_tag WHERE tag_name = 'gender' AND tag_val = 'Male') a,
        (SELECT bitmap FROM rb_tag WHERE tag_name = 'province' AND tag_val = '广东') b
    ) t2
) t;

-- 分桶版：聚合 BSI 后统计 GMV 分布
SELECT bsi_stat('{100,300,500}', bsi_add_agg(filter_bsi))
FROM (
    SELECT bsi_filter(t1.gmv_bsi, t2.crowd) AS filter_bsi, t1.bucket
    FROM (SELECT gmv_bsi, bucket FROM bsi_gmv WHERE category = '3C' AND ds = CURRENT_DATE - interval '1 day') t1
    JOIN
    (SELECT rb_and(a.bitmap, b.bitmap) AS crowd, a.bucket FROM
        (SELECT bitmap, bucket FROM rb_tag WHERE tag_name = 'gender' AND tag_val = 'Male') a
     JOIN
        (SELECT bitmap, bucket FROM rb_tag WHERE tag_name = 'province' AND tag_val = '广东') b
     ON a.bucket = b.bucket
    ) t2
    ON t1.bucket = t2.bucket
) t;
```

**Top K**：按行为标签值查询 Top K 用户。

```sql
-- 基础版：GMV Top 10 用户
SELECT rb_to_array(bsi_topk(filter_bsi, 10))
FROM (
    SELECT bsi_filter(t1.gmv_bsi, t2.crowd) AS filter_bsi
    FROM bsi_gmv t1,
    (SELECT rb_and(a.bitmap, b.bitmap) AS crowd FROM
        (SELECT bitmap FROM rb_tag WHERE tag_name = 'gender' AND tag_val = 'Male') a,
        (SELECT bitmap FROM rb_tag WHERE tag_name = 'province' AND tag_val = '广东') b
    ) t2
) t;

-- 分桶版：昨日 GMV Top 10 用户
SELECT bsi_topk(bsi_add_agg(filter_bsi), 10)
FROM (
    SELECT bsi_filter(t1.gmv_bsi, t2.crowd) AS filter_bsi, t1.bucket
    FROM (SELECT bsi_add_agg(gmv_bsi) AS gmv_bsi, bucket FROM bsi_gmv WHERE ds = CURRENT_DATE - interval '1 day' GROUP BY bucket) t1
    JOIN
    (SELECT rb_and(a.bitmap, b.bitmap) AS crowd, a.bucket FROM
        (SELECT bitmap, bucket FROM rb_tag WHERE tag_name = 'gender' AND tag_val = 'Male') a
     JOIN
        (SELECT bitmap, bucket FROM rb_tag WHERE tag_name = 'province' AND tag_val = '广东') b
     ON a.bucket = b.bucket
    ) t2
    ON t1.bucket = t2.bucket
) t;
```

### 模式二：基于行为标签的人群圈选

根据行为标签阈值圈选用户。

```sql
-- 基础版：圈选 GMV > 1000 的用户
SELECT rb_to_array(bsi_gt(gmv_bsi, 1000)) AS crowd
FROM bsi_gmv;

-- 分桶版：圈选过去一个月内 3C 品类 GMV > 1000 的用户
SELECT rb_to_array(bsi_gt(bsi_add_agg(gmv_bsi), 1000)) AS crowd
FROM bsi_gmv
WHERE category = '3C'
  AND ds BETWEEN CURRENT_DATE - interval '30 day' AND CURRENT_DATE - interval '1 day';
```

其他比较函数：

```sql
-- GMV >= 1000
SELECT rb_to_array(bsi_ge(gmv_bsi, 1000)) FROM bsi_gmv;

-- GMV < 500
SELECT rb_to_array(bsi_lt(gmv_bsi, 500)) FROM bsi_gmv;

-- GMV between 100 and 500 (inclusive)
SELECT rb_to_array(bsi_range(gmv_bsi, 100, 500)) FROM bsi_gmv;

-- GMV == 200
SELECT rb_to_array(bsi_eq(gmv_bsi, 200)) FROM bsi_gmv;

-- GMV != 0
SELECT rb_to_array(bsi_neq(gmv_bsi, 0)) FROM bsi_gmv;
```

## BSI 函数快速参考

完整函数参考请见 [references/bsi-functions.md](references/bsi-functions.md)。

| 函数 | 输入 | 输出 | 说明 |
|------|------|------|------|
| `bsi_build` | `integer[], bigint[]` | `bsi` | 从键值数组创建 BSI |
| `bsi_add_value` | `bsi, integer, bigint` | `bsi` | 向 BSI 添加一个键值对 |
| `bsi_iterate` | `bsi` | `set of integer[]` | 展开 BSI 为键值对 |
| `bsi_show` | `bsi/bytea, integer` | `text` | 显示前 N 个键值对 |
| `bsi_ebm` | `bsi/bytea` | `roaringbitmap` | 获取所有键作为 Roaring Bitmap |
| `bsi_eq` | `bsi, bigint [, bytea]` | `roaringbitmap` | 值 == N 的键 |
| `bsi_neq` | `bsi, bigint [, bytea]` | `roaringbitmap` | 值 != N 的键 |
| `bsi_gt` | `bsi, bigint [, bytea]` | `roaringbitmap` | 值 > N 的键 |
| `bsi_ge` | `bsi, bigint [, bytea]` | `roaringbitmap` | 值 >= N 的键 |
| `bsi_lt` | `bsi, bigint [, bytea]` | `roaringbitmap` | 值 < N 的键 |
| `bsi_le` | `bsi, bigint [, bytea]` | `roaringbitmap` | 值 <= N 的键 |
| `bsi_range` | `bsi, bigint, bigint [, bytea]` | `roaringbitmap` | 值在 [N, M] 范围内的键 |
| `bsi_filter` | `bsi/bytea, bytea` | `bsi` | 通过 Roaring Bitmap 交集过滤 BSI |
| `bsi_sum` | `bsi/bytea [, bytea]` | `bigint[]` | 返回 `[总和, 基数]` |
| `bsi_stat` | `bigint[], bsi/bytea [, bytea]` | `text` | 按边界值统计分布。**第一个参数是边界数组**，如 `'{100,300,500}'` |
| `bsi_topk` | `bsi/bytea, [bytea,] integer` | `roaringbitmap` | 按值取 Top K 键 |
| `bsi_transpose` | `bsi/bytea [, bytea]` | `roaringbitmap` | 去重值作为 Roaring Bitmap |
| `bsi_transpose_with_count` | `bsi/bytea [, bytea]` | `bsi` | 去重值及其计数作为 BSI |
| `bsi_add` | `bsi, bsi` | `bsi` | 相同键的两个 BSI 值相加 |
| `bsi_add_agg` | `bsi` | `bsi` | 跨行求和聚合 |
| `bsi_merge` | `bsi, bsi` | `bsi` | 合并两个 BSI（键不可重叠） |
| `bsi_merge_agg` | `bsi` | `bsi` | 合并聚合（键不可重叠） |
| `bsi_compare` | `text, bsi, [bytea,] bigint, bigint` | `roaringbitmap` | 比较过滤（LT/LE/GT/GE/EQ/NEQ/RANGE） |

> **可选 `bytea` 参数**：许多函数支持可选的 Roaring Bitmap（`bytea`）参数，先做交集再计算。这可以避免单独调用 `bsi_filter`。

## 数据导入模式

### 基础导入

```sql
-- 属性标签导入 Roaring Bitmap
INSERT INTO rb_tag
SELECT 'province', province, rb_build_agg(b.encode_uid) AS bitmap
FROM dws_userbase a JOIN dws_uid_dict b ON a.uid = b.uid
GROUP BY province;

-- 行为标签导入 BSI（bsi_build 需要 integer[] + bigint[] 数组参数）
INSERT INTO bsi_gmv
SELECT bsi_build(array_agg(b.encode_uid), array_agg(a.gmv::bigint)) AS bitmap
FROM usershop_behavior a JOIN dws_uid_dict b ON a.uid = b.uid;
```

### 分桶导入

```sql
-- 带分桶的属性标签导入
INSERT INTO rb_tag
SELECT 'province', province, encode_uid / 65536 AS bucket,
    rb_build_agg(b.encode_uid) AS bitmap
FROM dws_userbase a JOIN dws_uid_dict b ON a.uid = b.uid
GROUP BY province, bucket;

-- 带分桶的行为标签导入
INSERT INTO bsi_gmv
SELECT a.category, b.encode_uid / 65536 AS bucket,
    bsi_build(array_agg(b.encode_uid), array_agg(a.gmv::bigint)) AS bitmap, a.ds
FROM usershop_behavior a JOIN dws_uid_dict b ON a.uid = b.uid
WHERE ds = CURRENT_DATE - interval '1 day'
GROUP BY category, bucket, ds;
```

## 实施说明

### ⚠️ 需要 `--write` 标志的操作（通过 CLI）

以下操作修改数据，通过 `hologres sql run` 执行时需要 `--write` 标志：

| 操作 | CLI 命令 | 备注 |
|------|---------|------|
| 安装扩展 | `hologres sql run --write "CREATE EXTENSION IF NOT EXISTS bsi"` | DDL 写 |
| 建表 | `hologres sql run --write "CREATE TABLE ..."` | DDL 写 |
| 数据导入 (INSERT) | `hologres sql run --write "INSERT INTO ..."` | DML 写 |

### ✅ 可以只读执行的操作（通过 CLI）

所有 BSI/Roaring Bitmap 查询函数均为只读，完全可自动化：

```bash
# 求和与基数
hologres sql run "SELECT bsi_sum(gmv_bsi) FROM bsi_gmv"

# Top K 查询
hologres sql run "SELECT rb_to_array(bsi_topk(gmv_bsi, 10)) FROM bsi_gmv"

# 分布统计
hologres sql run "SELECT bsi_stat('{100,300,500}', gmv_bsi) FROM bsi_gmv"

# 人群过滤
hologres sql run "SELECT rb_to_array(bsi_gt(gmv_bsi, 1000)) FROM bsi_gmv"

# 比较查询（均为只读）
hologres sql run "SELECT rb_to_array(bsi_ge(gmv_bsi, 1000)) FROM bsi_gmv"
hologres sql run "SELECT rb_to_array(bsi_lt(gmv_bsi, 500)) FROM bsi_gmv"
hologres sql run "SELECT rb_to_array(bsi_range(gmv_bsi, 100, 500)) FROM bsi_gmv"
hologres sql run "SELECT rb_to_array(bsi_eq(gmv_bsi, 200)) FROM bsi_gmv"
hologres sql run "SELECT rb_to_array(bsi_neq(gmv_bsi, 0)) FROM bsi_gmv"
```

### ❌ 不可通过 CLI 或代码自动化的操作

以下步骤需要手动设置或超出 CLI 范围：

| 步骤 | 原因 | 解决方案 |
|------|--------|------------|
| UID 字典编码（`dws_uid_dict`） | 需在 BSI/RB 导入前完成填充 | 初始化通过 SQL INSERT 完成；增量维护由用户自行管理 |
| 源数据准备 | 用户需指定属性标签源表和行为标签源表 | 用户需指定属性标签源表和行为标签源表；若未指定，必须要求用户提供 |
| 分桶数选择 | 取决于集群规模和数据量，需要领域知识 | 推荐使用 `encode_uid / 65536` 作为分桶键，具体需结合业务调优 |
| 增量维护 | 由用户自行管理 | 可通过 DataWorks 等调度工具实现定时增量导入 |

## 最佳实践

1. **始终使用 UID 字典编码**：BSI 和 Roaring Bitmap 需要连续整数键。导入前先构建 `dws_uid_dict`。
2. **大数据量时使用分桶**：不分桶时数据集中在少数节点。使用 `encode_uid / 65536` 作为分桶键实现均匀分布。
3. **设置 `distribution_key = 'bucket'`**：确保数据分片与分桶边界对齐，实现本地计算。
4. **分桶聚合时使用 `bsi_add_agg`**：分析前先跨分桶聚合 BSI。
5. **优先使用可选 `bytea` 参数**：不必 `bsi_filter` + `bsi_sum` 分开调用，直接用 `bsi_sum(bsi, crowd_bytea)` 性能更优。
6. **使用 `bsi_stat` 做分布统计**：比明细表的多个 `CASE WHEN` 查询更高效。
7. **使用 `bsi_topk` 做排序**：将全局排序转化为位交集运算，比 `ORDER BY ... LIMIT` 快得多。
8. **BSI 值范围限制在 INT 内**：BSI 以 32 位切片存储值，值必须在整数范围内。

## 参考文档

| 文档 | 说明 |
|------|------|
| [references/bsi-functions.md](references/bsi-functions.md) | 完整的 BSI 函数参考，含语法和示例 |
| [references/table-design.md](references/table-design.md) | 基础版和分桶版的表设计模式和 DDL |