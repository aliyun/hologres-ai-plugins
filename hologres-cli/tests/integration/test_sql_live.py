"""Integration tests for SQL command with real Hologres database."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from hologres_cli.main import cli


@pytest.mark.integration
class TestSqlSelectLive:
    """Integration tests for SELECT queries."""

    def test_select_query(self, integration_conn):
        """Test basic SELECT query."""
        result = integration_conn.execute("SELECT 1 AS id, 'test' AS name")
        assert result == [{"id": 1, "name": "test"}]

    def test_select_with_limit(self, test_table_with_data, integration_conn):
        """Test SELECT with LIMIT clause."""
        result = integration_conn.execute(f"SELECT * FROM {test_table_with_data} LIMIT 2")
        assert len(result) == 2

    def test_select_count(self, test_table_with_data, integration_conn):
        """Test SELECT COUNT query."""
        result = integration_conn.execute(f"SELECT COUNT(*) AS cnt FROM {test_table_with_data}")
        assert result[0]["cnt"] == 3

    def test_select_with_where(self, test_table_with_data, integration_conn):
        """Test SELECT with WHERE clause."""
        result = integration_conn.execute(
            f"SELECT * FROM {test_table_with_data} WHERE id = %s",
            (1,)
        )
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_select_order_by(self, test_table_with_data, integration_conn):
        """Test SELECT with ORDER BY."""
        result = integration_conn.execute(
            f"SELECT * FROM {test_table_with_data} ORDER BY id DESC LIMIT 2"
        )
        assert len(result) == 2
        assert result[0]["id"] == 3


@pytest.mark.integration
class TestSqlInsertLive:
    """Integration tests for INSERT operations."""

    def test_insert_and_select(self, test_table, integration_conn):
        """Test inserting and selecting data."""
        # Insert
        integration_conn.execute(
            f"INSERT INTO {test_table} (id, name, phone, email) VALUES (%s, %s, %s, %s)",
            (100, "Test User", "13900000000", "test@test.com")
        )

        # Select
        result = integration_conn.execute(f"SELECT * FROM {test_table} WHERE id = 100")
        assert len(result) == 1
        assert result[0]["name"] == "Test User"

    def test_insert_multiple_rows(self, test_table, integration_conn):
        """Test inserting multiple rows."""
        rows = [(10, "User10"), (11, "User11"), (12, "User12")]
        integration_conn.execute_many(
            f"INSERT INTO {test_table} (id, name) VALUES (%s, %s)",
            rows
        )

        result = integration_conn.execute(f"SELECT COUNT(*) AS cnt FROM {test_table}")
        assert result[0]["cnt"] == 3


@pytest.mark.integration
class TestSqlUpdateLive:
    """Integration tests for UPDATE operations."""

    def test_update_with_where(self, test_table_with_data, integration_conn):
        """Test UPDATE with WHERE clause."""
        integration_conn.execute(
            f"UPDATE {test_table_with_data} SET name = %s WHERE id = %s",
            ("Alice Updated", 1)
        )

        result = integration_conn.execute(
            f"SELECT name FROM {test_table_with_data} WHERE id = 1"
        )
        assert result[0]["name"] == "Alice Updated"

    def test_update_multiple_columns(self, test_table_with_data, integration_conn):
        """Test updating multiple columns."""
        integration_conn.execute(
            f"UPDATE {test_table_with_data} SET name = %s, phone = %s WHERE id = %s",
            ("Bob Updated", "13999999999", 2)
        )

        result = integration_conn.execute(
            f"SELECT name, phone FROM {test_table_with_data} WHERE id = 2"
        )
        assert result[0]["name"] == "Bob Updated"
        assert result[0]["phone"] == "13999999999"


@pytest.mark.integration
class TestSqlDeleteLive:
    """Integration tests for DELETE operations."""

    def test_delete_with_where(self, test_table_with_data, integration_conn):
        """Test DELETE with WHERE clause."""
        # Get initial count
        initial = integration_conn.execute(f"SELECT COUNT(*) AS cnt FROM {test_table_with_data}")[0]["cnt"]

        # Delete one row
        integration_conn.execute(f"DELETE FROM {test_table_with_data} WHERE id = 3")

        # Check count decreased
        result = integration_conn.execute(f"SELECT COUNT(*) AS cnt FROM {test_table_with_data}")
        assert result[0]["cnt"] == initial - 1


@pytest.mark.integration
class TestSqlTransactionLive:
    """Integration tests for transaction handling."""

    @pytest.mark.xfail(reason="Hologres does not support transaction rollback for DML")
    def test_transaction_rollback(self, test_table, integration_conn_no_autocommit):
        """Test that transaction rollback works."""
        conn = integration_conn_no_autocommit

        # Insert data
        conn.execute(f"INSERT INTO {test_table} (id, name) VALUES (500, 'To Rollback')")

        # Verify data is visible in same transaction
        result = conn.execute(f"SELECT * FROM {test_table} WHERE id = 500")
        assert len(result) == 1

        # Rollback
        conn.conn.rollback()

        # Data should not exist after rollback
        result = conn.execute(f"SELECT * FROM {test_table} WHERE id = 500")
        assert len(result) == 0

    def test_transaction_commit(self, test_table, integration_conn_no_autocommit):
        """Test that transaction commit persists data."""
        conn = integration_conn_no_autocommit

        # Insert data
        conn.execute(f"INSERT INTO {test_table} (id, name) VALUES (600, 'To Commit')")

        # Commit
        conn.conn.commit()

        # Data should persist
        result = conn.execute(f"SELECT * FROM {test_table} WHERE id = 600")
        assert len(result) == 1


@pytest.mark.integration
class TestSqlCliLive:
    """Integration tests for SQL CLI commands."""

    def test_cli_select(self, test_table_with_data, integration_dsn, tmp_path):
        """Test SQL CLI with SELECT query."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql", f"SELECT * FROM {test_table_with_data} LIMIT 2"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 2

    def test_cli_insert(self, test_table, integration_dsn):
        """Test SQL CLI with INSERT."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql", "--write",
             f"INSERT INTO {test_table} (id, name) VALUES (700, 'CLI User')"]
        )

        assert result.exit_code == 0
        output = json.loads(result.output)
        assert output["ok"] is True

    def test_cli_select_table_format(self, test_table_with_data, integration_dsn):
        """Test SQL CLI with table format output."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "--format", "table",
             "sql", f"SELECT id, name FROM {test_table_with_data} LIMIT 2"]
        )

        assert result.exit_code == 0
        # Table format should contain column headers
        assert "id" in result.output or "name" in result.output


