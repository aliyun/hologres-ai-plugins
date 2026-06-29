"""Integration tests for CLI commands executed via Hologram OpenAPI (ExecuteStatement)."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.api_connection import HologresApiConnection
from hologres_cli.connection import get_connection
from hologres_cli.main import cli


@pytest.mark.integration
class TestApiStatusCommand:
    """hologres status via API mode."""

    def test_status_connected(self, api_test_profile: str):
        """Status command succeeds with API profile."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--profile", api_test_profile, "status"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["status"] == "connected"
        assert "Hologres" in output["data"]["version"] or "PostgreSQL" in output["data"]["version"]


@pytest.mark.integration
class TestApiSqlCommand:
    """hologres sql run via API mode."""

    def test_cli_sql_run(self, api_test_profile: str):
        """sql run SELECT 1 succeeds via API."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", api_test_profile, "sql", "run", "SELECT 1 AS value"
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 1

    def test_cli_sql_run_with_limit(self, api_test_profile: str):
        """sql run with LIMIT clause works."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", api_test_profile, "sql", "run",
            "SELECT generate_series(1, 5) AS n"
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["rows"]) == 5


@pytest.mark.integration
class TestApiTableCommand:
    """hologres table commands via API mode."""

    def test_table_list(self, api_test_profile: str):
        """table list returns table information."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", api_test_profile, "table", "list"
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] >= 0

    def test_table_show(self, api_test_table: str, api_test_profile: str):
        """table show returns table structure."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", api_test_profile, "table", "show", api_test_table
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "columns" in output["data"]
        col_names = [c["column_name"] for c in output["data"]["columns"]]
        assert "id" in col_names
        assert "name" in col_names

    def test_table_size(self, api_test_table: str, api_test_profile: str):
        """table size returns storage information."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", api_test_profile, "table", "size", api_test_table
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "size" in output["data"]


@pytest.mark.integration
class TestApiSchemaCommand:
    """hologres schema commands via API mode."""

    def test_schema_tables(self, api_test_profile: str):
        """schema tables returns table list."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", api_test_profile, "schema", "tables"
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] >= 0

    def test_schema_describe(self, api_test_table: str, api_test_profile: str):
        """schema describe returns column information."""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "--profile", api_test_profile, "schema", "describe", api_test_table
        ])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "columns" in output["data"]


@pytest.mark.integration
class TestApiConnectionMode:
    """Verify get_connection() returns the correct connection type for API mode."""

    def test_get_connection_returns_api_connection(self, api_test_profile: str):
        """get_connection() with API profile returns HologresApiConnection."""
        conn = get_connection(api_test_profile)
        try:
            assert isinstance(conn, HologresApiConnection)
        finally:
            conn.close()

    def test_api_connection_execute_sql(self, api_test_profile: str):
        """get_connection() → HologresApiConnection → execute SQL succeeds."""
        conn = get_connection(api_test_profile)
        try:
            result = conn.execute("SELECT 1 AS value")
            assert len(result) == 1
        finally:
            conn.close()
