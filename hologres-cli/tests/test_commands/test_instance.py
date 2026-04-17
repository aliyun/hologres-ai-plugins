"""Tests for instance command module."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli

SAMPLE_DSN = "hologres://testuser:testpass@example.hologres.aliyuncs.com:80/testdb"


@pytest.fixture
def mock_instance_conn(mocker):
    """Mock resolve_instance_dsn + HologresConnection for instance command."""
    from hologres_cli.connection import HologresConnection

    mock_conn = MagicMock(spec=HologresConnection)
    mock_conn.masked_dsn = "hologres://testuser:***@example.hologres.aliyuncs.com:80/testdb"
    mock_conn.execute.return_value = []
    mock_conn.close.return_value = None

    mocker.patch(
        "hologres_cli.commands.instance.resolve_instance_dsn",
        return_value=SAMPLE_DSN,
    )
    mocker.patch(
        "hologres_cli.commands.instance.HologresConnection",
        return_value=mock_conn,
    )
    return mock_conn


class TestInstanceCmd:
    """Tests for instance command."""

    def test_instance_cmd_success(self, mock_instance_conn):
        """Test successful instance query."""
        mock_instance_conn.execute.side_effect = [
            [{"hg_version": "Hologres 1.3.0"}],
            [{"instance_max_connections": 1000}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["instance", "my-instance"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["instance"] == "my-instance"
        assert output["data"]["hg_version"] == "Hologres 1.3.0"
        assert output["data"]["max_connections"] == 1000
        mock_instance_conn.close.assert_called_once()

    def test_instance_cmd_query_error(self, mock_instance_conn):
        """Test query error handling."""
        mock_instance_conn.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["instance", "my-instance"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_instance_cmd_empty_results(self, mock_instance_conn):
        """Test handling of empty query results."""
        mock_instance_conn.execute.side_effect = [
            [],  # Empty version result
            [],  # Empty max connections result
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["instance", "my-instance"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["hg_version"] == "Unknown"
        assert output["data"]["max_connections"] == "Unknown"

    def test_instance_cmd_table_format(self, mock_instance_conn):
        """Test table format output."""
        mock_instance_conn.execute.side_effect = [
            [{"hg_version": "Hologres 1.3.0"}],
            [{"instance_max_connections": 1000}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "instance", "my-instance"])

        assert result.exit_code == 0
        assert "Hologres" in result.output or "1000" in result.output


class TestInstanceDsnResolution:
    """Tests for instance DSN resolution from config and env."""

    def test_no_dsn_configured(self, mocker):
        """Test error when no DSN is configured for instance."""
        mocker.patch(
            "hologres_cli.commands.instance.resolve_instance_dsn",
            side_effect=DSNError("No DSN configured for instance 'unknown-inst'"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["instance", "unknown-inst"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"
        assert "unknown-inst" in output["error"]["message"]

    def test_dsn_from_env_variable(self, monkeypatch, mocker):
        """Test resolve_instance_dsn picks up HOLOGRES_DSN_<name> env var."""
        from hologres_cli.connection import resolve_instance_dsn

        monkeypatch.setenv("HOLOGRES_DSN_myinst", SAMPLE_DSN)
        resolved = resolve_instance_dsn("myinst")
        assert resolved == SAMPLE_DSN

    def test_dsn_from_config_file(self, tmp_path, monkeypatch, mocker):
        """Test resolve_instance_dsn reads from config.env."""
        # Ensure env var is not set
        monkeypatch.delenv("HOLOGRES_DSN_filetest", raising=False)

        # Create config file with instance DSN
        config_dir = tmp_path / ".hologres"
        config_dir.mkdir()
        config_file = config_dir / "config.env"
        config_file.write_text(f'HOLOGRES_DSN_filetest="{SAMPLE_DSN}"\n')

        # Patch CONFIG_FILE to point to our temp file
        mocker.patch("hologres_cli.connection.CONFIG_FILE", config_file)

        from hologres_cli.connection import resolve_instance_dsn
        resolved = resolve_instance_dsn("filetest")
        assert resolved == SAMPLE_DSN

    def test_dsn_env_takes_priority_over_config(self, tmp_path, monkeypatch, mocker):
        """Test env var takes priority over config file."""
        env_dsn = "hologres://envuser:envpass@envhost:80/envdb"
        file_dsn = "hologres://fileuser:filepass@filehost:80/filedb"

        monkeypatch.setenv("HOLOGRES_DSN_priority", env_dsn)

        config_dir = tmp_path / ".hologres"
        config_dir.mkdir()
        config_file = config_dir / "config.env"
        config_file.write_text(f'HOLOGRES_DSN_priority="{file_dsn}"\n')
        mocker.patch("hologres_cli.connection.CONFIG_FILE", config_file)

        from hologres_cli.connection import resolve_instance_dsn
        resolved = resolve_instance_dsn("priority")
        assert resolved == env_dsn

    def test_dsn_not_found_raises_error(self, tmp_path, monkeypatch, mocker):
        """Test DSNError raised when instance not in env or config."""
        monkeypatch.delenv("HOLOGRES_DSN_missing", raising=False)

        config_dir = tmp_path / ".hologres"
        config_dir.mkdir()
        config_file = config_dir / "config.env"
        config_file.write_text('HOLOGRES_DSN="hologres://default@host:80/db"\n')
        mocker.patch("hologres_cli.connection.CONFIG_FILE", config_file)

        from hologres_cli.connection import resolve_instance_dsn
        with pytest.raises(DSNError, match="No DSN configured for instance 'missing'"):
            resolve_instance_dsn("missing")

    def test_dsn_config_with_shell_escapes(self, tmp_path, monkeypatch, mocker):
        """Test config file DSN with shell escape characters."""
        monkeypatch.delenv("HOLOGRES_DSN_escaped", raising=False)

        config_dir = tmp_path / ".hologres"
        config_dir.mkdir()
        config_file = config_dir / "config.env"
        config_file.write_text(
            'HOLOGRES_DSN_escaped="hologres://BASIC\\$ops:pass@host:80/db"\n'
        )
        mocker.patch("hologres_cli.connection.CONFIG_FILE", config_file)

        from hologres_cli.connection import resolve_instance_dsn
        resolved = resolve_instance_dsn("escaped")
        assert "BASIC$ops" in resolved
        assert "\\$" not in resolved

    def test_missing_argument(self):
        """Test that instance_name argument is required."""
        runner = CliRunner()
        result = runner.invoke(cli, ["instance"])

        assert result.exit_code != 0
        assert "Missing argument" in result.output
