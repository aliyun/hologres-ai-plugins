"""Tests for partition command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


class TestPartitionCreateCmd:
    """Tests for partition create command."""

    def test_create_returns_notice(self):
        """Test partition create returns notice without DB connection."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "create", "--table", "my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "notice" in output["data"]
        assert "automatically" in output["data"]["notice"]
        assert output["message"] == "No action required"

    def test_create_with_partition_value(self):
        """Test partition create with --partition value (ignored)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "create", "--table", "my_table",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "notice" in output["data"]

    def test_create_with_dry_run(self):
        """Test partition create with --dry-run (same behavior)."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "create", "--table", "my_table",
                                     "--dry-run"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "notice" in output["data"]

    def test_create_table_format(self):
        """Test partition create with table output format."""
        runner = CliRunner()
        result = runner.invoke(cli, ["-f", "table", "partition", "create",
                                     "--table", "my_table"])

        assert result.exit_code == 0
        assert "notice" in result.output

    def test_create_table_option_required(self):
        """Test partition create without --table fails."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "create"])

        assert result.exit_code != 0
        assert "Missing option" in result.output or "--table" in result.output

    def test_create_short_option(self):
        """Test partition create with -t short option."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "create", "-t", "my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "notice" in output["data"]


class TestPartitionDropCmd:
    """Tests for partition drop command."""

    def test_drop_without_confirm_is_dry_run(self, mock_get_connection):
        """Test drop without --confirm shows dry-run SQL."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],  # _table_exists
            [{"property_value": "true"}],  # _is_logical_partitioned
            [{"property_value": "ds"}],  # _get_partition_columns
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.logs",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "DELETE FROM" in output["data"]["sql"]
        assert "ds = '2025-04-01'" in output["data"]["sql"]
        # Should NOT have called execute for DELETE
        assert mock_get_connection.execute.call_count == 3

    def test_drop_with_confirm_executes(self, mock_get_connection):
        """Test drop with --confirm executes DELETE."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],  # _table_exists
            [{"property_value": "true"}],  # _is_logical_partitioned
            [{"property_value": "ds"}],  # _get_partition_columns
            [],  # DELETE execution
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.logs",
                                     "--partition", "2025-04-01", "--confirm"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["executed"] is True
        assert "DELETE FROM" in output["data"]["sql"]
        assert output["message"] == "Partition dropped successfully"
        # Verify DELETE was called
        assert mock_get_connection.execute.call_count == 4
        delete_call = mock_get_connection.execute.call_args_list[3]
        assert "DELETE FROM" in delete_call[0][0]
        assert delete_call[0][1] == ("2025-04-01",)
        mock_get_connection.close.assert_called_once()

    def test_drop_default_schema(self, mock_get_connection):
        """Test drop defaults to public schema."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "ds"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "my_table",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "public.my_table" in output["data"]["sql"]
        # Verify schema passed as public
        calls = mock_get_connection.execute.call_args_list
        assert calls[0][0][1] == ("public", "my_table")

    def test_drop_with_schema(self, mock_get_connection):
        """Test drop with explicit schema."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "ds"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "myschema.my_table",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "myschema.my_table" in output["data"]["sql"]
        calls = mock_get_connection.execute.call_args_list
        assert calls[0][0][1] == ("myschema", "my_table")

    def test_drop_table_not_found(self, mock_get_connection):
        """Test drop with non-existent table."""
        mock_get_connection.execute.side_effect = [
            [],  # _table_exists returns empty
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.nonexistent",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"

    def test_drop_not_logical_partition(self, mock_get_connection):
        """Test drop with non-logical partition table."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],  # _table_exists
            [],  # _is_logical_partitioned returns empty
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.regular_table",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_LOGICAL_PARTITION"

    def test_drop_invalid_identifier(self, mock_get_connection):
        """Test drop with invalid table name."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.my;table",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_drop_connection_error(self, mocker):
        """Test drop with connection failure."""
        mocker.patch(
            "hologres_cli.commands.partition.get_connection",
            side_effect=DSNError("Connection refused"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.logs",
                                     "--partition", "2025-04-01", "--confirm"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_drop_query_error(self, mock_get_connection):
        """Test drop with SQL execution error."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "ds"}],
            Exception("permission denied"),
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.logs",
                                     "--partition", "2025-04-01", "--confirm"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_drop_partition_required(self):
        """Test drop without --partition fails."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.logs"])

        assert result.exit_code != 0
        assert "Missing option" in result.output or "--partition" in result.output

    def test_drop_table_option_required(self):
        """Test drop without --table fails."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--partition", "2025-04-01"])

        assert result.exit_code != 0
        assert "Missing option" in result.output or "--table" in result.output

    def test_drop_short_option(self, mock_get_connection):
        """Test drop with -t short option."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "ds"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "-t", "public.logs",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True

    def test_drop_verify_delete_sql(self, mock_get_connection):
        """Test that generated DELETE SQL is correct."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "ds"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.logs",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["sql"] == "DELETE FROM public.logs WHERE ds = '2025-04-01'"

    def test_drop_multi_partition_columns(self, mock_get_connection):
        """Test drop with multiple partition columns using key=value format."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "yy,mm"}],  # two partition columns
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.events",
                                     "--partition", "yy=2025,mm=04"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["dry_run"] is True
        assert "yy = '2025'" in output["data"]["sql"]
        assert "mm = '04'" in output["data"]["sql"]
        assert "AND" in output["data"]["sql"]

    def test_drop_multi_partition_column_mismatch(self, mock_get_connection):
        """Test drop with mismatched partition column names."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "yy,mm"}],  # two partition columns
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.events",
                                     "--partition", "xx=2025,zz=04"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"
        assert "mismatch" in output["error"]["message"].lower()

    def test_drop_single_value_for_multi_column_table(self, mock_get_connection):
        """Test drop with single value for multi-column partition table."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "yy,mm"}],  # two partition columns
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.events",
                                     "--partition", "2025"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"

    def test_drop_single_column_key_value_format(self, mock_get_connection):
        """Test drop with key=value format for single column table."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "ds"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "drop", "--table", "public.logs",
                                     "--partition", "ds=2025-04-01"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "ds = '2025-04-01'" in output["data"]["sql"]

    def test_drop_table_format(self, mock_get_connection):
        """Test drop with table output format."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"property_value": "ds"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["-f", "table", "partition", "drop",
                                     "--table", "public.logs",
                                     "--partition", "2025-04-01"])

        assert result.exit_code == 0
        assert "dry_run" in result.output or "sql" in result.output


