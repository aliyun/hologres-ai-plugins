"""Integration tests for output format variants across commands."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


@pytest.mark.integration
class TestSqlOutputFormatsLive:
    """Integration tests for SQL output format variants."""

    def test_sql_csv_format(self, integration_dsn):
        """Test SQL query with CSV format output."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "--format", "csv",
             "sql", "SELECT 1 AS id, 'test' AS name"]
        )

        assert result.exit_code == 0
        assert "id,name" in result.output
        assert "1,test" in result.output

    def test_sql_jsonl_format(self, integration_dsn):
        """Test SQL query with JSONL format output."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "--format", "jsonl",
             "sql", "SELECT 1 AS id"]
        )

        assert result.exit_code == 0
        line = result.output.strip().split("\n")[0]
        row = json.loads(line)
        assert row["id"] == 1


@pytest.mark.integration
class TestDataOutputFormatsLive:
    """Integration tests for data command output format variants."""

    def test_data_count_csv_format(self, test_table_with_data, integration_dsn):
        """Test data count with CSV format output."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "--format", "csv",
             "data", "count", test_table_with_data]
        )

        assert result.exit_code == 0


@pytest.mark.integration
class TestSchemaOutputFormatsLive:
    """Integration tests for schema command output format variants."""

    def test_schema_tables_jsonl_format(self, test_table_with_data, integration_dsn):
        """Test schema tables with JSONL format output."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "--format", "jsonl",
             "schema", "tables"]
        )

        assert result.exit_code == 0
        # JSONL should have at least one line with valid JSON
        lines = [l for l in result.output.strip().split("\n") if l]
        assert len(lines) >= 1
        row = json.loads(lines[0])
        assert "schema" in row
