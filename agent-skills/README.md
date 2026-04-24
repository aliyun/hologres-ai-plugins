# Hologres Agent Skills

An interactive installer that distributes Hologres AI agent skills to various AI coding tools.

## Included Skills

| Skill | Description |
|-------|-------------|
| `hologres-cli` | Teaches AI agents how to use the Hologres CLI tool — command usage, safety features, output formats, and best practices |
| `hologres-query-optimizer` | Enables AI agents to analyze and optimize Hologres SQL query execution plans |
| `hologres-slow-query-analysis` | Equips AI agents to diagnose slow/failed queries using `hologres.hg_query_log` |

## Supported AI Tools

Claude Code, OpenClaw, Cursor, Codex, OpenCode, GitHub Copilot, Qoder, Trae

## Quick Start

### Install via uvx (Recommended)

```bash
# Run directly without installation
uvx hologres-agent-skills
```

### Install via pip

```bash
pip install hologres-agent-skills
hologres-agent-skills
```

### Install from source (Development)

```bash
cd agent-skills
uv sync
uv run hologres-agent-skills
```

## Usage

The installer guides you through an interactive workflow:

1. **Select tool** — Choose which AI coding tool to install skills for
2. **Confirm path** — Verify the installation directory
3. **Select skills** — Pick one or more skills to install
4. **Done** — Skills are copied to the tool's skills directory

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

✨ Installation complete
```

## Development

### Build

```bash
cd agent-skills

# Build wheel (syncs skills into package, builds, then cleans up)
uv run upload_to_pypi.py

# Publish to PyPI
python -m twine upload dist/*
```

### Project Structure

```
agent-skills/
├── skills/                          # Source skills
│   ├── hologres-cli/
│   ├── hologres-query-optimizer/
│   └── hologres-slow-query-analysis/
├── src/
│   └── holo_plugin_installer/
│       ├── __init__.py
│       └── main.py
├── pyproject.toml
├── MANIFEST.in
├── upload_to_pypi.py
├── README.md
└── README_CN.md
```

## License

[Apache License 2.0](../LICENSE) — Copyright 2026 Alibaba Cloud
