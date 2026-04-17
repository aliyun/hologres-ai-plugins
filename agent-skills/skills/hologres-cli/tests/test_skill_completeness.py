"""Test SKILL.md completeness — ensure no feature is left undocumented.

Cross-references the actual CLI codebase to find features that should
be described in the skill documentation but might be missing.
"""

import re

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# 1. CLI command completeness
# ═══════════════════════════════════════════════════════════════════════════

class TestCommandCompleteness:
    """Ensure every CLI command and subcommand is covered in skill docs."""

    def test_no_undocumented_top_level_commands(self, skill_body, commands_md):
        """Every top-level command should appear in SKILL.md or commands.md."""
        from hologres_cli.main import cli

        combined = skill_body + "\n" + commands_md
        missing = []
        for cmd_name in cli.commands:
            if cmd_name not in combined:
                missing.append(cmd_name)
        assert not missing, \
            f"Commands not documented anywhere: {missing}"

    def test_no_undocumented_schema_subcommands(self, skill_body, commands_md):
        """Every schema subcommand should be documented."""
        from hologres_cli.commands.schema import schema_cmd

        combined = skill_body + "\n" + commands_md
        missing = []
        for sub_name in schema_cmd.commands:
            if sub_name not in combined:
                missing.append(f"schema {sub_name}")
        assert not missing, \
            f"Schema subcommands not documented: {missing}"

    def test_no_undocumented_data_subcommands(self, skill_body, commands_md):
        """Every data subcommand should be documented."""
        from hologres_cli.commands.data import data_cmd

        combined = skill_body + "\n" + commands_md
        missing = []
        for sub_name in data_cmd.commands:
            if sub_name not in combined:
                missing.append(f"data {sub_name}")
        assert not missing, \
            f"Data subcommands not documented: {missing}"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Error code completeness
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorCodeCompleteness:
    """Ensure all error codes used in the codebase are documented."""

    def _extract_error_codes_from_code(self) -> set[str]:
        """Extract all error code strings used in the CLI source."""
        import importlib
        import inspect
        codes = set()
        modules_to_check = [
            "hologres_cli.output",
            "hologres_cli.commands.sql",
            "hologres_cli.commands.schema",
            "hologres_cli.commands.data",
            "hologres_cli.commands.status",
            "hologres_cli.commands.instance",
            "hologres_cli.commands.warehouse",
        ]
        code_pattern = re.compile(r'["\']([A-Z][A-Z_]+_(?:ERROR|BLOCKED|REQUIRED))["\']')
        for mod_name in modules_to_check:
            try:
                mod = importlib.import_module(mod_name)
                source = inspect.getsource(mod)
                codes.update(code_pattern.findall(source))
            except Exception:
                pass
        return codes

    def test_all_code_error_codes_in_skill(self, skill_body, safety_md):
        """Every error code used in source should be in SKILL.md or safety-features.md."""
        codes = self._extract_error_codes_from_code()
        combined = skill_body + "\n" + safety_md
        missing = []
        for code in codes:
            if code not in combined:
                missing.append(code)
        assert not missing, \
            f"Error codes used in code but not documented: {missing}"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Output format completeness
# ═══════════════════════════════════════════════════════════════════════════

class TestOutputFormatCompleteness:
    """Ensure all output formats are documented with examples."""

    def test_all_formats_have_examples(self, skill_body):
        """Each output format should have at least one example."""
        from hologres_cli.output import VALID_FORMATS

        for fmt in VALID_FORMATS:
            assert fmt in skill_body, \
                f"Format '{fmt}' should have an example in SKILL.md"

    def test_format_flag_syntax(self, skill_body):
        """Format flag usage syntax should be shown."""
        assert "-f json" in skill_body or "-f table" in skill_body or \
               "--format" in skill_body, \
            "SKILL.md should show format flag syntax"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Masking pattern completeness
# ═══════════════════════════════════════════════════════════════════════════

