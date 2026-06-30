"""Integration tests for SQL execution via Hologram OpenAPI (ExecuteStatement)."""

from __future__ import annotations

import pytest

from hologres_cli.api_connection import ApiConnectionError, HologresApiConnection


@pytest.mark.integration
class TestApiSqlSelectLive:
    """Real SELECT queries through the ExecuteStatement API."""

    def test_select_literal(self, api_conn: HologresApiConnection):
        """SELECT literal value."""
        result = api_conn.execute("SELECT 1 AS value")
        assert len(result) == 1
        assert str(result[0]["value"]) == "1"

    def test_select_with_params(self, api_conn: HologresApiConnection):
        """Parameterized SELECT with %s substitution."""
        result = api_conn.execute("SELECT %s AS a, %s AS b", (42, "hello"))
        assert len(result) == 1
        assert str(result[0]["a"]) == "42"
        assert result[0]["b"] == "hello"

    def test_select_current_database(self, api_conn: HologresApiConnection, api_test_profile: str):
        """current_database() returns the correct database."""
        from hologres_cli.config_store import get_profile
        prof = get_profile(api_test_profile)
        result = api_conn.execute("SELECT current_database() AS db")
        assert result[0]["db"] == prof["database"]

    def test_select_version(self, api_conn: HologresApiConnection):
        """version() returns Hologres version string."""
        result = api_conn.execute("SELECT version() AS ver")
        assert len(result) == 1
        ver = result[0]["ver"]
        assert "Hologres" in ver or "PostgreSQL" in ver

    def test_select_current_user(self, api_conn: HologresApiConnection):
        """current_user returns a non-empty string."""
        result = api_conn.execute("SELECT current_user AS usr")
        assert len(result) == 1
        assert result[0]["usr"]

    def test_multi_column_result(self, api_conn: HologresApiConnection):
        """Multi-column SELECT returns proper dict structure."""
        result = api_conn.execute(
            "SELECT 1 AS id, 'test' AS name, true AS active"
        )
        assert len(result) == 1
        row = result[0]
        assert "id" in row
        assert "name" in row
        assert "active" in row
        assert row["name"] == "test"

    def test_select_from_table(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """SELECT from a real table with data."""
        result = api_conn.execute(f"SELECT * FROM {api_test_table_with_data} ORDER BY id")
        assert len(result) == 3
        assert result[0]["name"] == "Alice"

    def test_select_with_where(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """SELECT with WHERE clause filters rows."""
        result = api_conn.execute(
            f"SELECT * FROM {api_test_table_with_data} WHERE id = %s", (1,)
        )
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_select_with_limit(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """SELECT with LIMIT returns limited rows."""
        result = api_conn.execute(
            f"SELECT * FROM {api_test_table_with_data} LIMIT 2"
        )
        assert len(result) == 2

    def test_select_count(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """COUNT aggregate returns correct count."""
        result = api_conn.execute(
            f"SELECT COUNT(*) AS cnt FROM {api_test_table_with_data}"
        )
        assert str(result[0]["cnt"]) == "3"

    def test_select_order_by(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """ORDER BY sorts results correctly."""
        result = api_conn.execute(
            f"SELECT * FROM {api_test_table_with_data} ORDER BY id DESC LIMIT 2"
        )
        assert len(result) == 2
        assert str(result[0]["id"]) == "3"


@pytest.mark.integration
class TestApiSqlWriteLive:
    """Real DDL and DML operations through the ExecuteStatement API."""

    def test_create_insert_select_drop(self, api_conn: HologresApiConnection, unique_table_name: str):
        """Full DDL+DML lifecycle: CREATE → INSERT → SELECT → DROP."""
        t = unique_table_name
        try:
            api_conn.execute(f"CREATE TABLE {t} (id INT PRIMARY KEY, val TEXT)")
            api_conn.execute(f"INSERT INTO {t} (id, val) VALUES (1, 'hello')")
            result = api_conn.execute(f"SELECT * FROM {t}")
            assert len(result) == 1
            assert result[0]["val"] == "hello"
        finally:
            api_conn.execute(f"DROP TABLE IF EXISTS {t}")

    def test_execute_many(self, api_test_table: str, api_conn: HologresApiConnection):
        """execute_many inserts multiple rows."""
        rows = [(10, "User10"), (11, "User11"), (12, "User12")]
        api_conn.execute_many(
            f"INSERT INTO {api_test_table} (id, name) VALUES (%s, %s)",
            rows
        )
        result = api_conn.execute(
            f"SELECT COUNT(*) AS cnt FROM {api_test_table}"
        )
        assert str(result[0]["cnt"]) == "3"

    def test_update_rows(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """UPDATE with WHERE clause modifies rows."""
        api_conn.execute(
            f"UPDATE {api_test_table_with_data} SET name = 'Updated' WHERE id = 1"
        )
        result = api_conn.execute(
            f"SELECT name FROM {api_test_table_with_data} WHERE id = 1"
        )
        assert result[0]["name"] == "Updated"

    def test_delete_rows(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """DELETE with WHERE clause removes rows."""
        api_conn.execute(
            f"DELETE FROM {api_test_table_with_data} WHERE id = 3"
        )
        result = api_conn.execute(
            f"SELECT COUNT(*) AS cnt FROM {api_test_table_with_data}"
        )
        assert str(result[0]["cnt"]) == "2"

    def test_cursor_fetchall(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """cursor.fetchall() returns all rows."""
        cur = api_conn.cursor()
        cur.execute(f"SELECT * FROM {api_test_table_with_data} ORDER BY id")
        rows = cur.fetchall()
        assert len(rows) == 3

    def test_cursor_fetchone(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """cursor.fetchone() returns first row."""
        cur = api_conn.cursor()
        cur.execute(f"SELECT * FROM {api_test_table_with_data} ORDER BY id LIMIT 1")
        row = cur.fetchone()
        assert row is not None
        assert row["name"] == "Alice"

    def test_cursor_description(self, api_test_table_with_data: str, api_conn: HologresApiConnection):
        """cursor.description contains column names."""
        cur = api_conn.cursor()
        cur.execute(f"SELECT id, name FROM {api_test_table_with_data} LIMIT 1")
        assert cur.description is not None
        col_names = [d[0] for d in cur.description]
        assert "id" in col_names
        assert "name" in col_names

    def test_cursor_context_manager(self, api_conn: HologresApiConnection):
        """Cursor works as context manager."""
        with api_conn.cursor() as cur:
            cur.execute("SELECT 1 AS value")
            rows = cur.fetchall()
            assert len(rows) == 1


@pytest.mark.integration
class TestApiSqlErrorsLive:
    """Error handling with real API responses."""

    def test_invalid_sql_raises(self, api_conn: HologresApiConnection):
        """Invalid SQL syntax raises ApiConnectionError."""
        with pytest.raises(ApiConnectionError):
            api_conn.execute("SELECTTTYPO 1")

    def test_nonexistent_table_raises(self, api_conn: HologresApiConnection):
        """Querying a non-existent table raises ApiConnectionError."""
        with pytest.raises(ApiConnectionError):
            api_conn.execute("SELECT * FROM nonexistent_table_xyz_12345")

    def test_read_only_blocks_writes(self, api_conn_readonly: HologresApiConnection, unique_table_name: str):
        """read_only=True prevents DDL/DML at the server level."""
        with pytest.raises(ApiConnectionError):
            api_conn_readonly.execute(
                f"CREATE TABLE {unique_table_name} (id INT)"
            )


@pytest.mark.integration
class TestApiGUCBehavior:
    """Verify GUC settings take effect through real SQL execution."""

    def test_read_only_guc_blocks_ddl(self, api_conn_readonly: HologresApiConnection, unique_table_name: str):
        """read_only connection prepends SET default_transaction_read_only=ON, blocking DDL."""
        with pytest.raises(ApiConnectionError):
            api_conn_readonly.execute(
                f"CREATE TABLE {unique_table_name} (id INT)"
            )
