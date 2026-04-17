"""Fixtures for hologres-cli skill tests.

Provides parsed SKILL.md content and reference file access for validation tests.
"""

import re
import sys
from pathlib import Path

import pytest

# ── Path setup ──────────────────────────────────────────────────────────────
SKILL_DIR = Path(__file__).resolve().parent.parent          # agent-skills/skills/hologres-cli
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES_DIR = SKILL_DIR / "references"
COMMANDS_MD = REFERENCES_DIR / "commands.md"
SAFETY_MD = REFERENCES_DIR / "safety-features.md"

# Add hologres-cli/src to sys.path so we can import the actual CLI modules
# Path: tests/ -> hologres-cli/ -> skills/ -> agent-skills/ -> project-root/ -> hologres-cli/src
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
CLI_SRC = PROJECT_ROOT / "hologres-cli" / "src"
if str(CLI_SRC) not in sys.path:
    sys.path.insert(0, str(CLI_SRC))


# ── Helper: YAML frontmatter parser (lightweight) ──────────────────────────
def _parse_frontmatter(text: str) -> tuple[dict, str]:
    """Parse YAML-like frontmatter from markdown.

    Returns (metadata_dict, body_text).
    """
    if not text.startswith("---"):
        return {}, text
    end = text.find("---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    meta = {}
    current_key = None
    current_val_lines = []
    for line in fm_block.splitlines():
        m = re.match(r"^(\w[\w-]*):\s*(.*)", line)
        if m:
            if current_key:
                meta[current_key] = "\n".join(current_val_lines).strip()
            current_key = m.group(1)
            current_val_lines = [m.group(2).strip().lstrip("|").strip()]
        else:
            current_val_lines.append(line.strip())
    if current_key:
        meta[current_key] = "\n".join(current_val_lines).strip()
    body = text[end + 3:].strip()
    return meta, body


# ── Fixtures ────────────────────────────────────────────────────────────────
@pytest.fixture(scope="session")
def skill_raw() -> str:
    """Raw SKILL.md content."""
    return SKILL_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def skill_frontmatter(skill_raw) -> dict:
    """Parsed frontmatter metadata from SKILL.md."""
    meta, _ = _parse_frontmatter(skill_raw)
    return meta


@pytest.fixture(scope="session")
def skill_body(skill_raw) -> str:
    """Body text of SKILL.md (without frontmatter)."""
    _, body = _parse_frontmatter(skill_raw)
    return body


@pytest.fixture(scope="session")
def commands_md() -> str:
    """Raw content of references/commands.md."""
    return COMMANDS_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def safety_md() -> str:
    """Raw content of references/safety-features.md."""
    return SAFETY_MD.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def skill_sections(skill_body) -> dict[str, str]:
    """Split SKILL.md body into sections keyed by heading text (lowercase)."""
    sections: dict[str, str] = {}
    current_heading = "_preamble"
    current_lines: list[str] = []
    for line in skill_body.splitlines():
        m = re.match(r"^#{1,3}\s+(.+)", line)
        if m:
            sections[current_heading] = "\n".join(current_lines)
            current_heading = m.group(1).strip().lower()
            current_lines = []
        else:
            current_lines.append(line)
    sections[current_heading] = "\n".join(current_lines)
    return sections
