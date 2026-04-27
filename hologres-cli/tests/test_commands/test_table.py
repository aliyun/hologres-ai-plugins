"""Tests for table command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.commands.table import _build_table_alter_sql, _build_table_create_sql
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


class TestTableDropCmd:
    """Tests for table drop command."""

    def test_drop_without_confirm_is_dry_run(self):
        """Test that drop without --confirm is dry-run mode."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "DROP TABLE" in output["data"]["sql"]
        assert "public.my_table" in output["data"]["sql"]

    def test_drop_with_confirm_executes(self, mock_get_connection):
        """Test that drop with --confirm actually executes SQL."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "my_table", "--confirm"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True
        mock_get_connection.execute.assert_called_once()
        sql = mock_get_connection.execute.call_args[0][0]
        assert "DROP TABLE" in sql
        mock_get_connection.close.assert_called_once()

    def test_drop_with_if_exists(self):
        """Test --if-exists option adds IF EXISTS clause."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "my_table", "--if-exists"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "IF EXISTS" in output["data"]["sql"]

    def test_drop_with_cascade(self):
        """Test --cascade option adds CASCADE clause."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "my_table", "--cascade"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "CASCADE" in output["data"]["sql"]

    def test_drop_with_schema_qualified_name(self):
        """Test schema.table format is correctly parsed."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "myschema.my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "myschema.my_table" in output["data"]["sql"]

    def test_drop_without_schema_defaults_to_public(self):
        """Test that table name without schema defaults to public."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "public.my_table" in output["data"]["sql"]

    def test_drop_invalid_table_name(self):
        """Test invalid table name returns INVALID_INPUT error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "invalid;table"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_drop_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.table.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "my_table", "--confirm"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_drop_execution_error(self, mock_get_connection):
        """Test execution error returns QUERY_ERROR."""
        mock_get_connection.execute.side_effect = Exception("relation not found")

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "my_table", "--confirm"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_drop_with_if_exists_and_cascade(self):
        """Test combining --if-exists and --cascade options."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "drop", "my_table", "--if-exists", "--cascade"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "IF EXISTS" in output["data"]["sql"]
        assert "CASCADE" in output["data"]["sql"]


class TestTableTruncateCmd:
    """Tests for table truncate command."""

    def test_truncate_without_confirm_is_dry_run(self):
        """Test that truncate without --confirm is dry-run mode."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "truncate", "my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "TRUNCATE TABLE" in output["data"]["sql"]
        assert "public.my_table" in output["data"]["sql"]

    def test_truncate_with_confirm_executes(self, mock_get_connection):
        """Test that truncate with --confirm actually executes SQL."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "truncate", "my_table", "--confirm"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True
        mock_get_connection.execute.assert_called_once()
        sql = mock_get_connection.execute.call_args[0][0]
        assert "TRUNCATE TABLE" in sql
        mock_get_connection.close.assert_called_once()

    def test_truncate_with_schema_qualified_name(self):
        """Test schema.table format is correctly parsed."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "truncate", "myschema.my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "myschema.my_table" in output["data"]["sql"]

    def test_truncate_without_schema_defaults_to_public(self):
        """Test that table name without schema defaults to public."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "truncate", "my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "public.my_table" in output["data"]["sql"]

    def test_truncate_invalid_table_name(self):
        """Test invalid table name returns INVALID_INPUT error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "truncate", "bad;name"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_truncate_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.table.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "truncate", "my_table", "--confirm"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_truncate_execution_error(self, mock_get_connection):
        """Test execution error returns QUERY_ERROR."""
        mock_get_connection.execute.side_effect = Exception("permission denied")

        runner = CliRunner()
        result = runner.invoke(cli, ["table", "truncate", "my_table", "--confirm"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()


class TestBuildTableCreateSql:
    """Tests for _build_table_create_sql helper function."""

    def test_build_sql_minimal(self):
        """Test minimal SQL generation with only name and columns."""
        sql = _build_table_create_sql(name="my_table", columns="id INT")
        assert "BEGIN;" in sql
        assert "CREATE TABLE public.my_table" in sql
        assert "id INT" in sql
        assert "COMMIT;" in sql

    def test_build_sql_with_schema(self):
        """Test SQL with schema-qualified name."""
        sql = _build_table_create_sql(name="myschema.orders", columns="id INT")
        assert "CREATE TABLE myschema.orders" in sql

    def test_build_sql_with_primary_key(self):
        """Test SQL includes PRIMARY KEY clause."""
        sql = _build_table_create_sql(name="t", columns="id INT NOT NULL", primary_key="id")
        assert "PRIMARY KEY (id)" in sql

    def test_build_sql_composite_primary_key(self):
        """Test SQL with composite primary key."""
        sql = _build_table_create_sql(name="t", columns="id INT, ds TEXT", primary_key="id,ds")
        assert "PRIMARY KEY (id,ds)" in sql

    def test_build_sql_orientation(self):
        """Test orientation property."""
        sql = _build_table_create_sql(name="t", columns="id INT", orientation="column")
        assert "set_table_property('public.t', 'orientation', 'column')" in sql

    def test_build_sql_distribution_key(self):
        """Test distribution_key property."""
        sql = _build_table_create_sql(name="t", columns="id INT", distribution_key="id")
        assert "set_table_property('public.t', 'distribution_key', 'id')" in sql

    def test_build_sql_clustering_key(self):
        """Test clustering_key property."""
        sql = _build_table_create_sql(name="t", columns="id INT", clustering_key="created_at:asc")
        assert "set_table_property('public.t', 'clustering_key', 'created_at:asc')" in sql

    def test_build_sql_event_time_column(self):
        """Test event_time_column property."""
        sql = _build_table_create_sql(name="t", columns="id INT", event_time_column="created_at")
        assert "set_table_property('public.t', 'event_time_column', 'created_at')" in sql

    def test_build_sql_bitmap_columns(self):
        """Test bitmap_columns property."""
        sql = _build_table_create_sql(name="t", columns="id INT", bitmap_columns="status,type")
        assert "set_table_property('public.t', 'bitmap_columns', 'status,type')" in sql

    def test_build_sql_dictionary_encoding_columns(self):
        """Test dictionary_encoding_columns property."""
        sql = _build_table_create_sql(name="t", columns="id INT",
                                      dictionary_encoding_columns="user_id:auto")
        assert "set_table_property('public.t', 'dictionary_encoding_columns', 'user_id:auto')" in sql

    def test_build_sql_ttl(self):
        """Test time_to_live_in_seconds property."""
        sql = _build_table_create_sql(name="t", columns="id INT", ttl=2592000)
        assert "set_table_property('public.t', 'time_to_live_in_seconds', '2592000')" in sql

    def test_build_sql_storage_mode(self):
        """Test storage_mode property."""
        sql = _build_table_create_sql(name="t", columns="id INT", storage_mode="hot")
        assert "set_table_property('public.t', 'storage_mode', 'hot')" in sql

    def test_build_sql_table_group(self):
        """Test table_group property."""
        sql = _build_table_create_sql(name="t", columns="id INT", table_group="my_tg")
        assert "set_table_property('public.t', 'table_group', 'my_tg')" in sql

    def test_build_sql_partition_physical(self):
        """Test physical partition clause."""
        sql = _build_table_create_sql(name="t", columns="id INT, ds TEXT",
                                      partition_by="ds")
        assert "PARTITION BY LIST (ds)" in sql
        assert "LOGICAL" not in sql

    def test_build_sql_partition_logical(self):
        """Test logical partition uses WITH syntax instead of CALL."""
        sql = _build_table_create_sql(name="t", columns="id INT, ds TEXT",
                                      partition_by="ds", partition_mode="logical")
        assert "LOGICAL PARTITION BY LIST (ds)" in sql
        assert "BEGIN;" not in sql
        assert "COMMIT;" not in sql
        assert "CALL" not in sql

    def test_build_sql_binlog_replica(self):
        """Test binlog=replica generates binlog.level property (dot notation for CALL syntax)."""
        sql = _build_table_create_sql(name="t", columns="id INT", binlog="replica")
        assert "set_table_property('public.t', 'binlog.level', 'replica')" in sql

    def test_build_sql_binlog_none_no_property(self):
        """Test binlog=none does NOT generate property."""
        sql = _build_table_create_sql(name="t", columns="id INT", binlog="none")
        assert "binlog.level" not in sql
        assert "binlog_level" not in sql

    def test_build_sql_binlog_ttl(self):
        """Test binlog_ttl generates binlog.ttl property (dot notation for CALL syntax)."""
        sql = _build_table_create_sql(name="t", columns="id INT", binlog_ttl=86400)
        assert "set_table_property('public.t', 'binlog.ttl', '86400')" in sql

    def test_build_sql_if_not_exists(self):
        """Test IF NOT EXISTS clause."""
        sql = _build_table_create_sql(name="t", columns="id INT", if_not_exists=True)
        assert "CREATE TABLE IF NOT EXISTS public.t" in sql

    def test_build_sql_complex_columns(self):
        """Test complex column types like NUMERIC(10,2)."""
        cols = "order_id BIGINT NOT NULL, amount DECIMAL(10,2), ts TIMESTAMPTZ"
        sql = _build_table_create_sql(name="t", columns=cols)
        assert "DECIMAL(10,2)" in sql
        assert "TIMESTAMPTZ" in sql

    def test_build_sql_multiple_properties(self):
        """Test multiple properties are all generated."""
        sql = _build_table_create_sql(
            name="public.orders",
            columns="id BIGINT NOT NULL",
            primary_key="id",
            orientation="column",
            distribution_key="id",
            clustering_key="created_at:asc",
            event_time_column="created_at",
            ttl=7776000,
        )
        assert "orientation" in sql
        assert "distribution_key" in sql
        assert "clustering_key" in sql
        assert "event_time_column" in sql
        assert "time_to_live_in_seconds" in sql
        assert "PRIMARY KEY (id)" in sql

    def test_build_sql_full_example(self):
        """Test full example from requirement."""
        sql = _build_table_create_sql(
            name="public.orders",
            columns="order_id BIGINT NOT NULL, user_id INT, amount DECIMAL(10,2), created_at TIMESTAMPTZ",
            primary_key="order_id",
            orientation="column",
            distribution_key="user_id",
            clustering_key="created_at:asc",
            ttl=7776000,
        )
        assert "BEGIN;" in sql
        assert "CREATE TABLE public.orders" in sql
        assert "order_id BIGINT NOT NULL" in sql
        assert "PRIMARY KEY (order_id)" in sql
        assert "set_table_property('public.orders', 'orientation', 'column')" in sql
        assert "set_table_property('public.orders', 'distribution_key', 'user_id')" in sql
        assert "set_table_property('public.orders', 'clustering_key', 'created_at:asc')" in sql
        assert "set_table_property('public.orders', 'time_to_live_in_seconds', '7776000')" in sql
        assert "COMMIT;" in sql

    def test_build_sql_no_properties_no_call(self):
        """Test that no CALL statements when no properties."""
        sql = _build_table_create_sql(name="t", columns="id INT")
        assert "CALL" not in sql

    # --- Logical partition table tests ---

    def test_logical_partition_uses_with_syntax(self):
        """Test logical partition uses WITH(...) syntax."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            orientation="column",
        )
        assert "WITH (" in sql
        assert "orientation = 'column'" in sql
        assert "CALL" not in sql

    def test_logical_partition_no_begin_commit(self):
        """Test logical partition SQL has no BEGIN/COMMIT."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
        )
        assert "BEGIN;" not in sql
        assert "COMMIT;" not in sql

    def test_logical_partition_with_orientation(self):
        """Test WITH(orientation = 'column') for logical partition."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            orientation="column",
        )
        assert "orientation = 'column'" in sql

    def test_logical_partition_with_distribution_key(self):
        """Test WITH(distribution_key) for logical partition."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            distribution_key="id",
        )
        assert "distribution_key = 'id'" in sql

    def test_logical_partition_with_expiration_time(self):
        """Test partition_expiration_time property."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            partition_expiration_time="30 day",
        )
        assert "partition_expiration_time = '30 day'" in sql

    def test_logical_partition_with_keep_hot_window(self):
        """Test partition_keep_hot_window property."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            partition_keep_hot_window="15 day",
        )
        assert "partition_keep_hot_window = '15 day'" in sql

    def test_logical_partition_with_require_filter_true(self):
        """Test partition_require_filter = TRUE (no quotes)."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            partition_require_filter="true",
        )
        assert "partition_require_filter = TRUE" in sql
        # Must not be quoted
        assert "partition_require_filter = 'TRUE'" not in sql

    def test_logical_partition_with_require_filter_false(self):
        """Test partition_require_filter = FALSE."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            partition_require_filter="false",
        )
        assert "partition_require_filter = FALSE" in sql

    def test_logical_partition_with_binlog_window(self):
        """Test partition_generate_binlog_window property."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            partition_generate_binlog_window="3 day",
        )
        assert "partition_generate_binlog_window = '3 day'" in sql

    def test_logical_partition_with_binlog_ttl(self):
        """Test binlog_ttl uses underscore in WITH syntax."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            binlog_ttl=86400,
        )
        assert "binlog_ttl = '86400'" in sql

    def test_logical_partition_with_binlog_replica(self):
        """Test binlog_level uses underscore in WITH syntax."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
            binlog="replica",
        )
        assert "binlog_level = 'replica'" in sql

    def test_logical_partition_multi_column_key(self):
        """Test multi-column partition key."""
        sql = _build_table_create_sql(
            name="t", columns="a TEXT, yy TEXT NOT NULL, mm TEXT NOT NULL",
            partition_by="yy, mm", partition_mode="logical",
        )
        assert "LOGICAL PARTITION BY LIST (yy, mm)" in sql

    def test_logical_partition_no_properties(self):
        """Test logical partition with no WITH clause when no properties."""
        sql = _build_table_create_sql(
            name="t", columns="id INT, ds DATE NOT NULL",
            partition_by="ds", partition_mode="logical",
        )
        assert "LOGICAL PARTITION BY LIST (ds)" in sql
        assert "WITH" not in sql

    def test_logical_partition_full_example(self):
        """Test full logical partition example matching documentation."""
        sql = _build_table_create_sql(
            name="public.hologres_logical_parent_1",
            columns="a TEXT, b INT, c TIMESTAMP, ds DATE NOT NULL",
            primary_key="b, ds",
            partition_by="ds", partition_mode="logical",
            orientation="column",
            distribution_key="b",
            partition_expiration_time="30 day",
            partition_keep_hot_window="15 day",
            partition_require_filter="true",
            binlog="replica",
            partition_generate_binlog_window="3 day",
        )
        assert "LOGICAL PARTITION BY LIST (ds)" in sql
        assert "PRIMARY KEY (b, ds)" in sql
        assert "WITH (" in sql
        assert "orientation = 'column'" in sql
        assert "distribution_key = 'b'" in sql
        assert "partition_expiration_time = '30 day'" in sql
        assert "partition_keep_hot_window = '15 day'" in sql
        assert "partition_require_filter = TRUE" in sql
        assert "binlog_level = 'replica'" in sql
        assert "partition_generate_binlog_window = '3 day'" in sql
        assert "BEGIN;" not in sql
        assert "COMMIT;" not in sql

    def test_logical_partition_with_all_properties(self):
        """Test logical partition with all possible properties."""
        sql = _build_table_create_sql(
            name="public.t",
            columns="id INT, ds DATE NOT NULL",
            primary_key="id, ds",
            partition_by="ds", partition_mode="logical",
            orientation="column",
            distribution_key="id",
            clustering_key="id:asc",
            event_time_column="ds",
            bitmap_columns="id",
            dictionary_encoding_columns="id",
            ttl=2592000,
            storage_mode="hot",
            table_group="my_tg",
            binlog="replica",
            binlog_ttl=86400,
            partition_expiration_time="30 day",
            partition_keep_hot_window="15 day",
            partition_require_filter="true",
            partition_generate_binlog_window="3 day",
        )
        assert "WITH (" in sql
        assert "orientation = 'column'" in sql
        assert "distribution_key = 'id'" in sql
        assert "clustering_key = 'id:asc'" in sql
        assert "event_time_column = 'ds'" in sql
        assert "bitmap_columns = 'id'" in sql
        assert "dictionary_encoding_columns = 'id'" in sql
        assert "time_to_live_in_seconds = '2592000'" in sql
        assert "storage_mode = 'hot'" in sql
        assert "table_group = 'my_tg'" in sql
        assert "binlog_level = 'replica'" in sql
        assert "binlog_ttl = '86400'" in sql
        assert "partition_expiration_time = '30 day'" in sql
        assert "partition_keep_hot_window = '15 day'" in sql
        assert "partition_require_filter = TRUE" in sql
        assert "partition_generate_binlog_window = '3 day'" in sql

    def test_non_logical_binlog_uses_dot_notation(self):
        """Test non-logical table uses dot notation for binlog (binlog.level)."""
        sql = _build_table_create_sql(name="t", columns="id INT", binlog="replica")
        assert "set_table_property('public.t', 'binlog.level', 'replica')" in sql
        # Must NOT use underscore notation
        assert "binlog_level" not in sql

    def test_non_logical_binlog_ttl_uses_dot_notation(self):
        """Test non-logical table uses dot notation for binlog.ttl."""
        sql = _build_table_create_sql(name="t", columns="id INT", binlog_ttl=86400)
        assert "set_table_property('public.t', 'binlog.ttl', '86400')" in sql
        # Must NOT use underscore notation
        assert "binlog_ttl" not in sql


class TestTableCreateCmd:
    """Tests for table create command."""

    def test_create_dry_run_minimal(self):
        """Test dry-run with minimal options."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "my_table",
            "--columns", "id INT",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "CREATE TABLE" in output["data"]["sql"]
        assert "public.my_table" in output["data"]["sql"]
        assert "BEGIN;" in output["data"]["sql"]
        assert "COMMIT;" in output["data"]["sql"]

    def test_create_dry_run_with_all_options(self):
        """Test dry-run with all options specified."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "public.orders",
            "--columns", "order_id BIGINT NOT NULL, user_id INT",
            "--primary-key", "order_id",
            "--orientation", "column",
            "--distribution-key", "user_id",
            "--clustering-key", "order_id:asc",
            "--event-time-column", "created_at",
            "--bitmap-columns", "status",
            "--dictionary-encoding-columns", "user_id",
            "--ttl", "2592000",
            "--storage-mode", "hot",
            "--table-group", "my_tg",
            "--binlog", "replica",
            "--if-not-exists",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        sql = output["data"]["sql"]
        assert "IF NOT EXISTS" in sql
        assert "PRIMARY KEY (order_id)" in sql
        assert "orientation" in sql
        assert "distribution_key" in sql
        assert "clustering_key" in sql
        assert "event_time_column" in sql
        assert "bitmap_columns" in sql
        assert "dictionary_encoding_columns" in sql
        assert "time_to_live_in_seconds" in sql
        assert "storage_mode" in sql
        assert "table_group" in sql
        assert "binlog.level" in sql

    def test_create_dry_run_with_partition(self):
        """Test dry-run with partition options."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT, ds TEXT",
            "--partition-by", "ds",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "PARTITION BY LIST (ds)" in output["data"]["sql"]

    def test_create_dry_run_with_logical_partition(self):
        """Test dry-run with logical partition mode."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT, ds TEXT",
            "--partition-by", "ds",
            "--partition-mode", "logical",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "LOGICAL PARTITION BY LIST (ds)" in output["data"]["sql"]

    def test_create_executes_without_dry_run(self, mock_get_connection):
        """Test that create without --dry-run actually executes."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "my_table",
            "--columns", "id INT",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True
        mock_get_connection.execute.assert_called_once()
        sql = mock_get_connection.execute.call_args[0][0]
        assert "CREATE TABLE" in sql
        mock_get_connection.close.assert_called_once()

    def test_create_schema_qualified_name(self):
        """Test schema.table format is correctly parsed."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "myschema.orders",
            "--columns", "id INT",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "myschema.orders" in output["data"]["sql"]

    def test_create_default_schema_public(self):
        """Test that name without schema defaults to public."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "orders",
            "--columns", "id INT",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "public.orders" in output["data"]["sql"]

    def test_create_invalid_table_name(self):
        """Test invalid table name returns INVALID_INPUT error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "bad;name",
            "--columns", "id INT",
            "--dry-run",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_create_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.table.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "my_table",
            "--columns", "id INT",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_create_query_error(self, mock_get_connection):
        """Test query error returns QUERY_ERROR."""
        mock_get_connection.execute.side_effect = Exception("syntax error")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "my_table",
            "--columns", "id INT",
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_create_conn_closed_after_success(self, mock_get_connection):
        """Test connection is closed after successful create."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT",
        ])

        assert result.exit_code == 0
        mock_get_connection.close.assert_called_once()

    def test_create_conn_closed_on_error(self, mock_get_connection):
        """Test connection is closed even on error."""
        mock_get_connection.execute.side_effect = Exception("fail")

        runner = CliRunner()
        runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT",
        ])

        mock_get_connection.close.assert_called_once()

    def test_create_missing_required_name(self):
        """Test missing --name returns error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--columns", "id INT",
        ])

        assert result.exit_code != 0

    def test_create_missing_required_columns(self):
        """Test missing --columns returns error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
        ])

        assert result.exit_code != 0

    def test_create_binlog_none_no_property(self):
        """Test --binlog none does not generate binlog property."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT",
            "--binlog", "none",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "binlog.level" not in output["data"]["sql"]
        assert "binlog_level" not in output["data"]["sql"]

    def test_create_logs_operation_on_success(self, mock_get_connection, mocker):
        """Test successful create logs operation."""
        mock_log = mocker.patch("hologres_cli.commands.table.log_operation")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT",
        ])

        assert result.exit_code == 0
        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is True
        assert call_kwargs[0][0] == "table.create"

    def test_create_logs_operation_on_failure(self, mock_get_connection, mocker):
        """Test failed create logs operation with error."""
        mock_log = mocker.patch("hologres_cli.commands.table.log_operation")
        mock_get_connection.execute.side_effect = Exception("fail")

        runner = CliRunner()
        runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT",
        ])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"

    # --- Logical partition CLI tests ---

    def test_create_logical_partition_dry_run(self):
        """Test logical partition dry-run generates WITH syntax."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "public.logs",
            "--columns", "a TEXT, b INT, ds DATE NOT NULL",
            "--primary-key", "b,ds",
            "--partition-by", "ds",
            "--partition-mode", "logical",
            "--orientation", "column",
            "--distribution-key", "b",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        sql = output["data"]["sql"]
        assert "LOGICAL PARTITION BY LIST (ds)" in sql
        assert "WITH (" in sql
        assert "orientation = 'column'" in sql
        assert "distribution_key = 'b'" in sql
        assert "BEGIN;" not in sql
        assert "COMMIT;" not in sql

    def test_create_logical_partition_with_all_opts(self):
        """Test logical partition dry-run with all options."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "public.logs",
            "--columns", "a TEXT, b INT, ds DATE NOT NULL",
            "--primary-key", "b,ds",
            "--partition-by", "ds",
            "--partition-mode", "logical",
            "--orientation", "column",
            "--distribution-key", "b",
            "--partition-expiration-time", "30 day",
            "--partition-keep-hot-window", "15 day",
            "--partition-require-filter", "true",
            "--binlog", "replica",
            "--binlog-ttl", "86400",
            "--partition-generate-binlog-window", "3 day",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "partition_expiration_time = '30 day'" in sql
        assert "partition_keep_hot_window = '15 day'" in sql
        assert "partition_require_filter = TRUE" in sql
        assert "binlog_level = 'replica'" in sql
        assert "binlog_ttl = '86400'" in sql
        assert "partition_generate_binlog_window = '3 day'" in sql

    def test_create_logical_partition_executes(self, mock_get_connection):
        """Test logical partition without --dry-run actually executes."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT, ds DATE NOT NULL",
            "--partition-by", "ds",
            "--partition-mode", "logical",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["executed"] is True
        mock_get_connection.execute.assert_called_once()

    def test_create_logical_opts_without_logical_mode_error(self):
        """Test logical-only options without --partition-mode logical returns error."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT",
            "--partition-expiration-time", "30 day",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"
        assert "--partition-expiration-time" in output["error"]["message"]

    def test_create_logical_partition_multi_key(self):
        """Test multi-column partition key for logical partition."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "a TEXT, yy TEXT NOT NULL, mm TEXT NOT NULL",
            "--partition-by", "yy, mm",
            "--partition-mode", "logical",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "LOGICAL PARTITION BY LIST (yy, mm)" in output["data"]["sql"]

    def test_create_logical_partition_require_filter(self):
        """Test --partition-require-filter option."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT, ds DATE NOT NULL",
            "--partition-by", "ds",
            "--partition-mode", "logical",
            "--partition-require-filter", "true",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "partition_require_filter = TRUE" in output["data"]["sql"]

    def test_create_logical_partition_binlog_replica(self):
        """Test --binlog replica with logical partition."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT, ds DATE NOT NULL",
            "--partition-by", "ds",
            "--partition-mode", "logical",
            "--binlog", "replica",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "binlog_level = 'replica'" in output["data"]["sql"]

    def test_create_binlog_ttl_regular_table(self):
        """Test --binlog-ttl works with regular (non-logical) tables."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "create",
            "--name", "t",
            "--columns", "id INT",
            "--binlog", "replica",
            "--binlog-ttl", "86400",
            "--dry-run",
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "set_table_property('public.t', 'binlog.level', 'replica')" in sql
        assert "set_table_property('public.t', 'binlog.ttl', '86400')" in sql


class TestBuildTableAlterSql:
    """Tests for _build_table_alter_sql helper."""

    def test_add_single_column(self):
        sql = _build_table_alter_sql("public", "t", add_columns=("age INT",))
        assert sql == "ALTER TABLE IF EXISTS public.t ADD COLUMN age INT"

    def test_add_multiple_columns(self):
        sql = _build_table_alter_sql("public", "t", add_columns=("a INT", "b TEXT"))
        assert sql == "ALTER TABLE IF EXISTS public.t ADD COLUMN a INT, ADD COLUMN b TEXT"

    def test_add_column_with_constraints(self):
        sql = _build_table_alter_sql("public", "t", add_columns=("age INT NOT NULL DEFAULT 0",))
        assert sql == "ALTER TABLE IF EXISTS public.t ADD COLUMN age INT NOT NULL DEFAULT 0"

    def test_rename_column(self):
        sql = _build_table_alter_sql("public", "t", rename_column="old:new")
        assert sql == "ALTER TABLE IF EXISTS public.t RENAME COLUMN old TO new"

    def test_rename_column_with_spaces(self):
        sql = _build_table_alter_sql("public", "t", rename_column="old : new")
        assert sql == "ALTER TABLE IF EXISTS public.t RENAME COLUMN old TO new"

    def test_ttl(self):
        sql = _build_table_alter_sql("public", "t", ttl=3600)
        assert sql == "CALL set_table_property('public.t', 'time_to_live_in_seconds', '3600')"

    def test_dictionary_encoding_columns(self):
        sql = _build_table_alter_sql("public", "t", dictionary_encoding_columns="a:on,b:off")
        assert sql == "CALL SET_TABLE_PROPERTY('public.t', 'dictionary_encoding_columns', 'a:on,b:off')"

    def test_bitmap_columns(self):
        sql = _build_table_alter_sql("public", "t", bitmap_columns="a:on,b:off")
        assert sql == "CALL SET_TABLE_PROPERTY('public.t', 'bitmap_columns', 'a:on,b:off')"

    def test_owner(self):
        sql = _build_table_alter_sql("public", "t", owner="new_user")
        assert sql == "ALTER TABLE IF EXISTS public.t OWNER TO new_user"

    def test_rename_table(self):
        sql = _build_table_alter_sql("public", "t", rename="new_table")
        assert sql == "ALTER TABLE IF EXISTS public.t RENAME TO new_table"

    def test_no_options_returns_empty(self):
        sql = _build_table_alter_sql("public", "t")
        assert sql == ""

    def test_with_schema(self):
        sql = _build_table_alter_sql("myschema", "t", ttl=600)
        assert sql == "CALL set_table_property('myschema.t', 'time_to_live_in_seconds', '600')"

    def test_single_option_no_transaction(self):
        sql = _build_table_alter_sql("public", "t", ttl=600)
        assert not sql.startswith("BEGIN;")
        assert "COMMIT;" not in sql

    def test_multiple_options_wrapped_in_transaction(self):
        sql = _build_table_alter_sql("public", "t", add_columns=("a INT",), ttl=600)
        assert sql.startswith("BEGIN;")
        assert sql.endswith("COMMIT;")
        assert "ALTER TABLE IF EXISTS public.t ADD COLUMN a INT;" in sql
        assert "CALL set_table_property('public.t', 'time_to_live_in_seconds', '600');" in sql

    def test_execution_order(self):
        """Verify the correct order: ADD COLUMN -> RENAME COLUMN -> TTL -> OWNER -> RENAME."""
        sql = _build_table_alter_sql(
            "public", "t",
            add_columns=("a INT",),
            rename_column="x:y",
            ttl=600,
            owner="admin",
            rename="new_t",
        )
        lines = sql.split("\n")
        stmts = [l for l in lines if l.strip() and l.strip() not in ("BEGIN;", "COMMIT;")]
        assert "ADD COLUMN" in stmts[0]
        assert "RENAME COLUMN" in stmts[1]
        assert "time_to_live_in_seconds" in stmts[2]
        assert "OWNER TO" in stmts[3]
        assert "RENAME TO" in stmts[4]

    def test_rename_is_last(self):
        """Verify RENAME TO is the last statement."""
        sql = _build_table_alter_sql("public", "t", ttl=600, rename="new_t")
        lines = sql.split("\n")
        stmts = [l for l in lines if l.strip() and l.strip() not in ("BEGIN;", "COMMIT;")]
        assert "RENAME TO" in stmts[-1]
        assert "time_to_live_in_seconds" in stmts[0]


class TestTableAlterCmd:
    """Tests for table alter command."""

    def test_alter_dry_run(self):
        """Test dry-run mode returns SQL preview."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--add-column", "age INT", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "ADD COLUMN age INT" in output["data"]["sql"]

    def test_alter_execute(self, mock_get_connection):
        """Test execute mode calls conn.execute."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--add-column", "age INT"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True
        assert output["message"] == "Table altered successfully"
        mock_get_connection.execute.assert_called_once()
        mock_get_connection.close.assert_called_once()

    def test_alter_no_changes(self):
        """Test that no options returns NO_CHANGES error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["table", "alter", "my_table"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NO_CHANGES"

    def test_alter_add_column(self, mock_get_connection):
        """Test adding a column."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--add-column", "age INT"
        ])

        assert result.exit_code == 0
        sql = mock_get_connection.execute.call_args[0][0]
        assert "ALTER TABLE IF EXISTS public.my_table ADD COLUMN age INT" == sql

    def test_alter_add_multiple_columns(self):
        """Test adding multiple columns."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--add-column", "a INT", "--add-column", "b TEXT",
            "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "ADD COLUMN a INT, ADD COLUMN b TEXT" in output["data"]["sql"]

    def test_alter_rename_column(self, mock_get_connection):
        """Test renaming a column."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--rename-column", "old_col:new_col"
        ])

        assert result.exit_code == 0
        sql = mock_get_connection.execute.call_args[0][0]
        assert "RENAME COLUMN old_col TO new_col" in sql

    def test_alter_rename_column_invalid_format(self):
        """Test invalid --rename-column format."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--rename-column", "no_colon"
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"

    def test_alter_ttl(self, mock_get_connection):
        """Test modifying TTL."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--ttl", "3600"
        ])

        assert result.exit_code == 0
        sql = mock_get_connection.execute.call_args[0][0]
        assert "time_to_live_in_seconds" in sql
        assert "'3600'" in sql

    def test_alter_dictionary_encoding(self, mock_get_connection):
        """Test modifying dictionary encoding columns."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--dictionary-encoding-columns", "a:on,b:auto"
        ])

        assert result.exit_code == 0
        sql = mock_get_connection.execute.call_args[0][0]
        assert "dictionary_encoding_columns" in sql
        assert "a:on,b:auto" in sql

    def test_alter_bitmap(self, mock_get_connection):
        """Test modifying bitmap columns."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--bitmap-columns", "a:on,b:off"
        ])

        assert result.exit_code == 0
        sql = mock_get_connection.execute.call_args[0][0]
        assert "bitmap_columns" in sql
        assert "a:on,b:off" in sql

    def test_alter_owner(self, mock_get_connection):
        """Test changing table owner."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--owner", "new_user"
        ])

        assert result.exit_code == 0
        sql = mock_get_connection.execute.call_args[0][0]
        assert "OWNER TO new_user" in sql

    def test_alter_rename_table(self, mock_get_connection):
        """Test renaming a table."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--rename", "new_table"
        ])

        assert result.exit_code == 0
        sql = mock_get_connection.execute.call_args[0][0]
        assert "RENAME TO new_table" in sql

    def test_alter_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.table.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--ttl", "3600"
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_alter_query_error(self, mock_get_connection):
        """Test SQL execution failure returns QUERY_ERROR."""
        mock_get_connection.execute.side_effect = Exception("Query failed")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--ttl", "3600"
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_alter_invalid_identifier(self):
        """Test invalid table name returns INVALID_INPUT."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "invalid;table", "--ttl", "3600"
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_alter_multiple_options(self):
        """Test multiple options generate transaction-wrapped SQL."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--add-column", "age INT", "--ttl", "3600",
            "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert sql.startswith("BEGIN;")
        assert "COMMIT;" in sql
        assert "ADD COLUMN age INT" in sql
        assert "time_to_live_in_seconds" in sql

    def test_alter_with_schema(self):
        """Test schema.table format."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "myschema.my_table", "--ttl", "3600", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert "myschema.my_table" in output["data"]["sql"]

    def test_alter_rename_validates_identifier(self):
        """Test --rename value is validated."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--rename", "bad;name"
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_alter_owner_validates_identifier(self):
        """Test --owner value is validated."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--owner", "bad;user"
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_alter_single_option_no_transaction(self):
        """Test single option does not wrap in BEGIN/COMMIT."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--ttl", "600", "--dry-run"
        ])

        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert not sql.startswith("BEGIN;")
        assert "COMMIT;" not in sql

    def test_alter_transaction_failure(self, mock_get_connection):
        """Test transaction failure returns QUERY_ERROR."""
        mock_get_connection.execute.side_effect = Exception("Transaction failed")

        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--add-column", "a INT", "--ttl", "600"
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
        mock_get_connection.close.assert_called_once()

    def test_alter_rename_column_validates_identifiers(self):
        """Test --rename-column validates both old and new column names."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table", "--rename-column", "ok:bad;col"
        ])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    # --- Logical partition table SET property tests ---

    def test_alter_partition_expiration_time_dry_run(self):
        """Test --partition-expiration-time generates SET SQL."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--partition-expiration-time", "30 day", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        sql = output["data"]["sql"]
        assert "ALTER TABLE public.my_table SET" in sql
        assert "partition_expiration_time = '30 day'" in sql

    def test_alter_partition_keep_hot_window_dry_run(self):
        """Test --partition-keep-hot-window generates SET SQL."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--partition-keep-hot-window", "15 day", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "partition_keep_hot_window = '15 day'" in sql

    def test_alter_partition_require_filter_dry_run(self):
        """Test --partition-require-filter generates SET SQL with boolean."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--partition-require-filter", "true", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "partition_require_filter = TRUE" in sql

    def test_alter_partition_require_filter_false(self):
        """Test --partition-require-filter false generates FALSE."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--partition-require-filter", "false", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "partition_require_filter = FALSE" in sql

    def test_alter_binlog_level_dry_run(self):
        """Test --binlog generates SET SQL with binlog_level."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--binlog", "replica", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "binlog_level = 'replica'" in sql

    def test_alter_binlog_ttl_dry_run(self):
        """Test --binlog-ttl generates SET SQL with numeric value."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--binlog-ttl", "86400", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "binlog_ttl = 86400" in sql

    def test_alter_partition_generate_binlog_window_dry_run(self):
        """Test --partition-generate-binlog-window generates SET SQL."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--partition-generate-binlog-window", "3 day", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "partition_generate_binlog_window = '3 day'" in sql

    def test_alter_multiple_set_props_dry_run(self):
        """Test multiple SET properties in one ALTER TABLE SET."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--partition-expiration-time", "60 day",
            "--partition-keep-hot-window", "30 day",
            "--partition-require-filter", "false",
            "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert "ALTER TABLE public.my_table SET" in sql
        assert "partition_expiration_time = '60 day'" in sql
        assert "partition_keep_hot_window = '30 day'" in sql
        assert "partition_require_filter = FALSE" in sql

    def test_alter_set_props_with_add_column(self):
        """Test SET props combined with traditional ALTER generates transaction."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--add-column", "age INT",
            "--partition-expiration-time", "30 day",
            "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert sql.startswith("BEGIN;")
        assert "COMMIT;" in sql
        assert "ADD COLUMN age INT" in sql
        assert "ALTER TABLE public.my_table SET" in sql

    def test_alter_set_props_with_ttl(self):
        """Test SET props combined with TTL uses both syntaxes in transaction."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--ttl", "3600",
            "--partition-require-filter", "true",
            "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert sql.startswith("BEGIN;")
        assert "COMMIT;" in sql
        assert "time_to_live_in_seconds" in sql
        assert "partition_require_filter = TRUE" in sql

    def test_alter_set_props_single_no_transaction(self):
        """Test single SET prop does not wrap in BEGIN/COMMIT."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--partition-expiration-time", "30 day", "--dry-run"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        sql = output["data"]["sql"]
        assert not sql.startswith("BEGIN;")
        assert "COMMIT;" not in sql

    def test_alter_set_props_execute(self, mock_get_connection):
        """Test execute mode calls conn.execute."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "table", "alter", "my_table",
            "--partition-expiration-time", "30 day"
        ])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True
        assert output["message"] == "Table altered successfully"
        mock_get_connection.execute.assert_called_once()
        mock_get_connection.close.assert_called_once()
