"""Integration tests for warehouse command with real Hologres database."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


@pytest.mark.integration
class TestWarehouseLive:
    """Integration tests for warehouse command."""

    def test_list_warehouses(self, integration_dsn):
        """Test listing all warehouses."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--dsn", integration_dsn, "warehouse"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert isinstance(output["data"]["rows"], list)

    def test_query_specific_warehouse(self, integration_dsn):
        """Test querying a specific warehouse by name."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--dsn", integration_dsn, "warehouse", "init_warehouse"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_warehouse_table_format(self, integration_dsn):
        """Test warehouse with table format output."""
        runner = CliRunner()
        result = runner.invoke(
            cli, ["--dsn", integration_dsn, "--format", "table", "warehouse"]
        )

        assert result.exit_code == 0
