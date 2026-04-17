"""Tests for status command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


class TestStatusCmd:
    """Tests for status command."""

    def test_status_cmd_success(self, mock_get_connection):
        """Test successful status check."""
        mock_get_connection.execute.side_effect = [
            [{"version": "PostgreSQL 11.0 (Hologres)"}],
            [{"current_database": "testdb"}],
            [{"current_user": "testuser"}],
            [{"inet_server_addr": "127.0.0.1", "inet_server_port": 80}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["status"] == "connected"
        assert output["data"]["database"] == "testdb"
        assert output["data"]["user"] == "testuser"
        mock_get_connection.close.assert_called_once()

    def test_status_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.status.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["status"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_status_cmd_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["status"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_status_cmd_server_addr_error(self, mock_get_connection):
        """Test handling of server address query failure."""
        mock_get_connection.execute.side_effect = [
            [{"version": "PostgreSQL 11.0"}],
            [{"current_database": "testdb"}],
            [{"current_user": "testuser"}],
            Exception("Function not available"),  # inet_server_addr fails
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["status"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["server_address"] == "N/A"
        assert output["data"]["server_port"] == "N/A"

    def test_status_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.side_effect = [
            [{"version": "PostgreSQL 11.0"}],
            [{"current_database": "testdb"}],
            [{"current_user": "testuser"}],
            [{"inet_server_addr": "127.0.0.1", "inet_server_port": 80}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "status"])

        assert result.exit_code == 0
        assert "connected" in result.output
        assert "testdb" in result.output

    def test_status_cmd_masks_dsn(self, mock_get_connection):
        """Test that DSN is masked in output."""
        mock_get_connection.masked_dsn = "hologres://user:***@host/db"
        mock_get_connection.execute.side_effect = [
            [{"version": "PostgreSQL 11.0"}],
            [{"current_database": "testdb"}],
            [{"current_user": "testuser"}],
            [{"inet_server_addr": "127.0.0.1", "inet_server_port": 80}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["status"])

        output = json.loads(result.output)
        assert "***" in output["data"]["dsn"]
        assert "password" not in output["data"]["dsn"]
