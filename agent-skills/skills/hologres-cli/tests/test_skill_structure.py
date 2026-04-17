"""Test SKILL.md document structure and formatting.

Validates that the skill document follows the expected structure,
has all required sections, and reference files are properly linked.
"""

import re
import sys
from pathlib import Path

import pytest

SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_MD = SKILL_DIR / "SKILL.md"
REFERENCES_DIR = SKILL_DIR / "references"


# ═══════════════════════════════════════════════════════════════════════════
# 1. File existence
# ═══════════════════════════════════════════════════════════════════════════

class TestFileExistence:
    """Verify that all required skill files exist."""

    def test_skill_md_exists(self):
        assert SKILL_MD.exists(), "SKILL.md must exist"

    def test_references_dir_exists(self):
        assert REFERENCES_DIR.exists(), "references/ directory must exist"

    def test_commands_md_exists(self):
        assert (REFERENCES_DIR / "commands.md").exists(), "references/commands.md must exist"

    def test_safety_features_md_exists(self):
        assert (REFERENCES_DIR / "safety-features.md").exists(), "references/safety-features.md must exist"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Frontmatter validation
# ═══════════════════════════════════════════════════════════════════════════

class TestFrontmatter:
    """Validate YAML frontmatter in SKILL.md."""

    def test_has_frontmatter(self, skill_raw):
        assert skill_raw.startswith("---"), "SKILL.md must start with YAML frontmatter (---)"

    def test_frontmatter_has_name(self, skill_frontmatter):
        assert "name" in skill_frontmatter, "Frontmatter must have 'name' field"

    def test_frontmatter_name_value(self, skill_frontmatter):
        assert skill_frontmatter["name"] == "hologres-cli", \
            f"Frontmatter name should be 'hologres-cli', got '{skill_frontmatter['name']}'"

    def test_frontmatter_has_description(self, skill_frontmatter):
        assert "description" in skill_frontmatter, "Frontmatter must have 'description' field"

    def test_frontmatter_description_not_empty(self, skill_frontmatter):
        desc = skill_frontmatter.get("description", "")
        assert len(desc) > 20, "Frontmatter description should be meaningful (>20 chars)"

    def test_frontmatter_has_triggers(self, skill_frontmatter):
        desc = skill_frontmatter.get("description", "")
        assert "Triggers:" in desc or "triggers:" in desc.lower(), \
            "Frontmatter description should include trigger keywords"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Required sections
# ═══════════════════════════════════════════════════════════════════════════

class TestRequiredSections:
    """Verify SKILL.md has all required top-level sections."""

    @pytest.mark.parametrize("section_name", [
        "installation",
        "configuration",
        "quick start",
        "core commands",
        "output formats",
        "safety features",
        "error codes",
        "sensitive data masking",
        "best practices",
        "references",
    ])
    def test_has_section(self, skill_body, section_name):
        # Case-insensitive section heading search
        pattern = re.compile(r"^#{1,3}\s+" + re.escape(section_name), re.IGNORECASE | re.MULTILINE)
        assert pattern.search(skill_body), f"SKILL.md must have a '{section_name}' section"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Content format validation
# ═══════════════════════════════════════════════════════════════════════════

class TestContentFormat:
    """Validate formatting and content quality of SKILL.md."""

    def test_has_code_blocks(self, skill_body):
        code_blocks = re.findall(r"```", skill_body)
        assert len(code_blocks) >= 6, \
            f"SKILL.md should have at least 3 code blocks (found {len(code_blocks) // 2})"

    def test_has_bash_examples(self, skill_body):
        assert "```bash" in skill_body, "SKILL.md should include bash code examples"

    def test_has_json_examples(self, skill_body):
        assert "```json" in skill_body, "SKILL.md should include JSON output examples"

    def test_has_command_table(self, skill_body):
        # Should have a table with pipe separators listing commands
        assert "| Command" in skill_body or "| `hologres" in skill_body, \
            "SKILL.md should have a command reference table"

    def test_has_error_code_table(self, skill_body):
        assert "| Code" in skill_body or "| `CONNECTION_ERROR" in skill_body or \
               "CONNECTION_ERROR" in skill_body, \
            "SKILL.md should have an error code reference table"

    def test_dsn_format_documented(self, skill_body):
        assert "hologres://" in skill_body, "SKILL.md should document the DSN format"

    def test_no_broken_markdown_links(self, skill_body):
        # Find markdown links and verify referenced files exist
        link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
        for match in link_pattern.finditer(skill_body):
            link_text, link_target = match.groups()
            if link_target.startswith("http"):
                continue  # Skip external links
            target_path = SKILL_DIR / link_target
            assert target_path.exists(), \
                f"Broken link in SKILL.md: [{link_text}]({link_target}) - file not found"

    def test_response_structure_documented(self, skill_body):
        """Verify success/error response structure is shown."""
        assert '"ok": true' in skill_body or '"ok":true' in skill_body, \
            "SKILL.md should show success response structure with 'ok: true'"
        assert '"ok": false' in skill_body or '"ok":false' in skill_body, \
            "SKILL.md should show error response structure with 'ok: false'"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Reference files structure
# ═══════════════════════════════════════════════════════════════════════════

class TestReferenceFiles:
    """Validate reference file structure and content."""

    def test_commands_md_has_heading(self, commands_md):
        assert commands_md.startswith("#"), "commands.md should start with a heading"

    def test_commands_md_not_empty(self, commands_md):
        assert len(commands_md) > 100, "commands.md should have substantial content"

    def test_safety_md_has_heading(self, safety_md):
        assert safety_md.startswith("#"), "safety-features.md should start with a heading"

    def test_safety_md_not_empty(self, safety_md):
        assert len(safety_md) > 100, "safety-features.md should have substantial content"

    @pytest.mark.parametrize("section", [
        "status", "instance", "warehouse", "schema", "sql", "data", "history"
    ])
    def test_commands_md_documents_command(self, commands_md, section):
        assert section.lower() in commands_md.lower(), \
            f"commands.md should document the '{section}' command"

    @pytest.mark.parametrize("feature", [
        "row limit", "write protection", "dangerous write", "sensitive data masking"
    ])
    def test_safety_md_documents_feature(self, safety_md, feature):
        assert feature.lower() in safety_md.lower(), \
            f"safety-features.md should document '{feature}'"
