"""Integration tests for connection module with real Hologres database."""

from __future__ import annotations

import pytest

from hologres_cli.connection import DSNError, HologresConnection, get_connection


@pytest.mark.integration
class TestRealConnection:
    """Tests for real database connections."""

    def test_real_connection(self, integration_conn: HologresConnection):
        """Test establishing a real connection and querying version."""
        result = integration_conn.execute("SELECT version()")
        assert len(result) == 1
        assert "version" in result[0]
        # Hologres should return something like "PostgreSQL 11.x (Hologres)"
        assert "PostgreSQL" in result[0]["version"] or "Hologres" in result[0]["version"]

    def test_connection_execute_select(self, integration_conn: HologresConnection):
        """Test executing a simple SELECT query."""
        result = integration_conn.execute("SELECT 1 AS value")
        assert result == [{"value": 1}]

    def test_connection_execute_with_params(self, integration_conn: HologresConnection):
        """Test parameterized query execution."""
        result = integration_conn.execute(
            "SELECT %s AS a, %s AS b",
            (1, "test")
        )
        assert result == [{"a": 1, "b": "test"}]

    def test_connection_current_database(self, integration_conn: HologresConnection):
        """Test getting current database name."""
        result = integration_conn.execute("SELECT current_database()")
        assert len(result) == 1
        assert "current_database" in result[0]

    def test_connection_current_user(self, integration_conn: HologresConnection):
        """Test getting current user."""
        result = integration_conn.execute("SELECT current_user")
        assert len(result) == 1
        assert "current_user" in result[0]

    def test_connection_close_and_reconnect(self, integration_dsn: str):
        """Test closing and reopening connection."""
        conn = HologresConnection(integration_dsn)

        # First query
        result = conn.execute("SELECT 1")
        assert result == [{"?column?": 1}]

        # Close
        conn.close()
        assert conn._conn is None

        # Reconnect via property access
        result = conn.execute("SELECT 2")
        assert result == [{"?column?": 2}]

        conn.close()

    def test_connection_context_manager(self, integration_dsn: str):
        """Test using connection as context manager."""
        with HologresConnection(integration_dsn) as conn:
            result = conn.execute("SELECT 1 AS value")
            assert result == [{"value": 1}]
        # Connection should be closed after exiting context

    def test_connection_masked_dsn(self, integration_dsn: str):
        """Test that masked_dsn hides password."""
        conn = HologresConnection(integration_dsn)
        masked = conn.masked_dsn

        # If DSN has password, it should be masked
        if ":" in integration_dsn.split("@")[0]:
            assert "***" in masked
            # Original password should not appear
            # Extract password from DSN if present
            if "@" in integration_dsn:
                auth_part = integration_dsn.split("://")[1].split("@")[0]
                if ":" in auth_part and not auth_part.startswith(":"):
                    password = auth_part.split(":")[1]
                    if password:
                        assert password not in masked

        conn.close()


@pytest.mark.integration
class TestConnectionErrors:
    """Tests for connection error handling."""

    def test_invalid_host(self):
        """Test connection to invalid host raises error."""
        # Use a clearly invalid DSN
        invalid_dsn = "hologres://user:pass@nonexistent.invalid.host.12345:80/testdb"

        with pytest.raises(Exception):  # Could be ConnectionError or psycopg error
            conn = HologresConnection(invalid_dsn)
            conn.execute("SELECT 1")

    def test_parse_dsn_invalid_scheme(self):
        """Test DSN parsing with invalid scheme."""
        from hologres_cli.connection import parse_dsn

        with pytest.raises(DSNError):
            parse_dsn("mysql://user:pass@host/db")

    def test_parse_dsn_missing_database(self):
        """Test DSN parsing without database."""
        from hologres_cli.connection import parse_dsn

        with pytest.raises(DSNError):
            parse_dsn("hologres://user:pass@host")


@pytest.mark.integration
class TestGetConnection:
    """Tests for get_connection function."""

    def test_get_connection_with_dsn(self, integration_dsn: str):
        """Test get_connection with explicit DSN."""
        conn = get_connection(integration_dsn)
        assert isinstance(conn, HologresConnection)

        result = conn.execute("SELECT 1")
        assert len(result) == 1

        conn.close()

    def test_get_connection_autocommit_true(self, integration_dsn: str):
        """Test get_connection with autocommit=True (default)."""
        conn = get_connection(integration_dsn, autocommit=True)
        assert conn.autocommit is True

        # Should auto-commit
        conn.execute("SELECT 1")
        conn.close()

    def test_get_connection_autocommit_false(self, integration_dsn: str):
        """Test get_connection with autocommit=False."""
        conn = get_connection(integration_dsn, autocommit=False)
        assert conn.autocommit is False
        conn.close()
