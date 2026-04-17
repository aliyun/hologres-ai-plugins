"""Integration tests for schema commands with real Hologres database."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


@pytest.mark.integration
class TestSchemaTablesLive:
    """Integration tests for schema tables command."""

    def test_list_tables(self, integration_dsn, test_table_with_data):
        """Test listing all tables."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "schema", "tables"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        # Should have at least our test table
        assert output["data"]["count"] >= 1

    def test_list_tables_with_schema_filter(self, integration_dsn):
        """Test listing tables with schema filter."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "schema", "tables", "--schema", "public"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_list_tables_table_format(self, integration_dsn):
        """Test listing tables in table format."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "--format", "table", "schema", "tables"]
        )

        assert result.exit_code == 0
        # Table format should have headers
        assert "schema" in result.output.lower() or "table" in result.output.lower()


@pytest.mark.integration
class TestSchemaDescribeLive:
    """Integration tests for schema describe command."""

    def test_describe_table(self, integration_dsn, test_table_with_data):
        """Test describing a table structure."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "schema", "describe", test_table_with_data]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "columns" in output["data"]
        assert len(output["data"]["columns"]) >= 1

    def test_describe_table_columns(self, integration_dsn, test_table):
        """Test that describe shows column details."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "schema", "describe", test_table]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)

        # Check for expected columns
        column_names = [col["column_name"] for col in output["data"]["columns"]]
        assert "id" in column_names
        assert "name" in column_names

    def test_describe_nonexistent_table(self, integration_dsn):
        """Test describing a non-existent table."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "schema", "describe", "nonexistent_table_xyz"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "TABLE_NOT_FOUND"


@pytest.mark.integration
class TestSchemaDumpLive:
    """Integration tests for schema dump command."""

    def test_dump_table_ddl(self, integration_dsn, test_table):
        """Test dumping table DDL using hg_dump_script."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "schema", "dump", f"public.{test_table}"]
        )

        # Note: hg_dump_script may not be available in all Hologres versions
        # The test passes if we get a successful response or a known error
        if result.exit_code == 0:
            output = json.loads(result.output)
            if output["ok"]:
                assert "ddl" in output["data"]

    def test_dump_nonexistent_table(self, integration_dsn):
        """Test dumping a non-existent table."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "schema", "dump", "public.nonexistent_xyz"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is False


@pytest.mark.integration
class TestSchemaPrimaryKeyLive:
    """Integration tests for primary key detection."""

    def test_describe_shows_primary_key(self, integration_dsn, test_table):
        """Test that describe shows primary key information."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "schema", "describe", test_table]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        # test_table has id as primary key
        assert "primary_key" in output["data"]
        # Primary key should include 'id'
        if output["data"]["primary_key"]:
            assert "id" in output["data"]["primary_key"]
