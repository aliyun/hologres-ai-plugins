"""Tests for GUC parameter management commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


class TestGucShowCmd:
    """Tests for guc show command."""

    def test_show_cmd_success(self, mock_get_connection):
        """Test successful GUC parameter show."""
        mock_get_connection.execute.return_value = [
            {"optimizer_join_order": "exhaustive"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "show", "optimizer_join_order"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["param"] == "optimizer_join_order"
        assert output["data"]["value"] == "exhaustive"
        mock_get_connection.close.assert_called_once()

    def test_show_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.return_value = [
            {"optimizer_join_order": "exhaustive"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "guc", "show", "optimizer_join_order"])

        assert result.exit_code == 0
        assert "optimizer_join_order" in result.output
        assert "exhaustive" in result.output

    def test_show_cmd_csv_format(self, mock_get_connection):
        """Test CSV format output."""
        mock_get_connection.execute.return_value = [
            {"optimizer_join_order": "exhaustive"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "csv", "guc", "show", "optimizer_join_order"])

        assert result.exit_code == 0
        assert "optimizer_join_order" in result.output
        assert "exhaustive" in result.output

    def test_show_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.guc.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "show", "optimizer_join_order"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_show_cmd_query_error(self, mock_get_connection):
        """Test query error handling (e.g., unknown parameter)."""
        mock_get_connection.execute.side_effect = Exception(
            'unrecognized configuration parameter "bad_param"'
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "show", "bad_param"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_show_cmd_logging_success(self, mock_get_connection, mocker):
        """Test that successful show logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.guc.log_operation")
        mock_get_connection.execute.return_value = [
            {"statement_timeout": "0"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "show", "statement_timeout"])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[0][0] == "guc.show"

    def test_show_cmd_logging_failure(self, mock_get_connection, mocker):
        """Test that failed show logs operation with error."""
        mock_log = mocker.patch("hologres_cli.commands.guc.log_operation")
        mock_get_connection.execute.side_effect = Exception("DB error")

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "show", "bad_param"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"

    def test_show_cmd_connection_closed(self, mock_get_connection):
        """Test that connection is closed after show."""
        mock_get_connection.execute.return_value = [
            {"server_version": "14.0"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "show", "server_version"])

        assert result.exit_code == 0
        mock_get_connection.close.assert_called_once()

    def test_show_cmd_invalid_identifier(self, mock_get_connection):
        """Test show with invalid parameter name (SQL injection attempt)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "show", "bad;name"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_show_cmd_uses_identifier_quoting(self, mock_get_connection):
        """Test that parameter name is properly quoted via psycopg.sql.Identifier."""
        mock_get_connection.execute.return_value = [
            {"optimizer_join_order": "exhaustive"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "show", "optimizer_join_order"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        executed_sql = call_args[0][0]
        assert '"optimizer_join_order"' in executed_sql


class TestGucSetCmd:
    """Tests for guc set command."""

    def test_set_cmd_success_database_scope(self, mock_get_connection):
        """Test successful GUC parameter set at database level (default)."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "optimizer_join_order", "query"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["param"] == "optimizer_join_order"
        assert output["data"]["value"] == "query"
        assert output["data"]["scope"] == "database"
        assert output["data"]["database"] == "testdb"
        mock_get_connection.close.assert_called_once()

    def test_set_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "guc", "set",
                                     "optimizer_join_order", "query"])

        assert result.exit_code == 0
        assert "optimizer_join_order" in result.output
        assert "query" in result.output
        assert "database" in result.output

    def test_set_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.guc.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "optimizer_join_order", "query"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_set_cmd_query_error(self, mock_get_connection):
        """Test query error handling (e.g., permission denied)."""
        mock_get_connection.execute.side_effect = Exception("permission denied")
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "optimizer_join_order", "query"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_set_cmd_logging_success(self, mock_get_connection, mocker):
        """Test that successful set logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.guc.log_operation")
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "optimizer_join_order", "query"])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[0][0] == "guc.set"

    def test_set_cmd_logging_failure(self, mock_get_connection, mocker):
        """Test that failed set logs operation with error."""
        mock_log = mocker.patch("hologres_cli.commands.guc.log_operation")
        mock_get_connection.execute.side_effect = Exception("DB error")
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "optimizer_join_order", "query"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"

    def test_set_cmd_connection_closed(self, mock_get_connection):
        """Test that connection is closed after set."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "optimizer_join_order", "query"])

        assert result.exit_code == 0
        mock_get_connection.close.assert_called_once()

    def test_set_cmd_invalid_identifier(self, mock_get_connection):
        """Test set with invalid parameter name."""
        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "bad;name", "value"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_set_cmd_uses_identifier_quoting(self, mock_get_connection):
        """Test that ALTER DATABASE SQL uses identifier quoting for dbname and param."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "optimizer_join_order", "query"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        executed_sql = call_args[0][0]
        assert '"testdb"' in executed_sql
        assert '"optimizer_join_order"' in executed_sql
        assert "ALTER DATABASE" in executed_sql
        assert "SET" in executed_sql
        assert "$1" not in executed_sql

    def test_set_cmd_value_uses_literal(self, mock_get_connection):
        """Test that the parameter value is rendered via psycopg.sql.Literal."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "optimizer_join_order", "query"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert len(call_args[0]) == 1 or call_args[0][1] is None
        executed_sql = call_args[0][0]
        assert "$1" not in executed_sql

    def test_set_cmd_returns_scope_info(self, mock_get_connection):
        """Test that set returns scope=database and actual database name."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "my_hologres_db"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "statement_timeout", "5min"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["scope"] == "database"
        assert output["data"]["database"] == "my_hologres_db"

    def test_set_cmd_json_output_format(self, mock_get_connection):
        """Test JSON output format for set."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "optimizer_join_order", "query"])

        output = json.loads(result.output)
        assert output == {
            "ok": True,
            "data": {
                "param": "optimizer_join_order",
                "value": "query",
                "scope": "database",
                "database": "testdb",
            }
        }

    def test_set_cmd_value_off_rendered_as_literal(self, mock_get_connection):
        """Test that 'off' value is rendered without $1 placeholder."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "hg_experimental_enable_fse_common_table", "off"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        executed_sql = call_args[0][0]
        assert "$1" not in executed_sql

    def test_set_cmd_value_with_special_chars(self, mock_get_connection):
        """Test that value with special chars does not cause $1 placeholder."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "set", "statement_timeout", "5 min"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        executed_sql = call_args[0][0]
        assert "$1" not in executed_sql


