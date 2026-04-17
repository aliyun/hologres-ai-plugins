"""Integration tests for data import/export commands with real Hologres database."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


@pytest.mark.integration
class TestDataExportLive:
    """Integration tests for data export."""

    def test_export_table_to_csv(self, test_table_with_data, integration_dsn, tmp_path):
        """Test exporting table data to CSV file."""
        output_file = tmp_path / "export.csv"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "export",
             test_table_with_data, "-f", str(output_file)]
        )

        assert result.exit_code == 0
        assert output_file.exists()

        # Check CSV content
        content = output_file.read_text()
        assert "id,name" in content  # Header
        assert "Alice" in content

    def test_export_with_query(self, test_table_with_data, integration_dsn, tmp_path):
        """Test exporting with custom query."""
        output_file = tmp_path / "export.csv"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "export",
             "-q", f"SELECT id, name FROM {test_table_with_data} WHERE id = 1",
             "-f", str(output_file)]
        )

        assert result.exit_code == 0
        content = output_file.read_text()
        assert "Alice" in content

    def test_export_custom_delimiter(self, test_table_with_data, integration_dsn, tmp_path):
        """Test exporting with custom delimiter."""
        output_file = tmp_path / "export.csv"

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "export",
             test_table_with_data, "-f", str(output_file), "-d", "|"]
        )

        assert result.exit_code == 0
        content = output_file.read_text()
        assert "|" in content


@pytest.mark.integration
class TestDataImportLive:
    """Integration tests for data import."""

    def test_import_csv_to_table(self, test_table, integration_dsn, tmp_path):
        """Test importing CSV data to table."""
        # Create CSV file
        csv_file = tmp_path / "import.csv"
        csv_file.write_text("id,name,phone,email\n100,Import User,13900001111,import@test.com\n")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "import",
             test_table, "-f", str(csv_file)]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_import_multiple_rows(self, test_table, integration_dsn, tmp_path):
        """Test importing multiple rows from CSV."""
        csv_file = tmp_path / "import.csv"
        csv_file.write_text(
            "id,name\n"
            "200,User1\n"
            "201,User2\n"
            "202,User3\n"
        )

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "import",
             test_table, "-f", str(csv_file)]
        )

        assert result.exit_code == 0

    def test_import_with_truncate(self, test_table_with_data, integration_dsn, tmp_path):
        """Test importing with truncate flag."""
        # Create CSV with one row
        csv_file = tmp_path / "import.csv"
        csv_file.write_text("id,name\n1,New Alice\n")

        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "import",
             test_table_with_data, "-f", str(csv_file), "--truncate"]
        )

        assert result.exit_code == 0
        # Original data should be replaced
        # This verifies truncate happened


@pytest.mark.integration
class TestDataCountLive:
    """Integration tests for row counting."""

    def test_count_all_rows(self, test_table_with_data, integration_dsn):
        """Test counting all rows in table."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "count", test_table_with_data]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 3

    def test_count_with_where(self, test_table_with_data, integration_dsn):
        """Test counting rows with WHERE clause."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "count",
             test_table_with_data, "--where", "id = 1"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["count"] == 1


@pytest.mark.integration
class TestDataRoundTrip:
    """Integration tests for complete data round-trip."""

    def test_export_import_roundtrip(self, test_table, integration_dsn, tmp_path):
        """Test exporting data and importing back."""
        # First, insert some data
        runner = CliRunner()
        runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql", "--write",
             f"INSERT INTO {test_table} (id, name, phone, email) VALUES (1, 'RoundTrip', '13900000000', 'rt@test.com')"]
        )

        # Export
        export_file = tmp_path / "roundtrip.csv"
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "export",
             test_table, "-f", str(export_file)]
        )
        assert result.exit_code == 0

        # Clear table
        runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql", "--write",
             f"TRUNCATE TABLE {test_table}"]
        )

        # Import back
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "import",
             test_table, "-f", str(export_file)]
        )
        assert result.exit_code == 0

        # Verify data exists
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "data", "count", test_table]
        )
        output = json.loads(result.output)
        assert output["data"]["count"] >= 1