class TestPartitionListCmd:
    """Tests for partition list command."""

    def test_list_success(self, mock_get_connection):
        """Test successful partition list."""
        mock_get_connection.execute.side_effect = [
            # _table_exists
            [{"?column?": 1}],
            # _is_logical_partitioned
            [{"property_value": "true"}],
            # hg_list_logical_partition
            [
                {"partition": "2025-04-01"},
                {"partition": "2025-04-02"},
                {"partition": "2025-04-03"},
            ],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "--table", "public.logs"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 3
        assert output["data"]["rows"][0]["partition"] == "2025-04-01"
        assert output["data"]["rows"][2]["partition"] == "2025-04-03"
        mock_get_connection.close.assert_called_once()

    def test_list_empty(self, mock_get_connection):
        """Test partition list with no partitions."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "--table", "public.logs"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_table_not_found(self, mock_get_connection):
        """Test partition list with non-existent table."""
        mock_get_connection.execute.side_effect = [
            [],  # _table_exists returns empty
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "--table", "public.nonexistent"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"
        assert "nonexistent" in output["error"]["message"]

    def test_not_logical_partition(self, mock_get_connection):
        """Test partition list with non-logical partition table."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],  # _table_exists
            [],  # _is_logical_partitioned returns empty
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "--table",
                                     "public.regular_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "NOT_LOGICAL_PARTITION"
        assert "logical partition" in output["error"]["message"].lower()

    def test_default_schema(self, mock_get_connection):
        """Test partition list defaults to public schema."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"partition": "2025-01-01"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "--table", "my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        # Verify the SQL contains public.my_table
        calls = mock_get_connection.execute.call_args_list
        partition_sql = calls[2][0][0]
        assert "public.my_table" in partition_sql

    def test_with_schema(self, mock_get_connection):
        """Test partition list with explicit schema."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"partition": "2025-01-01"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "--table",
                                     "myschema.my_table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        # Verify schema passed correctly
        calls = mock_get_connection.execute.call_args_list
        # _table_exists call
        assert calls[0][0][1] == ("myschema", "my_table")
        # _is_logical_partitioned call
        assert calls[1][0][1] == ("myschema", "my_table")
        # hg_list_logical_partition call
        partition_sql = calls[2][0][0]
        assert "myschema.my_table" in partition_sql

    def test_invalid_identifier(self, mock_get_connection):
        """Test partition list with invalid table name."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "--table", "public.my;table"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_INPUT"

    def test_connection_error(self, mocker):
        """Test partition list with connection failure."""
        mocker.patch(
            "hologres_cli.commands.partition.get_connection",
            side_effect=DSNError("Connection refused"),
        )

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "--table", "public.logs"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_query_error(self, mock_get_connection):
        """Test partition list with SQL execution error."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            Exception("relation does not exist"),
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "--table", "public.logs"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_table_format(self, mock_get_connection):
        """Test partition list with table output format."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [
                {"partition": "2025-04-01"},
                {"partition": "2025-04-02"},
            ],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["-f", "table", "partition", "list",
                                     "--table", "public.logs"])

        assert result.exit_code == 0
        assert "partition" in result.output
        assert "2025-04-01" in result.output

    def test_csv_format(self, mock_get_connection):
        """Test partition list with CSV output format."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [
                {"partition": "2025-04-01"},
                {"partition": "2025-04-02"},
            ],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["-f", "csv", "partition", "list",
                                     "--table", "public.logs"])

        assert result.exit_code == 0
        assert "partition" in result.output
        assert "2025-04-01" in result.output

    def test_list_table_option_required(self):
        """Test partition list without --table fails."""
        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list"])

        assert result.exit_code != 0
        assert "Missing option" in result.output or "--table" in result.output

    def test_list_short_option(self, mock_get_connection):
        """Test partition list with -t short option."""
        mock_get_connection.execute.side_effect = [
            [{"?column?": 1}],
            [{"property_value": "true"}],
            [{"partition": "2025-01-01"}],
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["partition", "list", "-t", "public.logs"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
