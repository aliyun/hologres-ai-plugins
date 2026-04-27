"""Tests for partition command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


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
        result = runner.invoke(cli, ["partition", "list", "public.logs"])

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
        result = runner.invoke(cli, ["partition", "list", "public.logs"])

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
        result = runner.invoke(cli, ["partition", "list", "public.nonexistent"])

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
        result = runner.invoke(cli, ["partition", "list", "public.regular_table"])

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
        result = runner.invoke(cli, ["partition", "list", "my_table"])

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
        result = runner.invoke(cli, ["partition", "list", "myschema.my_table"])

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
        result = runner.invoke(cli, ["partition", "list", "public.my;table"])

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
        result = runner.invoke(cli, ["partition", "list", "public.logs"])

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
        result = runner.invoke(cli, ["partition", "list", "public.logs"])

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
        result = runner.invoke(cli, ["-f", "table", "partition", "list", "public.logs"])

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
        result = runner.invoke(cli, ["-f", "csv", "partition", "list", "public.logs"])

        assert result.exit_code == 0
        assert "partition" in result.output
        assert "2025-04-01" in result.output
