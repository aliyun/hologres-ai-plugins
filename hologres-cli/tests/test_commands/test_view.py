"""Tests for view command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


MOCK_VIEW_ROWS = [
    {"schema": "public", "view_name": "active_users", "owner": "admin"},
    {"schema": "analytics", "view_name": "daily_stats", "owner": "analyst"},
]


class TestViewListCmd:
    """Tests for view list command."""

    def test_list_cmd_success(self, mock_get_connection):
        """Test successful view list."""
        mock_get_connection.execute.return_value = MOCK_VIEW_ROWS

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 2
        mock_get_connection.close.assert_called_once()

    def test_list_cmd_with_schema(self, mock_get_connection):
        """Test view list with --schema filter."""
        mock_get_connection.execute.return_value = [
            {"schema": "public", "view_name": "active_users", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list", "--schema", "public"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert "public" in str(call_args)

    def test_list_cmd_short_flag(self, mock_get_connection):
        """Test view list with -s short flag."""
        mock_get_connection.execute.return_value = [
            {"schema": "myschema", "view_name": "my_view", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list", "-s", "myschema"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert "myschema" in str(call_args)

    def test_list_cmd_empty_result(self, mock_get_connection):
        """Test view list with no views."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_list_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.return_value = MOCK_VIEW_ROWS

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "view", "list"])

        assert result.exit_code == 0
        assert "public" in result.output
        assert "active_users" in result.output

    def test_list_cmd_csv_format(self, mock_get_connection):
        """Test CSV format output."""
        mock_get_connection.execute.return_value = MOCK_VIEW_ROWS

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "csv", "view", "list"])

        assert result.exit_code == 0
        assert "public" in result.output
        assert "active_users" in result.output

    def test_list_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.view.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_list_cmd_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_list_cmd_logging_success(self, mock_get_connection, mocker):
        """Test that successful list logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.view.log_operation")
        mock_get_connection.execute.return_value = MOCK_VIEW_ROWS

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list"])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert "view.list" in str(call_kwargs)

    def test_list_cmd_sql_uses_inline_not_in(self, mock_get_connection):
        """Test that view list SQL uses inline NOT IN literals, not parameterized tuple.

        psycopg3 does not support NOT IN %s with a tuple parameter — it produces
        invalid SQL like 'NOT IN $1'. The system schema names must be inlined.
        """
        mock_get_connection.execute.return_value = MOCK_VIEW_ROWS

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        sql_arg = call_args[0][0]
        # SQL should contain inline NOT IN with literal schema names
        assert "NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hg_internal')" in sql_arg
        # SQL should NOT contain parameterized NOT IN %s
        assert "NOT IN %s" not in sql_arg
        # params should not contain a tuple element
        params_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", ())
        for p in (params_arg or ()):
            assert not isinstance(p, tuple)

    def test_list_cmd_with_schema_sql_params(self, mock_get_connection):
        """Test that view list with --schema passes correct params without tuple elements."""
        mock_get_connection.execute.return_value = [
            {"schema": "public", "view_name": "active_users", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list", "--schema", "public"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        sql_arg = call_args[0][0]
        params_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1].get("params", ())
        # SQL should contain inline NOT IN
        assert "NOT IN ('pg_catalog', 'information_schema', 'hologres', 'hg_internal')" in sql_arg
        # params should only contain the schema name string, no tuple
        assert "public" in str(params_arg)
        for p in (params_arg or ()):
            assert not isinstance(p, tuple)

    def test_list_cmd_logging_failure(self, mock_get_connection, mocker):
        """Test that failed list logs operation with error."""
        mock_log = mocker.patch("hologres_cli.commands.view.log_operation")
        mock_get_connection.execute.side_effect = Exception("DB error")

        runner = CliRunner()
        result = runner.invoke(cli, ["view", "list"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"