@pytest.mark.integration
class TestSensitiveDataMaskingLive:
    """Integration tests for sensitive data masking with real data."""

    def test_masking_phone(self, test_table, integration_conn):
        """Test that phone numbers are masked in results."""
        from hologres_cli.masking import mask_rows

        integration_conn.execute(
            f"INSERT INTO {test_table} (id, phone) VALUES (1, '13812345678')"
        )
        result = integration_conn.execute(f"SELECT phone FROM {test_table} WHERE id = 1")

        masked = mask_rows(result)
        assert masked[0]["phone"] == "138****5678"

    def test_masking_email(self, test_table, integration_conn):
        """Test that emails are masked in results."""
        from hologres_cli.masking import mask_rows

        integration_conn.execute(
            f"INSERT INTO {test_table} (id, email) VALUES (2, 'test@example.com')"
        )
        result = integration_conn.execute(f"SELECT email FROM {test_table} WHERE id = 2")

        masked = mask_rows(result)
        assert masked[0]["email"] == "t***@example.com"


@pytest.mark.integration
class TestSqlSafetyLive:
    """Integration tests for SQL safety guardrails."""

    def test_cli_write_guard_error(self, test_table, integration_dsn):
        """Test INSERT without --write flag is blocked."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql",
             f"INSERT INTO {test_table} (id, name) VALUES (999, 'Blocked')"]
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "WRITE_GUARD_ERROR"

    def test_cli_dangerous_delete_blocked(self, test_table_with_data, integration_dsn):
        """Test DELETE without WHERE is blocked even with --write."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql", "--write",
             f"DELETE FROM {test_table_with_data}"]
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "DANGEROUS_WRITE_BLOCKED"

    def test_cli_dangerous_update_blocked(self, test_table_with_data, integration_dsn):
        """Test UPDATE without WHERE is blocked even with --write."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql", "--write",
             f"UPDATE {test_table_with_data} SET name = 'X'"]
        )

        output = json.loads(result.output)
        assert output["ok"] is False
        assert output["error"]["code"] == "DANGEROUS_WRITE_BLOCKED"

    def test_cli_no_mask_option(self, test_table_with_data, integration_dsn):
        """Test --no-mask disables sensitive field masking."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql", "--no-mask",
             f"SELECT phone FROM {test_table_with_data} WHERE id = 1"]
        )

        output = json.loads(result.output)
        assert output["ok"] is True
        # Without masking, phone should be the raw value
        assert output["data"]["rows"][0]["phone"] == "13812345678"

    def test_cli_multi_statement(self, integration_dsn):
        """Test executing multiple statements separated by semicolons."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql",
             "SELECT 1 AS a; SELECT 2 AS b"]
        )

        output = json.loads(result.output)
        assert output["ok"] is True
        assert output["data"]["count"] == 2
        assert len(output["data"]["statements"]) == 2

    def test_cli_with_schema_option(self, integration_dsn):
        """Test --with-schema includes column type info."""
        runner = CliRunner()
        result = runner.invoke(
            cli,
            ["--dsn", integration_dsn, "sql", "--with-schema",
             "SELECT 1 AS id, 'test' AS name"]
        )

        output = json.loads(result.output)
        assert output["ok"] is True
        assert "schema" in output["data"]
        schema_names = [s["name"] for s in output["data"]["schema"]]
        assert "id" in schema_names
        assert "name" in schema_names