class TestGucResetCmd:
    """Tests for guc reset command."""

    def test_reset_cmd_database_scope(self, mock_get_connection):
        """Test reset at database level (default)."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "reset", "statement_timeout"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["param"] == "statement_timeout"
        assert output["data"]["reset"] is True
        assert output["data"]["scope"] == "database"
        assert output["data"]["database"] == "testdb"

        call_args = mock_get_connection.execute.call_args
        executed_sql = call_args[0][0]
        assert "ALTER DATABASE" in executed_sql
        assert "RESET" in executed_sql
        assert '"statement_timeout"' in executed_sql
        mock_get_connection.close.assert_called_once()

    def test_reset_cmd_table_format_database(self, mock_get_connection):
        """Test table format output for database scope reset."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "guc", "reset",
                                     "statement_timeout"])

        assert result.exit_code == 0
        assert "reset to default" in result.output
        assert "database level" in result.output

    def test_reset_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.guc.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "reset", "statement_timeout"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_reset_cmd_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("permission denied")
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "reset", "bad_param"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_reset_cmd_invalid_identifier(self, mock_get_connection):
        """Test reset with invalid parameter name."""
        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "reset", "bad;name"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_reset_cmd_logging_success(self, mock_get_connection, mocker):
        """Test that successful reset logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.guc.log_operation")
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "reset", "statement_timeout"])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[0][0] == "guc.reset"

    def test_reset_cmd_logging_failure(self, mock_get_connection, mocker):
        """Test that failed reset logs operation with error."""
        mock_log = mocker.patch("hologres_cli.commands.guc.log_operation")
        mock_get_connection.execute.side_effect = Exception("DB error")
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "reset", "statement_timeout"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"

    def test_reset_cmd_connection_closed(self, mock_get_connection):
        """Test that connection is closed after reset."""
        mock_get_connection.execute.return_value = []
        mock_get_connection.database = "testdb"

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "reset", "statement_timeout"])

        assert result.exit_code == 0
        mock_get_connection.close.assert_called_once()


class TestGucListCmd:
    """Tests for guc list command."""

    def test_list_cmd_success(self, mock_get_connection):
        """Test successful GUC parameter listing."""
        mock_get_connection.execute.return_value = [
            {"hg_enable_start_auto_analyze_worker": "on"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) > 0
        mock_get_connection.close.assert_called_once()

    def test_list_cmd_with_filter(self, mock_get_connection):
        """Test list with keyword filter."""
        mock_get_connection.execute.return_value = [
            {"statement_timeout": "8h"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "list", "--filter", "timeout"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        rows = output["data"]["rows"]
        for row in rows:
            assert "timeout" in row["param"].lower()

    def test_list_cmd_filter_no_match(self, mock_get_connection):
        """Test list with filter that matches nothing."""
        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "list", "--filter", "zzzznonexistent"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 0

    def test_list_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.guc.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_list_cmd_handles_unavailable_params(self, mock_get_connection):
        """Test that list gracefully handles params that fail to query."""
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count % 2 == 0:
                raise Exception("unrecognized parameter")
            return [{"value": "on"}]

        mock_get_connection.execute.side_effect = side_effect

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        rows = output["data"]["rows"]
        has_not_available = any(r["value"] == "(not available)" for r in rows)
        assert has_not_available

    def test_list_cmd_logging(self, mock_get_connection, mocker):
        """Test that list logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.guc.log_operation")
        mock_get_connection.execute.return_value = [{"value": "on"}]

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "list"])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[0][0] == "guc.list"

    def test_list_cmd_connection_closed(self, mock_get_connection):
        """Test that connection is closed after list."""
        mock_get_connection.execute.return_value = [{"value": "on"}]

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "list"])

        assert result.exit_code == 0
        mock_get_connection.close.assert_called_once()

    def test_list_cmd_filter_short_option(self, mock_get_connection):
        """Test list with -q short option."""
        mock_get_connection.execute.return_value = [
            {"optimizer_join_order": "exhaustive"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["guc", "list", "-q", "optimizer"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        rows = output["data"]["rows"]
        for row in rows:
            assert "optimizer" in row["param"].lower()
