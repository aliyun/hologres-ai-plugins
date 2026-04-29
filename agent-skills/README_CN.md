# Hologres Agent Skills

一个交互式安装器，用于将 Hologres AI Agent 技能分发到各类 AI 编程工具。

## 包含的技能

| 技能 | 依赖 | 说明 |
|------|------|------|
| `hologres-cli` | — | 教会 AI Agent 如何使用 Hologres CLI 工具 — 命令用法、安全特性、输出格式处理和最佳实践 |
| `hologres-query-optimizer` | `hologres-cli` | 使 AI Agent 能够分析和优化 Hologres SQL 查询执行计划 |
| `hologres-slow-query-analysis` | `hologres-cli` | 使 AI Agent 能够通过 `hologres.hg_query_log` 系统表诊断慢查询和失败查询 |
| `hologres-schema-generator` | `hologres-cli` | Hologres DDL 建表专家 — 存储格式选择、索引配置、分区表设计、数据类型推荐 |
| `hologres-privileges` | `hologres-cli` | Hologres 权限管理 — 基于 PostgreSQL 标准 GRANT/REVOKE 授权模型的细粒度访问控制 |
| `hologres-uv-compute` | `hologres-cli` | 基于 Dynamic Table + RoaringBitmap 的实时 UV/PV 去重计算方案 |
| `hologres-bsi-profile-analysis` | `hologres-cli` | 基于 BSI（位切片索引）的用户画像分析 — 标签计算、人群圈选、GMV 分析 |
| `hologres-ad-campaign` | `hologres-cli` | 基于 AI Function 的广告素材生成与投放分析 — 视频合成、虚拟投放模拟、Dynamic Table 实时 ROI 分析 |

> **说明：** 除 `hologres-cli` 外，其他所有技能均依赖它作为基础技能。SQL 执行、GUC 参数管理、数据操作等均通过 CLI 命令完成。请优先安装 `hologres-cli` 技能。

## 支持的 AI 工具

Claude Code、OpenClaw、Cursor、Codex、OpenCode、GitHub Copilot、Qoder、Trae

## 快速开始

### 通过 uvx 安装（推荐）

```bash
# 无需预安装，直接运行
uvx hologres-agent-skills
```

### 通过 pip 安装

```bash
pip install hologres-agent-skills
hologres-agent-skills
```

### 从源码安装（开发模式）

```bash
cd agent-skills
uv sync
uv run hologres-agent-skills
```

## 使用方式

安装器会引导你完成以下交互流程：

1. **选择工具** — 选择要安装技能的 AI 编程工具
2. **确认路径** — 确认安装目录
3. **选择技能** — 勾选一个或多个技能
4. **完成** — 技能文件被拷贝到对应工具的技能目录

```
$ hologres-agent-skills

🚀 Hologres Agent Skills Installer
==================================================

📋 Select tool to install to:
? Select one tool: Claude Code

📁 Project root: /path/to/your/project
   (Skills will be installed under .claude/skills)
? Install skills to this directory? Yes

📦 Select skills to install:
? Select skills:
  ● hologres-cli
  ● hologres-query-optimizer
  ● hologres-slow-query-analysis
  ● hologres-schema-generator
  ● hologres-privileges
  ● hologres-uv-compute
  ● hologres-bsi-profile-analysis
  ● hologres-ad-campaign

✨ Installation complete
```

## 开发

### 构建与发布到 PyPI

```bash
cd agent-skills

# 仅构建（产物在 dist/ 目录）
python upload_to_pypi.py --build

# 上传到 TestPyPI（验证）
export TEST_PYPI_TOKEN="pypi-xxx"
python upload_to_pypi.py --test

# 上传到正式 PyPI
export UV_PUBLISH_TOKEN="pypi-xxx"
python upload_to_pypi.py --publish

# 指定版本号并发布
python upload_to_pypi.py --publish --version 0.2.0
```

### 发布到 Aone (contextlab) 平台

将单个技能发布到 Aone 平台：

```bash
cd agent-skills

# 设置认证 Token
export AONE_TOKEN=<your-token>

# 发布全部技能
python publish_to_aone.py

# 发布指定技能
python publish_to_aone.py --skill hologres-cli

# 预览模式（不实际发布）
python publish_to_aone.py --dry-run

# 自动递增 patch 版本后发布
python publish_to_aone.py --bump

# 指定版本号
python publish_to_aone.py --version 1.2.0
```

### 项目结构

```
agent-skills/
├── skills/                          # 源技能文件
│   ├── hologres-cli/
│   ├── hologres-query-optimizer/
│   ├── hologres-slow-query-analysis/
│   ├── hologres-schema-generator/
│   ├── hologres-privileges/
│   ├── hologres-uv-compute/
│   ├── hologres-bsi-profile-analysis/
│   └── hologres-ad-campaign/
├── src/
│   └── holo_plugin_installer/
│       ├── __init__.py
│       └── main.py
├── pyproject.toml
├── MANIFEST.in
├── upload_to_pypi.py
├── publish_to_aone.py
├── README.md
└── README_CN.md
```

## 许可证

[Apache License 2.0](../LICENSE) — Copyright 2026 Alibaba Cloud
