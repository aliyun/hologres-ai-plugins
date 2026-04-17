"""Integration tests for status command with real Hologres database."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


@pytest.mark.integration
class TestStatusLive:
    """Integration tests for status command."""

    def test_status_connected(self, integration_dsn):
        """Test status shows connected with server info."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--dsn", integration_dsn, "status"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["status"] == "connected"
        assert "version" in output["data"]
        assert "database" in output["data"]
        assert "user" in output["data"]

    def test_status_table_format(self, integration_dsn):
        """Test status with table format output."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--dsn", integration_dsn, "--format", "table", "status"]
        )

        assert result.exit_code == 0
        assert "connected" in result.output

    def test_status_connection_error(self, monkeypatch):
        """Test status with invalid DSN returns connection error."""
        monkeypatch.delenv("HOLOGRES_TEST_DSN", raising=False)
        runner = CliRunner()
        result = runner.invoke(cli, ["--dsn", "http://invalid", "status"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"
