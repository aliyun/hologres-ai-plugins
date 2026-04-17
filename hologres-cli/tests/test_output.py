"""Tests for output module."""

from __future__ import annotations

import json

import pytest

from hologres_cli.output import (
    FORMAT_CSV,
    FORMAT_JSON,
    FORMAT_JSONL,
    FORMAT_TABLE,
    connection_error,
    dangerous_write_error,
    error,
    limit_required_error,
    print_output,
    query_error,
    success,
    success_rows,
    write_guard_error,
    _format_csv,
    _format_jsonl,
    _format_table,
)


class TestSuccess:
    """Tests for success function."""

    def test_success_json_default(self):
        """Test default JSON format."""
        result = success({"key": "value"})
        data = json.loads(result)
        assert data["ok"] is True
        assert data["data"] == {"key": "value"}

    def test_success_with_message(self):
        """Test success with message."""
        result = success({"count": 10}, message="Query completed")
        data = json.loads(result)
        assert data["ok"] is True
        assert data["message"] == "Query completed"

    def test_success_table_format_list(self):
        """Test table format with list data."""
        data = [{"id": 1, "name": "Alice"}, {"id": 2, "name": "Bob"}]
        result = success(data, format=FORMAT_TABLE)
        assert "Alice" in result
        assert "Bob" in result

    def test_success_table_format_dict(self):
        """Test table format with dict data."""
        result = success({"key1": "value1", "key2": "value2"}, format=FORMAT_TABLE)
        assert "key1" in result
        assert "value1" in result

    def test_success_csv_format(self):
        """Test CSV format with list data."""
        data = [{"id": 1, "name": "Alice"}]
        result = success(data, format=FORMAT_CSV)
        assert "id,name" in result
        assert "1,Alice" in result

    def test_success_jsonl_format(self):
        """Test JSONL format with list data."""
        data = [{"id": 1}, {"id": 2}]
        result = success(data, format=FORMAT_JSONL)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"id": 1}

    def test_success_table_scalar_data(self):
        """Test table format with scalar data."""
        result = success("scalar value", format=FORMAT_TABLE)
        assert result == "scalar value"


class TestSuccessRows:
    """Tests for success_rows function."""

    def test_success_rows_json(self):
        """Test JSON format."""
        rows = [{"id": 1}, {"id": 2}]
        result = success_rows(rows, format=FORMAT_JSON)
        data = json.loads(result)
        assert data["ok"] is True
        assert data["data"]["rows"] == rows
        assert data["data"]["count"] == 2

    def test_success_rows_table(self):
        """Test table format."""
        rows = [{"id": 1, "name": "Alice"}]
        result = success_rows(rows, format=FORMAT_TABLE)
        assert "id" in result
        assert "Alice" in result

    def test_success_rows_csv(self):
        """Test CSV format."""
        rows = [{"id": 1, "name": "Alice"}]
        result = success_rows(rows, format=FORMAT_CSV)
        assert "id,name" in result
        assert "1,Alice" in result

    def test_success_rows_jsonl(self):
        """Test JSONL format."""
        rows = [{"id": 1}, {"id": 2}]
        result = success_rows(rows, format=FORMAT_JSONL)
        lines = result.strip().split("\n")
        assert len(lines) == 2

    def test_success_rows_with_total_count(self):
        """Test with total_count."""
        rows = [{"id": 1}]
        result = success_rows(rows, format=FORMAT_JSON, total_count=100)
        data = json.loads(result)
        assert data["data"]["total_count"] == 100

    def test_success_rows_with_message(self):
        """Test with message."""
        rows = [{"id": 1}]
        result = success_rows(rows, format=FORMAT_JSON, message="Found")
        data = json.loads(result)
        assert data["message"] == "Found"

    def test_success_rows_custom_columns_table(self):
        """Test table format with custom columns."""
        rows = [{"id": 1, "name": "Alice", "email": "alice@example.com"}]
        result = success_rows(rows, format=FORMAT_TABLE, columns=["id", "name"])
        assert "id" in result
        assert "name" in result
        assert "email" not in result  # Column not in output headers

    def test_success_rows_custom_columns_csv(self):
        """Test CSV format with custom columns."""
        rows = [{"id": 1, "name": "Alice", "email": "alice@example.com"}]
        result = success_rows(rows, format=FORMAT_CSV, columns=["id", "name"])
        assert "id,name" in result
        assert "email" not in result


class TestError:
    """Tests for error function."""

    def test_error_basic(self):
        """Test basic error."""
        result = error("TEST_ERROR", "Something went wrong")
        data = json.loads(result)
        assert data["ok"] is False
        assert data["error"]["code"] == "TEST_ERROR"
        assert data["error"]["message"] == "Something went wrong"

    def test_error_with_details(self):
        """Test error with details."""
        result = error("TEST_ERROR", "Error", details={"field": "value"})
        data = json.loads(result)
        assert data["error"]["details"] == {"field": "value"}

    def test_error_json_output(self):
        """Test JSON output format."""
        result = error("CODE", "msg")
        # Should be valid JSON
        data = json.loads(result)
        assert isinstance(data, dict)


