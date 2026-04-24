"""Tests for table commands."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


class TestTableDumpCmd:
    """Tests for table dump command."""

    def test_dump_cmd_success(self, mock_get_connection):
        """Test successful DDL dump."""
        mock_get_connection.execute.return_value = [
            {"hg_dump_script": "CREATE TABLE public.users (id integer PRIMARY KEY);"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "dump", "public.users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "CREATE TABLE" in output["data"]["ddl"]
        assert output["data"]["schema"] == "public"
        assert output["data"]["table"] == "users"

    def test_dump_cmd_without_schema(self, mock_get_connection):
        """Test dump without schema defaults to public."""
        mock_get_connection.execute.return_value = [
            {"hg_dump_script": "CREATE TABLE public.users (id integer);"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "dump", "users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["schema"] == "public"
        assert output["data"]["table"] == "users"

    def test_dump_cmd_with_schema(self, mock_get_connection):
        """Test dump with schema.table format."""
        mock_get_connection.execute.return_value = [
            {"hg_dump_script": "CREATE TABLE myschema.mytable ..."}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "dump", "myschema.mytable"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["schema"] == "myschema"
        assert output["data"]["table"] == "mytable"

    def test_dump_cmd_table_not_found(self, mock_get_connection):
        """Test dump non-existent table."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "dump", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"

    def test_dump_cmd_table_format(self, mock_get_connection):
        """Test dump with table format outputs raw DDL."""
        mock_get_connection.execute.return_value = [
            {"hg_dump_script": "CREATE TABLE test (id INT);"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "table", "dump", "test"])

        assert result.exit_code == 0
        assert "CREATE TABLE" in result.output

    def test_dump_cmd_query_error(self, mock_get_connection):
        """Test query error during dump."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "dump", "public.users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_dump_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.schema.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "dump", "public.users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_dump_matches_schema_dump(self, mock_get_connection):
        """Test that table dump and schema dump produce identical output."""
        ddl_text = "CREATE TABLE public.users (id integer PRIMARY KEY);"
        mock_get_connection.execute.return_value = [
            {"hg_dump_script": ddl_text}
        ]

        runner = CliRunner()

        table_result = runner.invoke(cli, ["table", "dump", "public.users"])
        schema_result = runner.invoke(cli, ["schema", "dump", "public.users"])

        assert table_result.exit_code == 0
        assert schema_result.exit_code == 0
        assert json.loads(table_result.output) == json.loads(schema_result.output)
