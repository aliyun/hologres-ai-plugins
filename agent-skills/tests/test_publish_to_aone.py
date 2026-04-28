"""Tests for publish_to_aone.py — package.json auto-generation logic."""

import json
from pathlib import Path

import pytest

# Adjust sys.path so we can import from the parent directory
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from publish_to_aone import (
    generate_package_json,
    parse_skill_md_frontmatter,
    read_package_json,
)

FRONTMATTER_MULTILINE = """\
---
name: test-skill
description: |
  First line of description.
  Second line with triggers.
  Triggers: "foo", "bar"
---

# Test Skill
Body content here.
"""

FRONTMATTER_SINGLE_LINE = """\
---
name: simple-skill
description: A simple one-line description.
---

# Simple Skill
"""

NO_FRONTMATTER = """\
# No Frontmatter Skill

This SKILL.md has no YAML frontmatter.
"""

EXISTING_PACKAGE_JSON = {
    "name": "existing-skill",
    "version": "2.3.0",
    "description": "Already exists",
    "publishConfig": {"registry": "https://contextlab.alibaba-inc.com/skill"},
    "aoneKit": {"generated": True},
}


@pytest.fixture
def skill_dir_with_frontmatter(tmp_path):
    d = tmp_path / "test-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(FRONTMATTER_MULTILINE, encoding="utf-8")
    return d


@pytest.fixture
def skill_dir_single_line(tmp_path):
    d = tmp_path / "simple-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(FRONTMATTER_SINGLE_LINE, encoding="utf-8")
    return d


@pytest.fixture
def skill_dir_no_frontmatter(tmp_path):
    d = tmp_path / "no-fm-skill"
    d.mkdir()
    (d / "SKILL.md").write_text(NO_FRONTMATTER, encoding="utf-8")
    return d


@pytest.fixture
def skill_dir_with_package_json(tmp_path):
    d = tmp_path / "existing-skill"
    d.mkdir()
    (d / "SKILL.md").write_text("# Existing\n", encoding="utf-8")
    (d / "package.json").write_text(
        json.dumps(EXISTING_PACKAGE_JSON, indent=2) + "\n", encoding="utf-8"
    )
    return d


class TestParseSkillMdFrontmatter:
    def test_multiline_description(self, skill_dir_with_frontmatter):
        result = parse_skill_md_frontmatter(skill_dir_with_frontmatter)
        assert result["name"] == "test-skill"
        assert "First line of description." in result["description"]
        assert "Second line with triggers." in result["description"]
        assert 'Triggers: "foo", "bar"' in result["description"]

    def test_single_line_description(self, skill_dir_single_line):
        result = parse_skill_md_frontmatter(skill_dir_single_line)
        assert result["name"] == "simple-skill"
        assert result["description"] == "A simple one-line description."

    def test_no_frontmatter_fallback(self, skill_dir_no_frontmatter):
        result = parse_skill_md_frontmatter(skill_dir_no_frontmatter)
        assert result["name"] == "no-fm-skill"
        assert result["description"] == ""

    def test_no_skill_md(self, tmp_path):
        d = tmp_path / "empty-skill"
        d.mkdir()
        result = parse_skill_md_frontmatter(d)
        assert result["name"] == "empty-skill"
        assert result["description"] == ""


class TestGeneratePackageJson:
    def test_generates_file_on_disk(self, skill_dir_with_frontmatter):
        pkg = generate_package_json(skill_dir_with_frontmatter)
        pkg_path = skill_dir_with_frontmatter / "package.json"
        assert pkg_path.exists()

        on_disk = json.loads(pkg_path.read_text(encoding="utf-8"))
        assert on_disk["name"] == "test-skill"
        assert on_disk["version"] == "1.0.0"
        assert "First line of description." in on_disk["description"]
        assert on_disk["publishConfig"] == {
            "registry": "https://contextlab.alibaba-inc.com/skill"
        }
        assert on_disk["aoneKit"] == {"generated": True}

    def test_returns_correct_dict(self, skill_dir_with_frontmatter):
        pkg = generate_package_json(skill_dir_with_frontmatter)
        assert pkg["name"] == "test-skill"
        assert pkg["version"] == "1.0.0"

    def test_fallback_when_no_frontmatter(self, skill_dir_no_frontmatter):
        pkg = generate_package_json(skill_dir_no_frontmatter)
        assert pkg["name"] == "no-fm-skill"
        assert pkg["description"] == ""
        assert pkg["version"] == "1.0.0"


class TestReadPackageJson:
    def test_reads_existing_package_json(self, skill_dir_with_package_json):
        pkg = read_package_json(skill_dir_with_package_json)
        assert pkg["name"] == "existing-skill"
        assert pkg["version"] == "2.3.0"
        assert pkg["description"] == "Already exists"

    def test_generates_when_missing(self, skill_dir_with_frontmatter):
        assert not (skill_dir_with_frontmatter / "package.json").exists()
        pkg = read_package_json(skill_dir_with_frontmatter)
        assert pkg["name"] == "test-skill"
        assert pkg["version"] == "1.0.0"
        # File should now exist on disk
        assert (skill_dir_with_frontmatter / "package.json").exists()

    def test_idempotent(self, skill_dir_with_frontmatter):
        """Second call should read the generated file, not regenerate."""
        pkg1 = read_package_json(skill_dir_with_frontmatter)
        # Manually bump version in the generated file
        pkg_path = skill_dir_with_frontmatter / "package.json"
        data = json.loads(pkg_path.read_text(encoding="utf-8"))
        data["version"] = "1.0.1"
        pkg_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

        pkg2 = read_package_json(skill_dir_with_frontmatter)
        assert pkg2["version"] == "1.0.1"  # Should read updated file, not regenerate
