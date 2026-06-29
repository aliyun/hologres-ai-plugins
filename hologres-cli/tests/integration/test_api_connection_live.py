"""Integration tests for API connection lifecycle with real Hologram OpenAPI."""

from __future__ import annotations

import pytest

from hologres_cli.api_connection import ApiConnectionError, HologresApiConnection


@pytest.mark.integration
class TestApiConnectionLifecycle:
    """Tests for real API connection creation, properties, and teardown."""

    def test_create_api_connection(self, api_conn: HologresApiConnection):
        """Verify we can create a connection and execute SQL."""
        result = api_conn.execute("SELECT 1 AS value")
        assert len(result) == 1

    def test_database_property(self, api_conn: HologresApiConnection, api_test_profile: str):
        """conn.database returns the configured database name."""
        from hologres_cli.config_store import get_profile
        prof = get_profile(api_test_profile)
        assert api_conn.database == prof["database"]

    def test_masked_dsn(self, api_conn: HologresApiConnection):
        """masked_dsn hides credentials."""
        masked = api_conn.masked_dsn
        assert "hologres+api://" in masked
        assert "***" in masked
        # AK should not appear in plain text after the :
        # Format: hologres+api://AK_PREFIX...:***@host:port/db
        auth_part = masked.split("://")[1].split("@")[0]
        assert ":***" in auth_part

    def test_autocommit_always_true(self, api_conn: HologresApiConnection):
        """API mode always has autocommit=True."""
        assert api_conn.autocommit is True

    def test_read_only_property(self, api_conn_readonly: HologresApiConnection):
        """read_only connection reports True."""
        assert api_conn_readonly.read_only is True

    def test_context_manager(self, api_test_profile: str):
        """Connection auto-closes on context manager exit."""
        from hologres_cli.config_store import get_profile
        prof = dict(get_profile(api_test_profile))
        prof["connection_mode"] = "api"
        with HologresApiConnection(prof, read_only=False) as conn:
            result = conn.execute("SELECT 1 AS value")
            assert len(result) == 1
        # After exiting context, connection should be closed
        with pytest.raises(ApiConnectionError, match="closed"):
            conn.execute("SELECT 1")

    def test_close_then_execute_raises(self, api_conn: HologresApiConnection):
        """Executing SQL after close raises ApiConnectionError."""
        api_conn.close()
        with pytest.raises(ApiConnectionError, match="closed"):
            api_conn.execute("SELECT 1")

    def test_double_close_no_error(self, api_test_profile: str):
        """Closing twice should not raise."""
        from hologres_cli.config_store import get_profile
        prof = dict(get_profile(api_test_profile))
        prof["connection_mode"] = "api"
        conn = HologresApiConnection(prof, read_only=False)
        conn.close()
        conn.close()  # Should not raise

    def test_cursor_returns_api_cursor(self, api_conn: HologresApiConnection):
        """conn.cursor() returns an _ApiCursor that can execute SQL."""
        from hologres_cli.api_connection import _ApiCursor
        cur = api_conn.cursor()
        assert isinstance(cur, _ApiCursor)
        cur.execute("SELECT 42 AS answer")
        rows = cur.fetchall()
        assert len(rows) == 1
