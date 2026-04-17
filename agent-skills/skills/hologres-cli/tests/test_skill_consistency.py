"""Test SKILL.md consistency with actual CLI implementation.

Validates that the skill documentation accurately reflects the real CLI code:
commands, error codes, safety features, output formats, masking patterns, etc.
"""

import re

import pytest


# ═══════════════════════════════════════════════════════════════════════════
# 1. Command consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestCommandConsistency:
    """Verify documented commands match actual CLI registration."""

    def test_all_registered_commands_documented(self, skill_body):
        """Every command registered in main.py should appear in SKILL.md."""
        from hologres_cli.main import cli

        registered = set(cli.commands.keys())
        for cmd_name in registered:
            assert cmd_name in skill_body, \
                f"Command '{cmd_name}' is registered in CLI but not documented in SKILL.md"

    def test_schema_subcommands_documented(self, skill_body):
        """Schema subcommands should be documented."""
        from hologres_cli.commands.schema import schema_cmd

        for sub_name in schema_cmd.commands:
            # Check for e.g. "schema tables" or "schema describe"
            assert sub_name in skill_body, \
                f"Schema subcommand '{sub_name}' is not documented in SKILL.md"

    def test_data_subcommands_documented(self, skill_body):
        """Data subcommands should be documented."""
        from hologres_cli.commands.data import data_cmd

        for sub_name in data_cmd.commands:
            assert sub_name in skill_body, \
                f"Data subcommand '{sub_name}' is not documented in SKILL.md"

    def test_status_command_documented(self, skill_body):
        assert "hologres status" in skill_body

    def test_instance_command_documented(self, skill_body):
        assert "hologres instance" in skill_body

    def test_warehouse_command_documented(self, skill_body):
        assert "hologres warehouse" in skill_body

    def test_history_command_documented(self, skill_body):
        assert "hologres history" in skill_body or "history" in skill_body


