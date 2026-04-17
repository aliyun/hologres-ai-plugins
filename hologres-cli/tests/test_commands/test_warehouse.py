"""Tests for warehouse command module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


class TestWarehouseCmd:
    """Tests for warehouse command."""

    def test_warehouse_cmd_list_all(self, mock_get_connection):
        """Test listing all warehouses."""
        mock_get_connection.execute.return_value = [
            {
                "warehouse_id": 1,
                "warehouse_name": "init_warehouse",
                "cpu": 4,
                "mem": 16,
                "status": 1,
                "target_status": 1,
                "is_default": True,
            },
            {
                "warehouse_id": 2,
                "warehouse_name": "etl_warehouse",
                "cpu": 8,
                "mem": 32,
                "status": 2,
                "target_status": 2,
                "is_default": False,
            },
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["warehouse"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 2
        mock_get_connection.close.assert_called_once()

    def test_warehouse_cmd_filter_by_name(self, mock_get_connection):
        """Test filtering by warehouse name."""
        mock_get_connection.execute.return_value = [
            {
                "warehouse_id": 1,
                "warehouse_name": "init_warehouse",
                "cpu": 4,
                "mem": 16,
                "status": 1,
                "target_status": 1,
            },
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["warehouse", "init_warehouse"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        # Verify query includes WHERE clause
        call_args = mock_get_connection.execute.call_args
        assert "init_warehouse" in str(call_args)

    def test_warehouse_cmd_status_enrichment(self, mock_get_connection):
        """Test status code mapping to descriptions."""
        mock_get_connection.execute.return_value = [
            {"warehouse_name": "w1", "status": 0, "target_status": 1},  # initializing
            {"warehouse_name": "w2", "status": 1, "target_status": 1},  # running
            {"warehouse_name": "w3", "status": 2, "target_status": 2},  # stopped
            {"warehouse_name": "w4", "status": 3, "target_status": 1},  # failed
            {"warehouse_name": "w5", "status": 4, "target_status": 1},  # processing
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["warehouse"])

        output = json.loads(result.output)
        rows = output["data"]["rows"]

        status_map = {r["warehouse_name"]: r for r in rows}
        assert status_map["w1"]["status_desc"] == "initializing"
        assert status_map["w2"]["status_desc"] == "running"
        assert status_map["w3"]["status_desc"] == "stopped"
        assert status_map["w4"]["status_desc"] == "failed"
        assert status_map["w5"]["status_desc"] == "processing"

        # Check target_status_desc
        assert status_map["w1"]["target_status_desc"] == "running"
        assert status_map["w3"]["target_status_desc"] == "stopped"

    def test_warehouse_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.warehouse.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["warehouse"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_warehouse_cmd_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("Table hologres.hg_warehouses not found")

        runner = CliRunner()
        result = runner.invoke(cli, ["warehouse"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_warehouse_cmd_empty_result(self, mock_get_connection):
        """Test empty warehouse list."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["warehouse"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["rows"] == []
        assert output["data"]["count"] == 0

    def test_warehouse_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.return_value = [
            {"warehouse_name": "init_warehouse", "cpu": 4, "mem": 16, "status": 1},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "warehouse"])

        assert result.exit_code == 0
        assert "init_warehouse" in result.output

    def test_warehouse_cmd_missing_status_field(self, mock_get_connection):
        """Test handling rows without status field."""
        mock_get_connection.execute.return_value = [
            {"warehouse_name": "w1"},  # No status field
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["warehouse"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        # Should not have status_desc if status field is missing
        assert "status_desc" not in output["data"]["rows"][0]