class TestFormatTable:
    """Tests for _format_table function."""

    def test_format_table_empty(self):
        """Test empty rows returns placeholder."""
        result = _format_table([])
        assert result == "(no rows)"

    def test_format_table_with_data(self):
        """Test rows with data."""
        rows = [{"id": 1, "name": "Alice"}]
        result = _format_table(rows)
        assert "id" in result
        assert "name" in result
        assert "Alice" in result

    def test_format_table_custom_columns(self):
        """Test custom column list."""
        rows = [{"id": 1, "name": "Alice", "email": "alice@example.com"}]
        result = _format_table(rows, columns=["id", "name"])
        assert "id" in result
        assert "name" in result

    def test_format_table_missing_values(self):
        """Test rows with missing keys."""
        rows = [{"id": 1, "name": "Alice"}, {"id": 2}]  # Second row missing name
        result = _format_table(rows, columns=["id", "name"])
        # Missing values should be empty string
        assert "1" in result
        assert "2" in result

    def test_format_table_multiple_rows(self):
        """Test multiple rows."""
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
            {"id": 3, "name": "Charlie"},
        ]
        result = _format_table(rows)
        assert "Alice" in result
        assert "Bob" in result
        assert "Charlie" in result


class TestFormatCsv:
    """Tests for _format_csv function."""

    def test_format_csv_empty(self):
        """Test empty rows returns empty string."""
        result = _format_csv([])
        assert result == ""

    def test_format_csv_with_data(self):
        """Test rows with data."""
        rows = [{"id": 1, "name": "Alice"}]
        result = _format_csv(rows)
        assert "id,name" in result
        assert "1,Alice" in result

    def test_format_csv_custom_columns(self):
        """Test custom column list."""
        rows = [{"id": 1, "name": "Alice", "secret": "hidden"}]
        result = _format_csv(rows, columns=["id", "name"])
        assert "id,name" in result
        assert "secret" not in result

    def test_format_csv_extras_ignored(self):
        """Test extra fields in rows are ignored."""
        rows = [{"id": 1, "name": "Alice", "extra": "value"}]
        result = _format_csv(rows, columns=["id", "name"])
        # extrasaction='ignore' means extra field is silently dropped
        assert "extra" not in result

    def test_format_csv_multiple_rows(self):
        """Test multiple rows."""
        rows = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]
        result = _format_csv(rows)
        lines = result.strip().split("\n")
        assert len(lines) == 3  # header + 2 data rows

    def test_format_csv_special_characters(self):
        """Test CSV with special characters."""
        rows = [{"id": 1, "name": "Alice, Bob"}]
        result = _format_csv(rows)
        # Should be quoted properly
        assert '"Alice, Bob"' in result


class TestFormatJsonl:
    """Tests for _format_jsonl function."""

    def test_format_jsonl_empty(self):
        """Test empty list returns empty string."""
        result = _format_jsonl([])
        assert result == ""

    def test_format_jsonl_with_data(self):
        """Test rows with data."""
        rows = [{"id": 1}, {"id": 2}]
        result = _format_jsonl(rows)
        lines = result.strip().split("\n")
        assert len(lines) == 2
        assert json.loads(lines[0]) == {"id": 1}
        assert json.loads(lines[1]) == {"id": 2}

    def test_format_jsonl_unicode(self):
        """Test Unicode characters are preserved."""
        rows = [{"name": "中文测试"}]
        result = _format_jsonl(rows)
        assert "中文测试" in result

    def test_format_jsonl_single_row(self):
        """Test single row."""
        rows = [{"id": 1, "name": "Alice"}]
        result = _format_jsonl(rows)
        data = json.loads(result)
        assert data == {"id": 1, "name": "Alice"}


class TestErrorHelpers:
    """Tests for error helper functions."""

    def test_connection_error(self):
        """Test connection_error helper."""
        result = connection_error("Connection refused")
        data = json.loads(result)
        assert data["ok"] is False
        assert data["error"]["code"] == "CONNECTION_ERROR"
        assert data["error"]["message"] == "Connection refused"

    def test_query_error(self):
        """Test query_error helper."""
        result = query_error("Syntax error")
        data = json.loads(result)
        assert data["ok"] is False
        assert data["error"]["code"] == "QUERY_ERROR"

    def test_query_error_with_details(self):
        """Test query_error with details."""
        result = query_error("Error", details={"line": 1})
        data = json.loads(result)
        assert data["error"]["details"] == {"line": 1}

    def test_limit_required_error(self):
        """Test limit_required_error helper."""
        result = limit_required_error()
        data = json.loads(result)
        assert data["ok"] is False
        assert data["error"]["code"] == "LIMIT_REQUIRED"
        assert "100 rows" in data["error"]["message"]

    def test_write_guard_error(self):
        """Test write_guard_error helper."""
        result = write_guard_error()
        data = json.loads(result)
        assert data["ok"] is False
        assert data["error"]["code"] == "WRITE_GUARD_ERROR"
        assert "--write flag" in data["error"]["message"]

    def test_dangerous_write_error(self):
        """Test dangerous_write_error helper."""
        result = dangerous_write_error("DELETE")
        data = json.loads(result)
        assert data["ok"] is False
        assert data["error"]["code"] == "DANGEROUS_WRITE_BLOCKED"
        assert "DELETE" in data["error"]["message"]
        assert "WHERE" in data["error"]["message"]


class TestPrintOutput:
    """Tests for print_output function."""

    def test_print_output_default(self, capsys):
        """Test print to stdout by default."""
        print_output("test output")
        captured = capsys.readouterr()
        assert "test output" in captured.out

    def test_print_output_custom_file(self, tmp_path):
        """Test print to custom file."""
        output_file = tmp_path / "output.txt"
        with open(output_file, "w") as f:
            print_output("test output", file=f)
        assert "test output" in output_file.read_text()
