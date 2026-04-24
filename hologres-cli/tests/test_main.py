"""Tests for main module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import _generate_ai_guide, cli, main


class TestGenerateAiGuide:
    """Tests for _generate_ai_guide function."""

    def test_generate_ai_guide_content(self):
        """Test guide is non-empty string."""
        result = _generate_ai_guide()
        assert isinstance(result, str)
        assert len(result) > 0

    def test_generate_ai_guide_has_commands(self):
        """Test guide contains command references."""
        result = _generate_ai_guide()
        assert "schema tables" in result
        assert "schema describe" in result
        assert "sql" in result
        assert "status" in result
        assert "config" in result

    def test_generate_ai_guide_has_safety(self):
        """Test guide contains safety information."""
        result = _generate_ai_guide()
        assert "LIMIT" in result
        assert "--write" in result
        assert "WHERE" in result

    def test_generate_ai_guide_has_format_info(self):
        """Test guide contains format information."""
        result = _generate_ai_guide()
        assert "json" in result
        assert "table" in result
        assert "csv" in result

    def test_generate_ai_guide_no_dsn(self):
        """Test guide mentions config instead of DSN."""
        result = _generate_ai_guide()
        assert "config" in result
        assert "--profile" in result


class TestCli:
    """Tests for CLI main group."""

    def test_cli_version(self):
        """Test --version flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "0.1.0" in result.output

    def test_cli_help(self):
        """Test --help flag."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Hologres CLI" in result.output
        assert "schema" in result.output
        assert "sql" in result.output
        assert "config" in result.output

    def test_cli_help_no_dsn(self):
        """Test --help does not show --dsn option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "--dsn" not in result.output
        assert "--profile" in result.output

    def test_cli_format_option(self):
        """Test --format option sets context."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "ai-guide"])
        assert result.exit_code == 0

    def test_cli_profile_option(self):
        """Test --profile option sets context."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--profile", "default", "ai-guide"])
        assert result.exit_code == 0


class TestAiGuideCmd:
    """Tests for ai-guide command."""

    def test_ai_guide_json_format(self):
        """Test JSON format output."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "json", "ai-guide"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["ok"] is True
        assert "guide" in data["data"]

    def test_ai_guide_table_format(self):
        """Test table format output (plain text)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "ai-guide"])
        assert result.exit_code == 0
        assert "Hologres CLI" in result.output


class TestHistoryCmd:
    """Tests for history command."""

    def test_history_cmd_empty(self, mock_home):
        """Test history with no logs."""
        runner = CliRunner()
        result = runner.invoke(cli, ["history"])
        assert result.exit_code == 0

    def test_history_cmd_with_count(self, mock_home):
        """Test history with count option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["history", "--count", "5"])
        assert result.exit_code == 0


class TestMain:
    """Tests for main function."""

    def test_main_dsn_error(self, monkeypatch, capsys):
        """Test main handles DSNError."""
        def mock_cli(**kwargs):
            raise DSNError("No profile configured")

        monkeypatch.setattr("hologres_cli.main.cli", mock_cli)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_main_internal_error(self, monkeypatch, capsys):
        """Test main handles unexpected exceptions."""
        def mock_cli(**kwargs):
            raise RuntimeError("Unexpected error")

        monkeypatch.setattr("hologres_cli.main.cli", mock_cli)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        output = json.loads(captured.out)
        assert output["ok"] is False
        assert output["error"]["code"] == "INTERNAL_ERROR"


class TestSubcommands:
    """Tests for subcommand registration."""

    def test_schema_command_registered(self):
        """Test schema command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "--help"])
        assert result.exit_code == 0
        assert "tables" in result.output
        assert "describe" in result.output

    def test_sql_command_registered(self):
        """Test sql command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "--help"])
        assert result.exit_code == 0
        assert "QUERY" in result.output

    def test_data_command_registered(self):
        """Test data command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["data", "--help"])
        assert result.exit_code == 0
        assert "export" in result.output
        assert "import" in result.output

    def test_status_command_registered(self):
        """Test status command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--help"])
        assert result.exit_code == 0

    def test_instance_command_registered(self):
        """Test instance command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["instance", "--help"])
        assert result.exit_code == 0

    def test_warehouse_command_registered(self):
        """Test warehouse command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["warehouse", "--help"])
        assert result.exit_code == 0

    def test_config_command_registered(self):
        """Test config command is registered."""
        runner = CliRunner()
        result = runner.invoke(cli, ["config", "--help"])
        assert result.exit_code == 0
        assert "set" in result.output
        assert "get" in result.output
        assert "list" in result.output