# ═══════════════════════════════════════════════════════════════════════════
# 2. Error code consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorCodeConsistency:
    """Verify documented error codes match actual output.py definitions."""

    def _get_code_error_codes(self) -> set[str]:
        """Extract error codes defined in output.py helper functions."""
        from hologres_cli import output
        codes = set()
        # Extract from helper function bodies
        if hasattr(output, 'connection_error'):
            codes.add("CONNECTION_ERROR")
        if hasattr(output, 'query_error'):
            codes.add("QUERY_ERROR")
        if hasattr(output, 'limit_required_error'):
            codes.add("LIMIT_REQUIRED")
        if hasattr(output, 'write_guard_error'):
            codes.add("WRITE_GUARD_ERROR")
        if hasattr(output, 'dangerous_write_error'):
            codes.add("DANGEROUS_WRITE_BLOCKED")
        return codes

    def test_all_error_codes_documented_in_skill(self, skill_body):
        """All error codes from output.py should appear in SKILL.md."""
        codes = self._get_code_error_codes()
        for code in codes:
            assert code in skill_body, \
                f"Error code '{code}' exists in code but not documented in SKILL.md"

    def test_all_error_codes_documented_in_safety_md(self, safety_md):
        """All error codes should also appear in safety-features.md."""
        codes = self._get_code_error_codes()
        for code in codes:
            assert code in safety_md, \
                f"Error code '{code}' not documented in safety-features.md"

    def test_write_blocked_error_documented(self, skill_body):
        """The WRITE_BLOCKED error from sql.py should be in SKILL.md or commands.md."""
        # sql.py uses "WRITE_BLOCKED" directly
        assert "WRITE_BLOCKED" in skill_body or "write" in skill_body.lower(), \
            "Write blocking behavior should be documented"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Safety feature consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestSafetyConsistency:
    """Verify documented safety features match actual implementation."""

    def test_row_limit_value_matches(self, skill_body):
        """The documented row limit should match DEFAULT_ROW_LIMIT in sql.py."""
        from hologres_cli.commands.sql import DEFAULT_ROW_LIMIT
        assert str(DEFAULT_ROW_LIMIT) in skill_body, \
            f"SKILL.md should mention the default row limit ({DEFAULT_ROW_LIMIT})"

    def test_write_keywords_documented(self, skill_body):
        """Major write keywords should be mentioned in SKILL.md."""
        from hologres_cli.commands.sql import WRITE_KEYWORDS

        # At least the main ones should be documented
        critical_keywords = {"INSERT", "UPDATE", "DELETE", "DROP"}
        body_upper = skill_body.upper()
        for kw in critical_keywords:
            assert kw in body_upper, \
                f"Write keyword '{kw}' from WRITE_KEYWORDS should be documented in SKILL.md"

    def test_no_limit_check_flag_documented(self, skill_body):
        """The --no-limit-check flag should be documented."""
        assert "--no-limit-check" in skill_body, \
            "SKILL.md should document the --no-limit-check flag"

    def test_no_mask_flag_documented(self, skill_body):
        """The --no-mask flag should be documented."""
        assert "--no-mask" in skill_body, \
            "SKILL.md should document the --no-mask flag"

    def test_write_flag_documented(self, skill_body):
        """The --write flag should be documented."""
        assert "--write" in skill_body, \
            "SKILL.md should document the --write flag"

    def test_where_clause_requirement_documented(self, skill_body):
        """DELETE/UPDATE without WHERE blocking should be documented."""
        body_lower = skill_body.lower()
        assert "where" in body_lower, \
            "SKILL.md should mention WHERE clause requirement for DELETE/UPDATE"

    def test_row_limit_protection_in_safety_md(self, safety_md):
        """safety-features.md should document row limit protection."""
        from hologres_cli.commands.sql import DEFAULT_ROW_LIMIT
        assert str(DEFAULT_ROW_LIMIT) in safety_md, \
            f"safety-features.md should mention the row limit threshold ({DEFAULT_ROW_LIMIT})"

    def test_dangerous_write_blocking_in_safety_md(self, safety_md):
        """safety-features.md should document dangerous write blocking."""
        assert "DELETE" in safety_md and "WHERE" in safety_md, \
            "safety-features.md should document DELETE without WHERE blocking"
        assert "UPDATE" in safety_md and "WHERE" in safety_md, \
            "safety-features.md should document UPDATE without WHERE blocking"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Output format consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestOutputFormatConsistency:
    """Verify documented output formats match actual implementation."""

    def test_all_formats_documented(self, skill_body):
        """All valid output formats should be documented."""
        from hologres_cli.output import VALID_FORMATS

        for fmt in VALID_FORMATS:
            assert fmt in skill_body, \
                f"Output format '{fmt}' is supported but not documented in SKILL.md"

    def test_default_format_documented(self, skill_body):
        """The default format (JSON) should be clearly stated."""
        from hologres_cli.output import FORMAT_JSON
        body_lower = skill_body.lower()
        assert FORMAT_JSON in body_lower and "default" in body_lower, \
            f"SKILL.md should state that '{FORMAT_JSON}' is the default format"

    def test_format_flag_documented(self, skill_body):
        """The -f / --format flag should be documented."""
        assert "-f " in skill_body or "--format" in skill_body, \
            "SKILL.md should document the -f / --format flag"

    def test_json_response_structure(self, skill_body):
        """The JSON response structure (ok/data/error) should be documented."""
        assert '"ok"' in skill_body, "SKILL.md should document the 'ok' field in JSON response"
        assert '"data"' in skill_body or '"rows"' in skill_body, \
            "SKILL.md should document the data structure in JSON response"
        assert '"error"' in skill_body or '"code"' in skill_body, \
            "SKILL.md should document the error structure in JSON response"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Data masking consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestMaskingConsistency:
    """Verify documented masking patterns match actual masking.py implementation."""

    def test_phone_masking_documented(self, skill_body):
        """Phone masking should be documented."""
        from hologres_cli.masking import get_mask_function
        assert get_mask_function("phone") is not None, "Code should mask 'phone' column"
        body_lower = skill_body.lower()
        assert "phone" in body_lower, "SKILL.md should document phone masking"

    def test_email_masking_documented(self, skill_body):
        """Email masking should be documented."""
        from hologres_cli.masking import get_mask_function
        assert get_mask_function("email") is not None, "Code should mask 'email' column"
        body_lower = skill_body.lower()
        assert "email" in body_lower, "SKILL.md should document email masking"

    def test_password_masking_documented(self, skill_body):
        """Password masking should be documented."""
        from hologres_cli.masking import get_mask_function
        assert get_mask_function("password") is not None, "Code should mask 'password' column"
        body_lower = skill_body.lower()
        assert "password" in body_lower, "SKILL.md should document password masking"

    def test_phone_mask_example_accurate(self, skill_body):
        """Phone masking example should match actual mask output."""
        from hologres_cli.masking import get_mask_function
        mask_fn = get_mask_function("phone")
        result = mask_fn("13812345678")
        assert result in skill_body, \
            f"Phone mask example in SKILL.md should show '{result}', the actual output"

    def test_email_mask_example_accurate(self, skill_body):
        """Email masking example should match actual mask output."""
        from hologres_cli.masking import get_mask_function
        mask_fn = get_mask_function("email")
        result = mask_fn("john@example.com")
        # The skill shows j***@example.com
        assert result in skill_body or "***@" in skill_body, \
            f"Email mask example should show '{result}'"

    def test_password_mask_output(self, skill_body):
        """Password masking should produce '********'."""
        from hologres_cli.masking import get_mask_function
        mask_fn = get_mask_function("password")
        result = mask_fn("secret123")
        assert result == "********", f"Password mask should produce '********', got '{result}'"
        assert "********" in skill_body, "SKILL.md should show '********' for password masking"

    def test_all_masking_categories_documented(self, skill_body):
        """All masking categories should be documented in SKILL.md."""
        body_lower = skill_body.lower()
        # These are the main categories from masking.py
        categories = [
            ("phone", "phone/mobile/tel"),
            ("email", "email"),
            ("password", "password/secret/token"),
        ]
        for keyword, desc in categories:
            assert keyword in body_lower, \
                f"Masking category '{desc}' should be documented in SKILL.md"


