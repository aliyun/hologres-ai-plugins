#!/usr/bin/env python3
"""Verify every skill on disk is registered in all 5 catalog files.

The 5 catalogs are:
  1. agent-skills/src/holo_plugin_installer/main.py  (AVAILABLE_SKILLS list — runtime truth)
  2. agent-skills/README.md                          (English skill table + install demo + tree)
  3. agent-skills/README_CN.md                       (Chinese version of above)
  4. README.md                                       (root, English: structure tree + detailed sections)
  5. README_CN.md                                    (root, Chinese version of above)

This script catches "ghost skills" — skill directories added to disk but forgotten in
one or more catalogs, which means `uvx hologres-agent-skills` users cannot install them.

Usage
-----
Standalone (exits non-zero on failure, prints a clear report):

    python agent-skills/tests/test_catalog_consistency.py

Via pytest:

    pytest agent-skills/tests/test_catalog_consistency.py -v

Add to your pre-commit hook: see .githooks/pre-commit in the repo root.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

# Locate paths relative to this file: agent-skills/tests/test_catalog_consistency.py
_THIS_FILE = Path(__file__).resolve()
AGENT_SKILLS_DIR = _THIS_FILE.parent.parent
REPO_ROOT = AGENT_SKILLS_DIR.parent

SKILLS_DIR = AGENT_SKILLS_DIR / "skills"
INSTALLER = AGENT_SKILLS_DIR / "src" / "holo_plugin_installer" / "main.py"

# 4 human-readable catalog files
README_FILES = [
    AGENT_SKILLS_DIR / "README.md",
    AGENT_SKILLS_DIR / "README_CN.md",
    REPO_ROOT / "README.md",
    REPO_ROOT / "README_CN.md",
]

# Skills exempt from the "must appear in every catalog" rule.
# Add a skill name here if it is intentionally hidden (e.g. WIP not yet ready to ship).
EXEMPT: set[str] = set()

# Pattern matches `hologres-<lowercase-and-hyphens>` tokens anywhere in text.
# Token boundary: start-of-string or non-alnum on the left; non-alnum on the right.
_SKILL_PATTERN = re.compile(r"(?<![A-Za-z0-9])hologres-[a-z][a-z0-9-]*")


def list_disk_skills() -> list[str]:
    """Return sorted list of skill directory names under agent-skills/skills/."""
    return sorted(
        p.name
        for p in SKILLS_DIR.iterdir()
        if p.is_dir() and not p.name.startswith(".")
    )


def parse_available_skills() -> list[str]:
    """Parse AVAILABLE_SKILLS from main.py without executing it.

    Avoids triggering the `import questionary` at module top, which fails in
    a clean Python environment.
    """
    src = INSTALLER.read_text()
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        if not any(
            isinstance(t, ast.Name) and t.id == "AVAILABLE_SKILLS"
            for t in node.targets
        ):
            continue
        if not isinstance(node.value, (ast.List, ast.Tuple)):
            raise RuntimeError(
                f"AVAILABLE_SKILLS in {INSTALLER} is not a list/tuple literal; "
                "this checker only supports static lists."
            )
        return [
            el.value for el in node.value.elts
            if isinstance(el, ast.Constant) and isinstance(el.value, str)
        ]
    raise RuntimeError(f"AVAILABLE_SKILLS not found in {INSTALLER}")


def find_mentions(text: str) -> set[str]:
    """Return all `hologres-xxx` skill names mentioned in text."""
    return set(_SKILL_PATTERN.findall(text))


def find_drift() -> dict[str, set[str]]:
    """Compute drift between disk and each catalog.

    Returns mapping `catalog path (relative to repo root) -> set of MISSING skill names`.
    Empty mapping means every catalog covers every on-disk skill.
    """
    disk_skills = set(list_disk_skills()) - EXEMPT
    drift: dict[str, set[str]] = {}

    installer_skills = set(parse_available_skills())
    inst_missing = disk_skills - installer_skills
    if inst_missing:
        drift[str(INSTALLER.relative_to(REPO_ROOT))] = inst_missing

    for readme in README_FILES:
        mentions = find_mentions(readme.read_text())
        missing = disk_skills - mentions
        if missing:
            drift[str(readme.relative_to(REPO_ROOT))] = missing

    return drift


def find_stale() -> set[str]:
    """Return skill names registered in installer but missing from disk (stale entries)."""
    return set(parse_available_skills()) - set(list_disk_skills()) - EXEMPT


def test_catalog_consistency() -> None:
    """pytest entrypoint — asserts no drift and no stale entries."""
    drift = find_drift()
    stale = find_stale()

    problems: list[str] = []

    if drift:
        problems.append("Skills on disk missing from one or more catalogs:")
        for path, skills in sorted(drift.items()):
            problems.append(f"  {path}:")
            for s in sorted(skills):
                problems.append(f"    - {s}")

    if stale:
        problems.append("Skills registered in installer but NOT on disk (stale):")
        for s in sorted(stale):
            problems.append(f"    - {s}")

    if problems:
        problems.append("")
        problems.append("Fix: add each missing skill to the listed catalog files,")
        problems.append("or add it to EXEMPT in this script if intentionally hidden.")
        problems.append("")
        problems.append(f"Re-run: python {Path(__file__).relative_to(REPO_ROOT)}")
        raise AssertionError("\n" + "\n".join(problems))


def _main() -> int:
    try:
        test_catalog_consistency()
    except AssertionError as e:
        print("FAIL: catalog drift detected", file=sys.stderr)
        print(str(e), file=sys.stderr)
        return 1
    disk_count = len(list_disk_skills())
    print(
        f"OK: all {disk_count} skills are registered in installer + "
        f"{len(README_FILES)} README catalogs."
    )
    return 0


if __name__ == "__main__":
    sys.exit(_main())
