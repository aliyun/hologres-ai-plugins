"""Tests for table command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

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


class TestTableListCmd:
    """Tests for table list command."""

    def test_list_success(self, mock_get_connection):
        """Test successful table list."""
        mock_get_connection.execute.return_value = [
            {"schema": "public", "table_name": "users", "owner": "admin"},
            {"schema": "public", "table_name": "orders", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 2
        mock_get_connection.close.assert_called_once()

    def test_list_with_schema_filter(self, mock_get_connection):
        """Test table list with schema filter."""
        mock_get_connection.execute.return_value = [
            {"schema": "myschema", "table_name": "mytable", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "list", "--schema", "myschema"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert "myschema" in str(call_args)

    def test_list_with_short_schema_flag(self, mock_get_connection):
        """Test table list with -s short flag."""
        mock_get_connection.execute.return_value = [
            {"schema": "myschema", "table_name": "mytable", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "list", "-s", "myschema"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert "myschema" in str(call_args)

    def test_list_empty_result(self, mock_get_connection):
        """Test table list with no tables."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "list"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_list_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.return_value = [
            {"schema": "public", "table_name": "users", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "table", "list"])

        assert result.exit_code == 0
        assert "public" in result.output
        assert "users" in result.output

    def test_list_csv_format(self, mock_get_connection):
        """Test CSV format output."""
        mock_get_connection.execute.return_value = [
            {"schema": "public", "table_name": "users", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "csv", "table", "list"])

        assert result.exit_code == 0
        assert "public" in result.output
        assert "users" in result.output

    def test_list_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.schema.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_list_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "list"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_list_logs_operation_on_success(self, mock_get_connection, mocker):
        """Test that successful list logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.schema.log_operation")
        mock_get_connection.execute.return_value = [
            {"schema": "public", "table_name": "t1", "owner": "admin"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "list"])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert "table.list" in str(call_kwargs)

    def test_list_logs_operation_on_failure(self, mock_get_connection, mocker):
        """Test that failed list logs operation with error."""
        mock_log = mocker.patch("hologres_cli.commands.schema.log_operation")
        mock_get_connection.execute.side_effect = Exception("DB error")

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "list"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"


class TestShowCmd:
    """Tests for table show command."""

    def test_show_cmd_success(self, mock_get_connection):
        """Test successful table show."""
        mock_get_connection.execute.side_effect = [
            # Columns query result
            [
                {"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": None, "ordinal_position": 1, "comment": "primary id"},
                {"column_name": "name", "data_type": "text", "is_nullable": "YES", "column_default": None, "ordinal_position": 2, "comment": "user name"},
            ],
            # Primary key query result
            [{"column_name": "id"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "show", "users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["schema"] == "public"
        assert output["data"]["table"] == "users"
        assert output["data"]["primary_key"] == ["id"]
        assert len(output["data"]["columns"]) == 2
        mock_get_connection.close.assert_called_once()

    def test_show_cmd_with_schema(self, mock_get_connection):
        """Test show with schema.table format."""
        mock_get_connection.execute.side_effect = [
            [{"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": None, "ordinal_position": 1, "comment": ""}],
            [],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "show", "myschema.mytable"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["schema"] == "myschema"
        assert output["data"]["table"] == "mytable"

    def test_show_cmd_table_not_found(self, mock_get_connection):
        """Test show non-existent table."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "show", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"

    def test_show_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.table.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "show", "users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_show_cmd_query_error(self, mock_get_connection):
        """Test query error during show."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "show", "users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_show_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.side_effect = [
            [
                {"column_name": "id", "data_type": "integer", "is_nullable": "NO", "column_default": None, "ordinal_position": 1, "comment": ""},
            ],
            [{"column_name": "id"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "table", "show", "users"])

        assert result.exit_code == 0
        assert "id" in result.output
        assert "integer" in result.output

    def test_show_cmd_no_pk(self, mock_get_connection):
        """Test show table with no primary key."""
        mock_get_connection.execute.side_effect = [
            [
                {"column_name": "col1", "data_type": "text", "is_nullable": "YES", "column_default": None, "ordinal_position": 1, "comment": ""},
            ],
            [],  # No primary key
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "show", "no_pk_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["primary_key"] == []


class TestTableSizeCmd:
    """Tests for table size command."""

    def test_size_cmd_success(self, mock_get_connection):
        """Test successful table size query."""
        mock_get_connection.execute.return_value = [
            {"size": "123 MB", "size_bytes": 128974848}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "size", "public.users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["schema"] == "public"
        assert output["data"]["table"] == "users"
        assert output["data"]["size"] == "123 MB"
        assert output["data"]["size_bytes"] == 128974848
        mock_get_connection.close.assert_called_once()

    def test_size_cmd_without_schema(self, mock_get_connection):
        """Test size without schema defaults to public."""
        mock_get_connection.execute.return_value = [
            {"size": "56 kB", "size_bytes": 57344}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "size", "users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["schema"] == "public"
        assert output["data"]["table"] == "users"

    def test_size_cmd_with_schema(self, mock_get_connection):
        """Test size with schema.table format."""
        mock_get_connection.execute.return_value = [
            {"size": "0 bytes", "size_bytes": 0}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "size", "myschema.mytable"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["schema"] == "myschema"
        assert output["data"]["table"] == "mytable"

    def test_size_cmd_table_not_found(self, mock_get_connection):
        """Test size of non-existent table."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "size", "public.nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"

    def test_size_cmd_invalid_identifier(self, mock_get_connection):
        """Test size with invalid identifier (SQL injection attempt)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "size", "public.bad;table"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_size_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.schema.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "size", "public.users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_size_cmd_query_error(self, mock_get_connection):
        """Test query error during size."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "size", "public.users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_size_cmd_non_json_format(self, mock_get_connection):
        """Test size with non-JSON format output."""
        mock_get_connection.execute.return_value = [
            {"size": "123 MB", "size_bytes": 128974848}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "csv", "table", "size", "public.users"])

        assert result.exit_code == 0
        assert "public.users: 123 MB" in result.output

    def test_size_cmd_uses_string_param(self, mock_get_connection):
        """Test that size command uses parameterized string query, not SQL identifier."""
        mock_get_connection.execute.return_value = [
            {"size": "123 MB", "size_bytes": 128974848}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "size", "public.users"])

        assert result.exit_code == 0
        # Verify execute was called with parameterized query
        call_args = mock_get_connection.execute.call_args
        sql_str = call_args[0][0]
        params = call_args[0][1]
        assert "%s" in sql_str
        assert params == ("public.users", "public.users")
        # Ensure no double-quoted identifiers in SQL
        assert '"public"' not in sql_str
        assert '"users"' not in sql_str

    def test_size_cmd_uses_string_param_with_schema(self, mock_get_connection):
        """Test that schema.table format also uses parameterized string query."""
        mock_get_connection.execute.return_value = [
            {"size": "0 bytes", "size_bytes": 0}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "size", "myschema.mytable"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        params = call_args[0][1]
        assert params == ("myschema.mytable", "myschema.mytable")

    def test_size_matches_schema_size(self, mock_get_connection):
        """Test that table size and schema size produce identical output."""
        mock_get_connection.execute.return_value = [
            {"size": "123 MB", "size_bytes": 128974848}
        ]

        runner = CliRunner()

        table_result = runner.invoke(cli, ["table", "size", "public.users"])
        schema_result = runner.invoke(cli, ["schema", "size", "public.users"])

        assert table_result.exit_code == 0
        assert schema_result.exit_code == 0
        assert json.loads(table_result.output) == json.loads(schema_result.output)


class TestTablePropertiesCmd:
    """Tests for table properties command."""

    def test_properties_cmd_success(self, mock_get_connection):
        """Test successful table properties query."""
        mock_get_connection.execute.return_value = [
            {"property_key": "clustering_key", "property_value": "created_at:asc"},
            {"property_key": "distribution_key", "property_value": "user_id"},
            {"property_key": "orientation", "property_value": "column"},
            {"property_key": "time_to_live_in_seconds", "property_value": "2592000"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "public.users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 4
        assert len(output["data"]["rows"]) == 4
        mock_get_connection.close.assert_called_once()

    def test_properties_cmd_without_schema(self, mock_get_connection):
        """Test properties without schema defaults to public."""
        mock_get_connection.execute.return_value = [
            {"property_key": "orientation", "property_value": "column"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "users"])

        assert result.exit_code == 0
        # Verify "public" was passed as table_namespace
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][1] == ("public", "users")

    def test_properties_cmd_with_schema(self, mock_get_connection):
        """Test properties with schema.table format."""
        mock_get_connection.execute.return_value = [
            {"property_key": "orientation", "property_value": "column"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "myschema.orders"])

        assert result.exit_code == 0
        call_args = mock_get_connection.execute.call_args
        assert call_args[0][1] == ("myschema", "orders")

    def test_properties_cmd_table_not_found(self, mock_get_connection):
        """Test properties for non-existent table."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "public.nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"

    def test_properties_cmd_invalid_identifier(self, mock_get_connection):
        """Test properties with invalid identifier."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "public.bad;table"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_properties_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.table.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "public.users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_properties_cmd_query_error(self, mock_get_connection):
        """Test query error during properties."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "public.users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_properties_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.return_value = [
            {"property_key": "orientation", "property_value": "column"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "table", "properties", "public.users"])

        assert result.exit_code == 0
        assert "property_key" in result.output
        assert "orientation" in result.output

    def test_properties_cmd_csv_format(self, mock_get_connection):
        """Test CSV format output."""
        mock_get_connection.execute.return_value = [
            {"property_key": "orientation", "property_value": "column"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "csv", "table", "properties", "public.users"])

        assert result.exit_code == 0
        assert "property_key" in result.output
        assert "orientation" in result.output

    def test_properties_cmd_logs_success(self, mock_get_connection, mocker):
        """Test that successful properties logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.table.log_operation")
        mock_get_connection.execute.return_value = [
            {"property_key": "orientation", "property_value": "column"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "public.users"])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[0][0] == "table.properties"

    def test_properties_cmd_logs_failure(self, mock_get_connection, mocker):
        """Test that failed properties logs operation with error."""
        mock_log = mocker.patch("hologres_cli.commands.table.log_operation")
        mock_get_connection.execute.side_effect = Exception("DB error")

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "public.users"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"

    def test_properties_cmd_connection_closed(self, mock_get_connection):
        """Test that connection is closed after properties."""
        mock_get_connection.execute.return_value = [
            {"property_key": "orientation", "property_value": "column"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "properties", "public.users"])

        assert result.exit_code == 0
        mock_get_connection.close.assert_called_once()