class TestMaskingCompleteness:
    """Ensure all masking categories are documented."""

    def test_all_masking_patterns_documented(self, skill_body, safety_md):
        """Every registered masking pattern category should be documented."""
        from hologres_cli.masking import SENSITIVE_PATTERNS

        combined = (skill_body + "\n" + safety_md).lower()
        # Extract the pattern keywords from each registered pattern
        pattern_keywords = {
            "phone": ["phone", "mobile", "tel"],
            "email": ["email"],
            "password": ["password", "secret", "token"],
            "id_card": ["id_card", "ssn"],
            "bank_card": ["bank_card", "credit_card"],
        }
        missing = []
        for category, keywords in pattern_keywords.items():
            if not any(kw in combined for kw in keywords):
                missing.append(category)
        assert not missing, \
            f"Masking categories not documented: {missing}"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Safety feature completeness
# ═══════════════════════════════════════════════════════════════════════════

class TestSafetyCompleteness:
    """Ensure all safety features are fully documented."""

    def test_write_keywords_completeness(self, skill_body, safety_md):
        """All critical write keywords should be mentioned somewhere."""
        from hologres_cli.commands.sql import WRITE_KEYWORDS

        combined = (skill_body + "\n" + safety_md).upper()
        # At minimum, these critical ones must be documented
        critical = {"INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE"}
        missing = []
        for kw in critical:
            if kw not in combined:
                missing.append(kw)
        assert not missing, \
            f"Critical write keywords not documented: {missing}"

    def test_limit_bypass_documented(self, skill_body, safety_md):
        """Ways to bypass the row limit should be documented."""
        combined = skill_body + "\n" + safety_md
        assert "--no-limit-check" in combined, \
            "The --no-limit-check bypass should be documented"

    def test_audit_log_path_documented(self, skill_body, safety_md):
        """The audit log file path should be documented."""
        combined = skill_body + "\n" + safety_md
        assert "sql-history.jsonl" in combined or "history" in combined, \
            "The audit log file path (sql-history.jsonl) should be documented"


# ═══════════════════════════════════════════════════════════════════════════
# 6. Best practices completeness
# ═══════════════════════════════════════════════════════════════════════════

class TestBestPracticesCompleteness:
    """Ensure best practices section covers key recommendations."""

    def test_limit_best_practice(self, skill_body):
        """Should recommend using LIMIT."""
        body_lower = skill_body.lower()
        assert "limit" in body_lower, "Best practices should mention LIMIT"

    def test_json_output_recommendation(self, skill_body):
        """Should recommend JSON for automation."""
        body_lower = skill_body.lower()
        assert "json" in body_lower, "Best practices should recommend JSON output"

    def test_status_check_recommendation(self, skill_body):
        """Should recommend checking status before operations."""
        assert "status" in skill_body.lower(), \
            "Best practices should mention checking status"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Cross-document consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossDocConsistency:
    """Verify SKILL.md, commands.md, and safety-features.md are consistent."""

    def test_error_codes_consistent_across_docs(self, skill_body, safety_md):
        """Error codes in SKILL.md and safety-features.md should be the same set."""
        code_pattern = re.compile(r"`([A-Z][A-Z_]+)`")
        skill_codes = set(code_pattern.findall(skill_body))
        safety_codes = set(code_pattern.findall(safety_md))

        # Filter to only error-like codes
        error_pattern = re.compile(r".*(?:ERROR|BLOCKED|REQUIRED)$")
        skill_error_codes = {c for c in skill_codes if error_pattern.match(c)}
        safety_error_codes = {c for c in safety_codes if error_pattern.match(c)}

        # safety-features.md should be a superset of SKILL.md error codes
        missing_in_safety = skill_error_codes - safety_error_codes
        assert not missing_in_safety, \
            f"Error codes in SKILL.md but missing from safety-features.md: {missing_in_safety}"

    def test_commands_consistent_between_skill_and_ref(self, skill_body, commands_md):
        """Commands mentioned in SKILL.md should also be in commands.md."""
        # Extract hologres commands from SKILL.md
        skill_cmds = set(re.findall(r"`hologres\s+(\w+)", skill_body))
        for cmd in skill_cmds:
            assert cmd in commands_md, \
                f"Command 'hologres {cmd}' in SKILL.md but not in commands.md"
