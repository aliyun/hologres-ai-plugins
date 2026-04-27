"""Tests for extension command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


class TestExtensionListCmd:
    """Tests for extension list command."""

    def test_list_success(self, mock_get_connection):
        """Test successful extension list."""
        mock_get_connection.execute.return_value = [
            {"name": "plpgsql", "version": "1.0", "schema": "pg_catalog"},
            {"name": "roaring_bitmap", "version": "0.5", "schema": "public"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 2
        assert output["data"]["count"] == 2
        mock_get_connection.close.assert_called_once()

    def test_list_empty_result(self, mock_get_connection):
        """Test extension list with no extensions."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_list_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.return_value = [
            {"name": "plpgsql", "version": "1.0", "schema": "pg_catalog"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "extension", "list"])

        assert result.exit_code == 0
        assert "plpgsql" in result.output
        assert "pg_catalog" in result.output

    def test_list_csv_format(self, mock_get_connection):
        """Test CSV format output."""
        mock_get_connection.execute.return_value = [
            {"name": "plpgsql", "version": "1.0", "schema": "pg_catalog"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "csv", "extension", "list"])

        assert result.exit_code == 0
        assert "name" in result.output
        assert "plpgsql" in result.output

    def test_list_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.extension.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_list_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_list_logs_operation_on_success(self, mock_get_connection, mocker):
        """Test that successful list logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.extension.log_operation")
        mock_get_connection.execute.return_value = [
            {"name": "plpgsql", "version": "1.0", "schema": "pg_catalog"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "list"])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[0][0] == "extension.list"

    def test_list_logs_operation_on_failure(self, mock_get_connection, mocker):
        """Test that failed list logs operation with error."""
        mock_log = mocker.patch("hologres_cli.commands.extension.log_operation")
        mock_get_connection.execute.side_effect = Exception("DB error")

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "list"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"

    def test_list_connection_closed(self, mock_get_connection):
        """Test that connection is closed after list."""
        mock_get_connection.execute.return_value = [
            {"name": "plpgsql", "version": "1.0", "schema": "pg_catalog"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "list"])

        assert result.exit_code == 0
        mock_get_connection.close.assert_called_once()


class TestExtensionCreateCmd:
    """Tests for extension create command."""

    def test_create_success(self, mock_get_connection):
        """Test successful extension creation."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "roaring_bitmap"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["extension"] == "roaring_bitmap"
        assert output["data"]["created"] is True
        mock_get_connection.close.assert_called_once()

    def test_create_with_if_not_exists(self, mock_get_connection):
        """Test create with --if-not-exists flag."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "postgis", "--if-not-exists"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        # Verify SQL contains IF NOT EXISTS
        call_args = mock_get_connection.execute.call_args
        executed_sql = call_args[0][0]
        assert "IF NOT EXISTS" in executed_sql

    def test_create_without_if_not_exists(self, mock_get_connection):
        """Test create without --if-not-exists flag."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "hstore"])

        assert result.exit_code == 0
        # Verify SQL does NOT contain IF NOT EXISTS
        call_args = mock_get_connection.execute.call_args
        executed_sql = call_args[0][0]
        assert "IF NOT EXISTS" not in executed_sql

    def test_create_invalid_identifier(self, mock_get_connection):
        """Test create with invalid extension name (SQL injection attempt)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "bad;name"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_create_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.extension.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "roaring_bitmap"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_create_query_error(self, mock_get_connection):
        """Test query error during create."""
        mock_get_connection.execute.side_effect = Exception("Extension not found")

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "nonexistent_ext"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_create_logs_operation_on_success(self, mock_get_connection, mocker):
        """Test that successful create logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.extension.log_operation")
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "roaring_bitmap"])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[0][0] == "extension.create"

    def test_create_logs_operation_on_failure(self, mock_get_connection, mocker):
        """Test that failed create logs operation with error."""
        mock_log = mocker.patch("hologres_cli.commands.extension.log_operation")
        mock_get_connection.execute.side_effect = Exception("DB error")

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "roaring_bitmap"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"

    def test_create_connection_closed(self, mock_get_connection):
        """Test that connection is closed after create."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "roaring_bitmap"])

        assert result.exit_code == 0
        mock_get_connection.close.assert_called_once()

    def test_create_json_output_format(self, mock_get_connection):
        """Test JSON output format for create."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "roaring_bitmap"])

        output = json.loads(result.output)
        assert output == {"ok": True, "data": {"extension": "roaring_bitmap", "created": True}}

    def test_create_table_format(self, mock_get_connection):
        """Test table format output for create."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "extension", "create", "roaring_bitmap"])

        assert result.exit_code == 0
        assert "roaring_bitmap" in result.output

    def test_create_sql_uses_identifier_quoting(self, mock_get_connection):
        """Test that extension name is properly quoted via psycopg.sql.Identifier."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["extension", "create", "hologres_fdw"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        executed_sql = call_args[0][0]
        # psycopg.sql.Identifier quotes the name with double quotes
        assert '"hologres_fdw"' in executed_sql
