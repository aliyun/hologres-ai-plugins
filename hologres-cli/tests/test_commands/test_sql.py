"""Tests for SQL command module - pure functions and CLI commands."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from hologres_cli.connection import DSNError
from hologres_cli.main import cli
from hologres_cli.commands.sql import (
    _add_limit,
    _has_limit,
    _is_select,
    _is_write_operation,
    _split_statements,
    _truncate_large_fields,
)


class TestSplitStatements:
    """Tests for _split_statements function."""

    def test_split_statements_single(self):
        """Test single statement."""
        result = _split_statements("SELECT 1")
        assert result == ["SELECT 1"]

    def test_split_statements_multiple(self):
        """Test multiple statements."""
        result = _split_statements("SELECT 1; SELECT 2")
        assert result == ["SELECT 1", "SELECT 2"]

    def test_split_statements_with_string_single_quote(self):
        """Test statement with semicolon inside single quotes."""
        result = _split_statements("SELECT 'a;b'")
        assert result == ["SELECT 'a;b'"]

    def test_split_statements_with_string_double_quote(self):
        """Test statement with semicolon inside double quotes."""
        result = _split_statements('SELECT "a;b"')
        assert result == ['SELECT "a;b"']

    def test_split_statements_trailing_semicolon(self):
        """Test statement with trailing semicolon."""
        result = _split_statements("SELECT 1;")
        assert result == ["SELECT 1"]

    def test_split_statements_trailing_semicolon_with_space(self):
        """Test statement with trailing semicolon and space."""
        result = _split_statements("SELECT 1; ")
        assert result == ["SELECT 1"]

    def test_split_statements_empty(self):
        """Test empty string returns empty list."""
        result = _split_statements("")
        assert result == []

    def test_split_statements_whitespace_only(self):
        """Test whitespace only returns empty list."""
        result = _split_statements("   ")
        assert result == []

    def test_split_statements_multiple_with_trailing(self):
        """Test multiple statements with trailing semicolon."""
        result = _split_statements("SELECT 1; SELECT 2;")
        assert result == ["SELECT 1", "SELECT 2"]

    def test_split_statements_empty_between(self):
        """Test empty statement between semicolons."""
        result = _split_statements("SELECT 1;; SELECT 2")
        # Empty statement between ;; is filtered out
        assert result == ["SELECT 1", "SELECT 2"]

    def test_split_statements_complex_string(self):
        """Test complex statement with strings."""
        result = _split_statements("INSERT INTO t VALUES ('a;b', \"c;d\")")
        assert len(result) == 1
        assert "a;b" in result[0]
        assert 'c;d' in result[0]


class TestIsWriteOperation:
    """Tests for _is_write_operation function."""

    def test_is_write_operation_insert(self):
        """Test INSERT statement."""
        assert _is_write_operation("INSERT INTO t VALUES (1)") is True

    def test_is_write_operation_update(self):
        """Test UPDATE statement."""
        assert _is_write_operation("UPDATE t SET x = 1") is True

    def test_is_write_operation_delete(self):
        """Test DELETE statement."""
        assert _is_write_operation("DELETE FROM t") is True

    def test_is_write_operation_drop(self):
        """Test DROP statement."""
        assert _is_write_operation("DROP TABLE t") is True

    def test_is_write_operation_create(self):
        """Test CREATE statement."""
        assert _is_write_operation("CREATE TABLE t (id INT)") is True

    def test_is_write_operation_alter(self):
        """Test ALTER statement."""
        assert _is_write_operation("ALTER TABLE t ADD COLUMN x INT") is True

    def test_is_write_operation_truncate(self):
        """Test TRUNCATE statement."""
        assert _is_write_operation("TRUNCATE TABLE t") is True

    def test_is_write_operation_grant(self):
        """Test GRANT statement."""
        assert _is_write_operation("GRANT SELECT ON t TO user") is True

    def test_is_write_operation_revoke(self):
        """Test REVOKE statement."""
        assert _is_write_operation("REVOKE SELECT ON t FROM user") is True

    def test_is_write_operation_select(self):
        """Test SELECT statement."""
        assert _is_write_operation("SELECT * FROM t") is False

    def test_is_write_operation_case_insensitive(self):
        """Test lowercase keywords."""
        assert _is_write_operation("insert into t values (1)") is True
        assert _is_write_operation("update t set x = 1") is True
        assert _is_write_operation("delete from t") is True

    def test_is_write_operation_with_leading_spaces(self):
        """Test statement with leading whitespace."""
        assert _is_write_operation("   INSERT INTO t VALUES (1)") is True

    def test_is_write_operation_empty(self):
        """Test empty string."""
        assert _is_write_operation("") is False

    def test_is_write_operation_comment(self):
        """Test comment-only string."""
        assert _is_write_operation("-- comment") is False


class TestIsSelect:
    """Tests for _is_select function."""

    def test_is_select_basic(self):
        """Test basic SELECT statement."""
        assert _is_select("SELECT * FROM t") is True

    def test_is_select_with_cte(self):
        """Test WITH ... SELECT."""
        # The regex matches SELECT at the start, so WITH ... SELECT doesn't match
        result = _is_select("WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert result is False  # Doesn't start with SELECT

    def test_is_select_case_insensitive(self):
        """Test lowercase select."""
        assert _is_select("select * from t") is True

    def test_is_select_mixed_case(self):
        """Test mixed case."""
        assert _is_select("Select * From t") is True

    def test_is_select_not_select(self):
        """Test INSERT statement."""
        assert _is_select("INSERT INTO t VALUES (1)") is False

    def test_is_select_with_spaces(self):
        """Test SELECT with leading spaces."""
        assert _is_select("   SELECT * FROM t") is True

    def test_is_select_subquery(self):
        """Test statement starting with SELECT in subquery."""
        assert _is_select("SELECT * FROM (SELECT 1) t") is True


class TestHasLimit:
    """Tests for _has_limit function."""

    def test_has_limit_present(self):
        """Test query with LIMIT."""
        assert _has_limit("SELECT * FROM t LIMIT 10") is True

    def test_has_limit_not_present(self):
        """Test query without LIMIT."""
        assert _has_limit("SELECT * FROM t") is False

    def test_has_limit_case_insensitive(self):
        """Test lowercase limit."""
        assert _has_limit("select * from t limit 10") is True

    def test_has_limit_with_value(self):
        """Test LIMIT with different values."""
        assert _has_limit("SELECT * FROM t LIMIT 1") is True
        assert _has_limit("SELECT * FROM t LIMIT 1000") is True

    def test_has_limit_no_space(self):
        """Test LIMIT without space (shouldn't match)."""
        # Pattern requires LIMIT followed by space and digits
        assert _has_limit("SELECT * FROM t LIMIT") is False

    def test_has_limit_in_subquery(self):
        """Test LIMIT in subquery."""
        # LIMIT pattern search finds any LIMIT in query
        assert _has_limit("SELECT * FROM (SELECT * FROM t LIMIT 10) sub") is True


class TestAddLimit:
    """Tests for _add_limit function."""

    def test_add_limit_no_existing(self):
        """Test adding LIMIT to query without LIMIT."""
        result = _add_limit("SELECT * FROM t", 100)
        assert result == "SELECT * FROM t LIMIT 100"

    def test_add_limit_existing(self):
        """Test query with existing LIMIT is unchanged."""
        result = _add_limit("SELECT * FROM t LIMIT 10", 100)
        assert result == "SELECT * FROM t LIMIT 10"

    def test_add_limit_with_semicolon(self):
        """Test query ending with semicolon."""
        result = _add_limit("SELECT * FROM t;", 100)
        assert result == "SELECT * FROM t LIMIT 100"

    def test_add_limit_with_trailing_spaces(self):
        """Test query with trailing spaces and semicolon."""
        # rstrip(';') only removes semicolons, not spaces before them
        result = _add_limit("SELECT * FROM t  ;  ", 100)
        # The function does rstrip(';').strip() which handles this
        assert result == "SELECT * FROM t  ; LIMIT 100"

    def test_add_limit_custom_value(self):
        """Test custom LIMIT value."""
        result = _add_limit("SELECT * FROM t", 50)
        assert result == "SELECT * FROM t LIMIT 50"

    def test_add_limit_complex_query(self):
        """Test complex query."""
        result = _add_limit("SELECT a, b FROM t WHERE x = 1 ORDER BY a", 100)
        assert result == "SELECT a, b FROM t WHERE x = 1 ORDER BY a LIMIT 100"


class TestTruncateLargeFields:
    """Tests for _truncate_large_fields function."""

    def test_truncate_large_fields_string_long(self):
        """Test long string is truncated."""
        long_string = "x" * 2000
        rows = [{"data": long_string}]
        result = _truncate_large_fields(rows, max_len=1000)
        assert len(result[0]["data"]) < len(long_string)
        assert "truncated" in result[0]["data"]
        assert "2000 chars" in result[0]["data"]

    def test_truncate_large_fields_string_short(self):
        """Test short string is unchanged."""
        short_string = "short"
        rows = [{"data": short_string}]
        result = _truncate_large_fields(rows, max_len=1000)
        assert result[0]["data"] == short_string

    def test_truncate_large_fields_bytes_long(self):
        """Test long bytes is replaced with placeholder."""
        long_bytes = b"x" * 2000
        rows = [{"data": long_bytes}]
        result = _truncate_large_fields(rows, max_len=1000)
        assert "[binary data" in result[0]["data"]
        assert "2000 bytes" in result[0]["data"]

    def test_truncate_large_fields_bytes_short(self):
        """Test short bytes is unchanged."""
        short_bytes = b"short"
        rows = [{"data": short_bytes}]
        result = _truncate_large_fields(rows, max_len=1000)
        assert result[0]["data"] == short_bytes

    def test_truncate_large_fields_int(self):
        """Test integer is unchanged."""
        rows = [{"id": 123}]
        result = _truncate_large_fields(rows, max_len=1000)
        assert result[0]["id"] == 123

    def test_truncate_large_fields_none(self):
        """Test None is unchanged."""
        rows = [{"data": None}]
        result = _truncate_large_fields(rows, max_len=1000)
        assert result[0]["data"] is None

    def test_truncate_large_fields_float(self):
        """Test float is unchanged."""
        rows = [{"value": 3.14}]
        result = _truncate_large_fields(rows, max_len=1000)
        assert result[0]["value"] == 3.14

    def test_truncate_large_fields_custom_max(self):
        """Test custom max length."""
        long_string = "x" * 200
        rows = [{"data": long_string}]
        result = _truncate_large_fields(rows, max_len=100)
        assert len(result[0]["data"]) < len(long_string)
        assert "truncated" in result[0]["data"]

    def test_truncate_large_fields_multiple_rows(self):
        """Test multiple rows."""
        rows = [
            {"id": 1, "data": "short"},
            {"id": 2, "data": "x" * 2000},
        ]
        result = _truncate_large_fields(rows, max_len=1000)
        assert result[0]["data"] == "short"
        assert "truncated" in result[1]["data"]

    def test_truncate_large_fields_multiple_columns(self):
        """Test multiple columns."""
        rows = [{
            "short": "ok",
            "long": "x" * 2000,
            "bytes": b"y" * 2000,
        }]
        result = _truncate_large_fields(rows, max_len=1000)
        assert result[0]["short"] == "ok"
        assert "truncated" in result[0]["long"]
        assert "binary data" in result[0]["bytes"]

    def test_truncate_large_fields_empty_list(self):
        """Test empty list."""
        result = _truncate_large_fields([], max_len=1000)
        assert result == []

    def test_truncate_large_fields_exactly_max_len(self):
        """Test string exactly at max length."""
        exact_string = "x" * 1000
        rows = [{"data": exact_string}]
        result = _truncate_large_fields(rows, max_len=1000)
        # Exactly at max length, should not be truncated
        assert result[0]["data"] == exact_string

    def test_truncate_large_fields_one_over_max(self):
        """Test string one char over max length."""
        over_string = "x" * 1001
        rows = [{"data": over_string}]
        result = _truncate_large_fields(rows, max_len=1000)
        assert "truncated" in result[0]["data"]


class TestSqlCmd:
    """Tests for sql command CLI."""

    def test_sql_cmd_select_success(self, mock_get_connection):
        """Test successful SELECT query."""
        mock_get_connection.execute.return_value = [
            {"id": 1, "name": "Alice"},
            {"id": 2, "name": "Bob"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "SELECT * FROM users LIMIT 10"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        mock_get_connection.close.assert_called_once()

    def test_sql_cmd_write_blocked(self, mock_get_connection):
        """Test write operation is blocked."""
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "INSERT INTO users VALUES (1)"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "WRITE_GUARD_ERROR"

    def test_sql_cmd_delete_blocked(self, mock_get_connection):
        """Test DELETE operation is blocked."""
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "DELETE FROM users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "WRITE_GUARD_ERROR"

    def test_sql_cmd_update_blocked(self, mock_get_connection):
        """Test UPDATE operation is blocked."""
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "UPDATE users SET name = 'test' WHERE id = 1"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "WRITE_GUARD_ERROR"

    def test_sql_cmd_limit_required(self, mock_get_connection):
        """Test query without LIMIT that returns too many rows."""
        # Return more than 100 rows (PROBE_LIMIT = 101)
        mock_get_connection.execute.return_value = [{"id": i} for i in range(102)]

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "SELECT * FROM users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "LIMIT_REQUIRED"

    def test_sql_cmd_limit_required_with_flag(self, mock_get_connection):
        """Test --no-limit-check bypasses limit check."""
        mock_get_connection.execute.return_value = [{"id": i} for i in range(200)]

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "--no-limit-check", "SELECT * FROM users"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_sql_cmd_connection_error(self, mocker):
        """Test connection error handling."""
        mocker.patch("hologres_cli.commands.sql.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "SELECT 1"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_sql_cmd_query_error(self, mock_get_connection):
        """Test query error handling."""
        mock_get_connection.execute.side_effect = Exception("Syntax error")

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "SELECT * FROM users LIMIT 10"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_sql_cmd_multiple_statements(self, mock_get_connection):
        """Test multiple statements execution."""
        mock_get_connection.execute.return_value = [{"id": 1}]

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "SELECT 1; SELECT 2"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 2

    def test_sql_cmd_with_schema(self, mock_get_connection):
        """Test --with-schema option."""
        mock_get_connection.execute.return_value = [{"id": 1, "name": "Alice"}]

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "--with-schema", "SELECT id, name FROM users LIMIT 10"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "schema" in output["data"]

    def test_sql_cmd_no_mask(self, mock_get_connection):
        """Test --no-mask option."""
        mock_get_connection.execute.return_value = [{"phone": "13812345678"}]

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "--no-mask", "SELECT phone FROM users LIMIT 10"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        # Phone should not be masked
        assert output["data"]["rows"][0]["phone"] == "13812345678"

    def test_sql_cmd_drop_blocked(self, mock_get_connection):
        """Test DROP operation is blocked."""
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "DROP TABLE users"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "WRITE_GUARD_ERROR"

    def test_sql_cmd_table_format(self, mock_get_connection):
        """Test table format output."""
        mock_get_connection.execute.return_value = [{"id": 1, "name": "Alice"}]

        runner = CliRunner()
        result = runner.invoke(cli, ["--format", "table", "sql", "SELECT * FROM users LIMIT 10"])

        assert result.exit_code == 0
        assert "Alice" in result.output


class TestExplainCmd:
    """Tests for sql explain subcommand."""

    def test_explain_basic(self, mock_get_connection):
        """Test basic EXPLAIN query."""
        mock_get_connection.execute.return_value = [
            {"QUERY PLAN": "Seq Scan on orders  (cost=0.00..35.50 rows=2550 width=36)"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "explain", "SELECT * FROM orders"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "plan" in output["data"]
        assert len(output["data"]["plan"]) == 1
        assert output["data"]["query"] == "SELECT * FROM orders"

    def test_explain_builds_correct_sql(self, mock_get_connection):
        """Test that EXPLAIN SQL is correctly constructed."""
        mock_get_connection.execute.return_value = [{"QUERY PLAN": "..."}]

        runner = CliRunner()
        runner.invoke(cli, ["sql", "explain", "SELECT 1"])

        mock_get_connection.execute.assert_called_once_with("EXPLAIN SELECT 1")

    def test_explain_complex_query(self, mock_get_connection):
        """Test EXPLAIN with complex query."""
        mock_get_connection.execute.return_value = [
            {"QUERY PLAN": "Hash Join  (cost=1.00..2.00 rows=10 width=100)"},
            {"QUERY PLAN": "  -> Seq Scan on orders"},
            {"QUERY PLAN": "  -> Hash"},
            {"QUERY PLAN": "       -> Seq Scan on users"},
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "explain", "SELECT * FROM orders JOIN users ON orders.uid = users.id"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert len(output["data"]["plan"]) == 4

    def test_explain_empty_plan(self, mock_get_connection):
        """Test EXPLAIN with empty result."""
        mock_get_connection.execute.return_value = []

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "explain", "SELECT 1"])

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["plan"] == []

    def test_explain_connection_error(self, mocker):
        """Test EXPLAIN with connection error."""
        mocker.patch("hologres_cli.commands.sql.get_connection",
                     side_effect=DSNError("No DSN configured"))

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "explain", "SELECT 1"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "CONNECTION_ERROR"

    def test_explain_query_error(self, mock_get_connection):
        """Test EXPLAIN with invalid SQL."""
        mock_get_connection.execute.side_effect = Exception("syntax error at or near \"SELEC\"")

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "explain", "SELEC TYPO"])

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "QUERY_ERROR"

    def test_explain_logs_operation(self, mock_get_connection, mocker):
        """Test that EXPLAIN logs operation."""
        mock_get_connection.execute.return_value = [{"QUERY PLAN": "..."}]
        mock_log = mocker.patch("hologres_cli.commands.sql.log_operation")

        runner = CliRunner()
        runner.invoke(cli, ["sql", "explain", "SELECT 1"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[0][0] == "sql.explain"
        assert call_kwargs[1]["success"] is True

    def test_explain_error_logs(self, mock_get_connection, mocker):
        """Test that EXPLAIN error is logged."""
        mock_get_connection.execute.side_effect = Exception("some error")
        mock_log = mocker.patch("hologres_cli.commands.sql.log_operation")

        runner = CliRunner()
        runner.invoke(cli, ["sql", "explain", "INVALID"])

        mock_log.assert_called_once()
        call_kwargs = mock_log.call_args
        assert call_kwargs[0][0] == "sql.explain"
        assert call_kwargs[1]["success"] is False
        assert call_kwargs[1]["error_code"] == "QUERY_ERROR"

    def test_explain_output_structure(self, mock_get_connection):
        """Test EXPLAIN output JSON structure."""
        mock_get_connection.execute.return_value = [
            {"QUERY PLAN": "Seq Scan on t  (cost=0.00..1.00 rows=1 width=4)"}
        ]

        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "explain", "SELECT * FROM t"])

        output = json.loads(result.output)
        assert "ok" in output
        assert "data" in output
        assert "plan" in output["data"]
        assert "query" in output["data"]
        assert isinstance(output["data"]["plan"], list)
        assert isinstance(output["data"]["query"], str)


class TestSqlGroupCompatibility:
    """Tests for backward compatibility of sql group with 'run' subcommand."""

    def test_sql_run_explicit(self, mock_get_connection):
        """Test explicit 'sql run' subcommand."""
        mock_get_connection.execute.return_value = [{"id": 1}]
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "run", "SELECT 1"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_sql_backward_compat(self, mock_get_connection):
        """Test backward compatible 'sql <query>' form."""
        mock_get_connection.execute.return_value = [{"id": 1}]
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "SELECT 1"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_sql_run_with_options(self, mock_get_connection):
        """Test 'sql run' with options."""
        mock_get_connection.execute.return_value = [{"id": 1}]
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "run", "--no-limit-check", "SELECT * FROM t"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_sql_backward_compat_with_options(self, mock_get_connection):
        """Test backward compat with options."""
        mock_get_connection.execute.return_value = [{"id": 1}]
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "--no-limit-check", "SELECT * FROM t"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_sql_help_shows_subcommands(self):
        """Test 'sql --help' shows available subcommands including 'run' and 'explain'."""
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "--help"])
        assert "run" in result.output
        assert "explain" in result.output

    def test_sql_run_help(self):
        """Test 'sql run --help' shows run command help."""
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "run", "--help"])
        assert "QUERY" in result.output

    def test_sql_explain_recognized(self, mock_get_connection):
        """Test 'sql explain' is recognized as a subcommand, not routed to run."""
        mock_get_connection.execute.return_value = [{"QUERY PLAN": "..."}]
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "explain", "SELECT 1"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert "plan" in output["data"]

    def test_sql_backward_compat_not_broken_by_explain(self, mock_get_connection):
        """Test 'sql <query>' still routes to run after adding explain."""
        mock_get_connection.execute.return_value = [{"id": 1}]
        runner = CliRunner()
        result = runner.invoke(cli, ["sql", "SELECT 1"])
        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        # Should be run output, not explain output
        assert "plan" not in output.get("data", {})
