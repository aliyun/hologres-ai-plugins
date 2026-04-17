"""Tests for schema command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


class TestTablesCmd:
    """Tests for schema tables command."""

    def test_tables_cmd_success(self, mock_get_connection):
        """Test successful tables list."""
        mock_get_connection.execute.return_value = [
            {"schema": "public", "table_name": "users", "owner": "admin"},
            {"schema": "public", "table_name": "orders", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "tables"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        mock_get_connection.close.assert_called_once()

    def test_tables_cmd_with_schema_filter(self, mock_get_connection):
        """Test tables list with schema filter."""
        mock_get_connection.execute.return_value = [
            {"schema": "myschema", "table_name": "mytable", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "tables", "--schema", "myschema"])

        assert result.exit_code == 0
        # Verify the SQL includes schema filter
        call_args = mock_get_connection.execute.call_args
        assert "myschema" in str(call_args)

    def test_tables_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.schema.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "tables"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_tables_cmd_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "tables"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_tables_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.return_value = [
            {"schema": "public", "table_name": "users", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "schema", "tables"])

        assert result.exit_code == 0
        assert "public" in result.output
        assert "users" in result.output


class TestDescribeCmd:
    """Tests for schema describe command."""

    def test_describe_cmd_success(self, mock_get_connection):
        """Test successful table describe."""
        mock_get_connection.execute.side_effect = [
            # Columns query result
            [
                {"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": None, "ordinal_position": 1, "comment": ""},
                {"column_name": "name", "data_type": "varchar", "is_nullable": "YES", "column_default": None, "ordinal_position": 2, "comment": ""},
            ],
            # Primary key query result
            [{"column_name": "id"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "describe", "users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["schema"] == "public"
        assert output["data"]["table"] == "users"
        assert len(output["data"]["columns"]) == 2

    def test_describe_cmd_with_schema(self, mock_get_connection):
        """Test describe with schema.table format."""
        mock_get_connection.execute.side_effect = [
            [{"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": None, "ordinal_position": 1, "comment": ""}],
            [],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "describe", "myschema.mytable"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["schema"] == "myschema"
        assert output["data"]["table"] == "mytable"

    def test_describe_cmd_table_not_found(self, mock_get_connection):
        """Test describe non-existent table."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "describe", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"

    def test_describe_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.schema.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "describe", "users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_describe_cmd_query_error(self, mock_get_connection):
        """Test query error during describe."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "describe", "users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"


class TestDumpCmd:
    """Tests for schema dump command."""

    def test_dump_cmd_success(self, mock_get_connection):
        """Test successful DDL dump."""
        mock_get_connection.execute.return_value = [
            {"hg_dump_script": "CREATE TABLE public.users (id integer PRIMARY KEY);"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "dump", "public.users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "CREATE TABLE" in output["data"]["ddl"]

    def test_dump_cmd_with_schema(self, mock_get_connection):
        """Test dump with schema.table format."""
        mock_get_connection.execute.return_value = [
            {"hg_dump_script": "CREATE TABLE myschema.mytable ..."}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "dump", "myschema.mytable"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["schema"] == "myschema"
        assert output["data"]["table"] == "mytable"

    def test_dump_cmd_table_not_found(self, mock_get_connection):
        """Test dump non-existent table."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "dump", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"

    def test_dump_cmd_table_format(self, mock_get_connection):
        """Test dump with table format outputs raw DDL."""
        mock_get_connection.execute.return_value = [
            {"hg_dump_script": "CREATE TABLE test (id INT);"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "schema", "dump", "test"])

        assert result.exit_code == 0
        assert "CREATE TABLE" in result.output

    def test_dump_cmd_query_error(self, mock_get_connection):
        """Test query error during dump."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "dump", "public.users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_dump_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.schema.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["schema", "dump", "public.users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"
