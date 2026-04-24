"""Tests for instance command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


class TestInstanceCmd:
    """Tests for instance command."""

    def test_instance_cmd_success(self, mock_get_connection):
        """Test successful instance query."""
        mock_get_connection.execute.side_effect = [
            [{"hg_version": "Hologres 1.3.0"}],
            [{"instance_max_connections": 1000}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["instance"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["hg_version"] == "Hologres 1.3.0"
        assert output["data"]["max_connections"] == 1000
        mock_get_connection.close.assert_called_once()

    def test_instance_cmd_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["instance"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_instance_cmd_empty_results(self, mock_get_connection):
        """Test handling of empty query results."""
        mock_get_connection.execute.side_effect = [
            [],  # Empty version result
            [],  # Empty max connections result
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["instance"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["hg_version"] == "Unknown"
        assert output["data"]["max_connections"] == "Unknown"

    def test_instance_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.side_effect = [
            [{"hg_version": "Hologres 1.3.0"}],
            [{"instance_max_connections": 1000}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "instance"])

        assert result.exit_code == 0
        assert "Hologres" in result.output or "1000" in result.output

    def test_instance_cmd_with_profile(self, mock_get_connection):
        """Test instance command with --profile option."""
        mock_get_connection.execute.side_effect = [
            [{"hg_version": "Hologres 1.3.0"}],
            [{"instance_max_connections": 500}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--profile", "prod", "instance"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_instance_no_argument_required(self):
        """Test that instance command no longer requires an argument."""
        runner = CliRunner()
        result = runner.invoke(cli, ["instance", "--help"])
        assert result.exit_code == 0
        # Should not have positional arguments
        assert "INSTANCE_NAME" not in result.output