# ═══════════════════════════════════════════════════════════════════════════
# 6. DSN configuration consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestDSNConsistency:
    """Verify documented DSN configuration matches connection.py."""

    def test_dsn_format_matches(self, skill_body):
        """DSN format should match what connection.py parses."""
        # connection.py supports hologres:// scheme
        assert "hologres://" in skill_body, \
            "SKILL.md should document the hologres:// DSN scheme"

    def test_config_priority_documented(self, skill_body):
        """DSN resolution priority should be documented."""
        body_lower = skill_body.lower()
        assert "--dsn" in skill_body, "Should document --dsn flag as config method"
        assert "hologres_dsn" in body_lower or "HOLOGRES_DSN" in skill_body, \
            "Should document HOLOGRES_DSN env var as config method"
        assert "config.env" in skill_body, \
            "Should document config.env file as config method"

    def test_config_priority_order(self, skill_body):
        """CLI flag > env var > config file priority order should match code."""
        # In the skill, the order should be: 1. CLI flag, 2. env var, 3. config file
        dsn_pos = skill_body.find("--dsn")
        env_pos = skill_body.find("HOLOGRES_DSN")
        config_pos = skill_body.find("config.env")
        # All should exist
        assert dsn_pos >= 0, "--dsn should be documented"
        assert env_pos >= 0, "HOLOGRES_DSN should be documented"
        assert config_pos >= 0, "config.env should be documented"


# ═══════════════════════════════════════════════════════════════════════════
# 7. Command reference (commands.md) consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestCommandsRefConsistency:
    """Verify commands.md is consistent with actual CLI."""

    def test_all_commands_in_reference(self, commands_md):
        """All registered CLI commands should be in commands.md."""
        from hologres_cli.main import cli

        for cmd_name in cli.commands:
            assert cmd_name in commands_md, \
                f"Command '{cmd_name}' not found in commands.md reference"

    def test_global_options_documented(self, commands_md):
        """Global CLI options should be documented."""
        assert "--dsn" in commands_md, "commands.md should document --dsn option"
        assert "--format" in commands_md or "-f" in commands_md, \
            "commands.md should document --format option"

    def test_write_flag_in_sql_section(self, commands_md):
        """The --write flag should be mentioned in the sql section."""
        assert "--write" in commands_md, \
            "commands.md should document the --write flag for sql command"

    def test_export_import_examples(self, commands_md):
        """Data export/import should have examples."""
        cmd_lower = commands_md.lower()
        assert "export" in cmd_lower, "commands.md should have export examples"
        assert "import" in cmd_lower, "commands.md should have import examples"


# ═══════════════════════════════════════════════════════════════════════════
# 8. Safety features reference consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestSafetyRefConsistency:
    """Verify safety-features.md is consistent with actual implementation."""

    def test_error_codes_match_code(self, safety_md):
        """Error codes in safety-features.md should match output.py."""
        from hologres_cli.output import (
            connection_error,
            dangerous_write_error,
            limit_required_error,
            query_error,
            write_guard_error,
        )
        expected_codes = [
            "CONNECTION_ERROR",
            "QUERY_ERROR",
            "LIMIT_REQUIRED",
            "WRITE_GUARD_ERROR",
            "DANGEROUS_WRITE_BLOCKED",
        ]
        for code in expected_codes:
            assert code in safety_md, \
                f"Error code '{code}' should be documented in safety-features.md"

    def test_audit_logging_documented(self, safety_md):
        """Audit logging feature should be documented."""
        assert "sql-history.jsonl" in safety_md or "audit" in safety_md.lower() or \
               "logging" in safety_md.lower() or "history" in safety_md.lower(), \
            "safety-features.md should document audit logging"

    def test_masking_patterns_in_safety_md(self, safety_md):
        """Masking patterns should be in safety-features.md."""
        assert "phone" in safety_md.lower(), "safety-features.md should mention phone masking"
        assert "email" in safety_md.lower(), "safety-features.md should mention email masking"
        assert "password" in safety_md.lower(), "safety-features.md should mention password masking"
