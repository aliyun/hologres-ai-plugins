"""Tests for data command module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli


class TestExportCmd:
    """Tests for data export command."""

    def test_export_cmd_table_success(self, mock_get_connection, tmp_path):
        """Test successful table export to CSV."""
        output_file = tmp_path / "output.csv"

        # Mock cursor and copy operation
        mock_cursor = MagicMock()
        mock_copy = MagicMock()
        mock_copy.__enter__ = MagicMock(return_value=iter([b"id,name\n1,Alice\n"]))
        mock_copy.__exit__ = MagicMock(return_value=None)
        mock_cursor.copy.return_value = mock_copy
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_get_connection.cursor.return_value = mock_cursor

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "export", "users", "-f", str(output_file)])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_export_cmd_query_success(self, mock_get_connection, tmp_path):
        """Test successful query export to CSV."""
        output_file = tmp_path / "output.csv"

        mock_cursor = MagicMock()
        mock_copy = MagicMock()
        mock_copy.__enter__ = MagicMock(return_value=iter([b"count\n100\n"]))
        mock_copy.__exit__ = MagicMock(return_value=None)
        mock_cursor.copy.return_value = mock_copy
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_get_connection.cursor.return_value = mock_cursor

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "export", "-f", str(output_file), "-q", "SELECT COUNT(*) FROM users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_export_cmd_custom_delimiter(self, mock_get_connection, tmp_path):
        """Test export with custom delimiter."""
        output_file = tmp_path / "output.csv"

        mock_cursor = MagicMock()
        mock_copy = MagicMock()
        mock_copy.__enter__ = MagicMock(return_value=iter([b"id|name\n1|Alice\n"]))
        mock_copy.__exit__ = MagicMock(return_value=None)
        mock_cursor.copy.return_value = mock_copy
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_get_connection.cursor.return_value = mock_cursor

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "export", "users", "-f", str(output_file), "-d", "|"])

        assert result.exit_code == 0

    def test_export_cmd_no_table_or_query(self):
        """Test export without table or query returns error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["data", "export", "-f", "/tmp/out.csv"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "INVALID_ARGS"

    def test_export_cmd_copy_error(self, mock_get_connection, tmp_path):
        """Test export failure during COPY."""
        output_file = tmp_path / "output.csv"

        mock_cursor = MagicMock()
        mock_cursor.copy.side_effect = Exception("COPY failed")
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_get_connection.cursor.return_value = mock_cursor

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "export", "users", "-f", str(output_file)])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "EXPORT_ERROR"

    def test_export_cmd_connection_error(self, mocker, tmp_path):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.data.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "export", "users", "-f", str(tmp_path / "out.csv")])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"


class TestImportCmd:
    """Tests for data import command."""

    def test_import_cmd_success(self, mock_get_connection, tmp_path):
        """Test successful CSV import."""
        input_file = tmp_path / "input.csv"
        input_file.write_text("id,name\n1,Alice\n2,Bob\n")

        mock_cursor = MagicMock()
        mock_copy = MagicMock()
        mock_copy.__enter__ = MagicMock(return_value=mock_copy)
        mock_copy.__exit__ = MagicMock(return_value=None)
        mock_copy.write = MagicMock()
        mock_cursor.copy.return_value = mock_copy
        mock_cursor.execute = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_get_connection.cursor.return_value = mock_cursor

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "import", "users", "-f", str(input_file)])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_import_cmd_with_truncate(self, mock_get_connection, tmp_path):
        """Test import with truncate flag."""
        input_file = tmp_path / "input.csv"
        input_file.write_text("id,name\n1,Alice\n")

        mock_cursor = MagicMock()
        mock_copy = MagicMock()
        mock_copy.__enter__ = MagicMock(return_value=mock_copy)
        mock_copy.__exit__ = MagicMock(return_value=None)
        mock_copy.write = MagicMock()
        mock_cursor.copy.return_value = mock_copy
        mock_cursor.execute = MagicMock()
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_get_connection.cursor.return_value = mock_cursor

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "import", "users", "-f", str(input_file), "--truncate"])

        assert result.exit_code == 0
        mock_cursor.execute.assert_called()

    def test_import_cmd_file_not_found(self):
        """Test import with non-existent file."""
        runner = CliRunner()
        result = runner.invoke(cli, ["data", "import", "users", "-f", "/nonexistent/file.csv"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "FILE_NOT_FOUND"

    def test_import_cmd_connection_error(self, mocker, tmp_path):
        """Test connection error handling."""
        input_file = tmp_path / "input.csv"
        input_file.write_text("id,name\n")

        mocker.patch("hologres_cli.commands.data.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "import", "users", "-f", str(input_file)])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_import_cmd_query_error(self, mock_get_connection, tmp_path):
        """Test import failure reports error correctly."""
        input_file = tmp_path / "input.csv"
        input_file.write_text("id,name\n")

        mock_cursor = MagicMock()
        mock_cursor.copy.side_effect = Exception("Import failed")
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=None)
        mock_get_connection.cursor.return_value = mock_cursor

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "import", "users", "-f", str(input_file)])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "IMPORT_ERROR"


class TestCountCmd:
    """Tests for data count command."""

    def test_count_cmd_success(self, mock_get_connection):
        """Test successful row count."""
        mock_get_connection.execute.return_value = [{"count": 100}]

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "count", "users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 100

    def test_count_cmd_with_where(self, mock_get_connection):
        """Test count with WHERE clause."""
        mock_get_connection.execute.return_value = [{"count": 50}]

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "count", "users", "-w", "status = 'active'"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["data"]["count"] == 50
        # Verify WHERE clause is in the SQL
        call_args = mock_get_connection.execute.call_args
        assert "WHERE" in call_args[0][0]

    def test_count_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.data.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "count", "users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_count_cmd_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("Table not found")

        runner = CliRunner()
        result = runner.invoke(cli, ["data", "count", "nonexistent"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"
