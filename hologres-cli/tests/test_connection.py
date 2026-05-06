"""Tests for connection module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hologres_cli.connection import (
    DSNError,
    HologresConnection,
    get_connection,
    mask_dsn_password,
    parse_dsn,
    resolve_dsn,
)


class TestParseDsn:
    """Tests for parse_dsn function."""

    def test_parse_dsn_full(self):
        """Test full DSN with all components."""
        result = parse_dsn("hologres://user:pass@host:5432/db")
        assert result["host"] == "host"
        assert result["port"] == 5432
        assert result["dbname"] == "db"
        assert result["user"] == "user"
        assert result["password"] == "pass"

    def test_parse_dsn_no_password(self):
        """Test DSN without password."""
        result = parse_dsn("hologres://user@host:80/db")
        assert result["user"] == "user"
        assert "password" not in result

    def test_parse_dsn_no_user(self):
        """Test DSN without user."""
        result = parse_dsn("hologres://host:80/db")
        assert "user" not in result
        assert "password" not in result

    def test_parse_dsn_default_port(self):
        """Test DSN without port uses default 80."""
        result = parse_dsn("hologres://user:pass@host/db")
        assert result["port"] == 80

    def test_parse_dsn_postgresql_scheme(self):
        """Test DSN with postgresql:// scheme."""
        result = parse_dsn("postgresql://user:pass@host:5432/db")
        assert result["host"] == "host"
        assert result["user"] == "user"
        assert result["password"] == "pass"

    def test_parse_dsn_postgres_scheme(self):
        """Test DSN with postgres:// scheme."""
        result = parse_dsn("postgres://user:pass@host/db")
        assert result["host"] == "host"

    def test_parse_dsn_invalid_scheme(self):
        """Test DSN with invalid scheme raises DSNError."""
        with pytest.raises(DSNError) as exc_info:
            parse_dsn("mysql://user:pass@host/db")
        assert "Invalid DSN scheme" in str(exc_info.value)

    def test_parse_dsn_no_hostname(self):
        """Test DSN without hostname raises DSNError."""
        with pytest.raises(DSNError) as exc_info:
            parse_dsn("hologres:///db")
        assert "must include a hostname" in str(exc_info.value)

    def test_parse_dsn_no_database(self):
        """Test DSN without database raises DSNError."""
        with pytest.raises(DSNError) as exc_info:
            parse_dsn("hologres://user:pass@host")
        assert "must include a database" in str(exc_info.value)

    def test_parse_dsn_with_query_params(self):
        """Test DSN with query parameters."""
        result = parse_dsn("hologres://user:pass@host/db?connect_timeout=30")
        assert result["connect_timeout"] == "30"

    def test_parse_dsn_with_keepalives_override(self):
        """Test DSN with keepalive params override defaults."""
        result = parse_dsn("hologres://user:pass@host/db?keepalives_idle=60")
        assert result["keepalives_idle"] == 60

    def test_parse_dsn_invalid_keepalive_value(self):
        """Test invalid integer for keepalive raises DSNError."""
        with pytest.raises(DSNError) as exc_info:
            parse_dsn("hologres://user:pass@host/db?keepalives_idle=abc")
        assert "Invalid integer" in str(exc_info.value)

    def test_parse_dsn_url_encoded_user(self):
        """Test URL-encoded username is decoded."""
        result = parse_dsn("hologres://user%40domain:pass@host/db")
        assert result["user"] == "user@domain"

    def test_parse_dsn_url_encoded_password(self):
        """Test URL-encoded password is decoded."""
        result = parse_dsn("hologres://user:p%40ss@host/db")
        assert result["password"] == "p@ss"

    def test_parse_dsn_default_keepalives(self):
        """Test default keepalive values are set."""
        result = parse_dsn("hologres://user:pass@host/db")
        assert result["keepalives"] == 1
        assert result["keepalives_idle"] == 130
        assert result["keepalives_interval"] == 10
        assert result["keepalives_count"] == 15

    def test_parse_dsn_options_param(self):
        """Test DSN with options parameter."""
        result = parse_dsn("hologres://user:pass@host/db?options=-c%20search_path=public")
        assert result["options"] == "-c search_path=public"

    def test_parse_dsn_default_application_name(self):
        """Test default application_name is hologres-cli."""
        result = parse_dsn("hologres://user:pass@host:80/db")
        assert result["application_name"] == "hologres-cli"

    def test_parse_dsn_application_name_from_dsn(self):
        """Test DSN with application_name is prefixed with hologres-cli/."""
        result = parse_dsn("hologres://user:pass@host:80/db?application_name=my-app")
        assert result["application_name"] == "hologres-cli/my-app"

    def test_parse_dsn_empty_application_name(self):
        """Test DSN with empty application_name falls back to default."""
        result = parse_dsn("hologres://user:pass@host:80/db?application_name=")
        assert result["application_name"] == "hologres-cli"

    def test_parse_dsn_application_name_postgresql_scheme(self):
        """Test application_name with postgresql:// scheme."""
        result = parse_dsn("postgresql://user:pass@host:5432/db")
        assert result["application_name"] == "hologres-cli"

    def test_parse_dsn_application_name_with_other_params(self):
        """Test application_name coexists with other query params."""
        result = parse_dsn("hologres://user:pass@host:80/db?connect_timeout=30&application_name=custom")
        assert result["application_name"] == "hologres-cli/custom"
        assert result["connect_timeout"] == "30"


class TestMaskDsnPassword:
    """Tests for mask_dsn_password function."""

    def test_mask_dsn_password_with_password(self):
        """Test DSN with password is masked."""
        result = mask_dsn_password("hologres://user:secretpass@host/db")
        assert "secretpass" not in result
        assert "***" in result
        assert result == "hologres://user:***@host/db"

    def test_mask_dsn_password_without_password(self):
        """Test DSN without password is unchanged."""
        result = mask_dsn_password("hologres://user@host/db")
        assert result == "hologres://user@host/db"

    def test_mask_dsn_password_special_chars(self):
        """Test password with special characters is masked."""
        result = mask_dsn_password("hologres://user:p@ss!word@host/db")
        assert "p@ss!word" not in result
        assert "***" in result

    def test_mask_dsn_password_complex(self):
        """Test complex password is masked."""
        result = mask_dsn_password("hologres://admin:P@$$w0rd!@example.com:80/mydb")
        assert "***" in result
        assert "example.com" in result
        assert "mydb" in result


class TestResolveDsn:
    """Tests for resolve_dsn function."""

    def test_resolve_dsn_named_profile(self, mock_config):
        """Test resolving DSN from named profile."""
        dsn = resolve_dsn("default")
        assert dsn.startswith("hologres://")
        assert "testdb" in dsn

    def test_resolve_dsn_current_profile(self, mock_config):
        """Test resolving DSN from current profile."""
        dsn = resolve_dsn()
        assert dsn.startswith("hologres://")

    def test_resolve_dsn_no_profile(self, mock_home):
        """Test resolving DSN with no profile configured."""
        with pytest.raises(DSNError):
            resolve_dsn()

    def test_resolve_dsn_nonexistent_profile(self, mock_config):
        """Test resolving DSN with non-existent profile."""
        with pytest.raises(DSNError, match="not found"):
            resolve_dsn("nonexistent")


class TestHologresConnection:
    """Tests for HologresConnection class."""

    def test_connection_init(self):
        """Test connection initialization."""
        conn = HologresConnection("hologres://user:pass@host/db")
        assert conn.raw_dsn == "hologres://user:pass@host/db"
        assert conn.autocommit is True
        assert conn.read_only is True
        assert conn._conn is None

    def test_connection_init_autocommit_false(self):
        """Test connection with autocommit=False."""
        conn = HologresConnection("hologres://user:pass@host/db", autocommit=False)
        assert conn.autocommit is False

    def test_connection_init_read_only_false(self):
        """Test connection with read_only=False."""
        conn = HologresConnection("hologres://user:pass@host/db", read_only=False)
        assert conn.read_only is False

    def test_connection_masked_dsn(self):
        """Test masked_dsn property."""
        conn = HologresConnection("hologres://user:secretpass@host/db")
        assert conn.masked_dsn == "hologres://user:***@host/db"

    def test_connection_lazy_connection(self, mock_psycopg):
        """Test lazy connection creation."""
        conn = HologresConnection("hologres://user:pass@host:80/db")
        assert conn._conn is None
        _ = conn.conn
        assert conn._conn is not None
        mock_psycopg["connect"].assert_called_once()

    def test_connection_read_only_default(self, mock_psycopg):
        """Test default connection sets read-only mode and default GUCs."""
        conn = HologresConnection("hologres://user:pass@host:80/db")
        _ = conn.conn
        calls = mock_psycopg["conn"].execute.call_args_list
        assert any("hg_experimental_enable_adaptive_execution" in str(c) for c in calls)
        assert any("hg_computing_resource" in str(c) for c in calls)
        assert any("default_transaction_read_only" in str(c) for c in calls)

    def test_connection_read_only_false_no_set(self, mock_psycopg):
        """Test read_only=False does NOT set read-only mode but still sets default GUCs."""
        conn = HologresConnection("hologres://user:pass@host:80/db", read_only=False)
        _ = conn.conn
        calls = mock_psycopg["conn"].execute.call_args_list
        # Default GUCs are still applied
        assert any("hg_experimental_enable_adaptive_execution" in str(c) for c in calls)
        assert any("hg_computing_resource" in str(c) for c in calls)
        # But read-only is NOT set
        assert not any("default_transaction_read_only" in str(c) for c in calls)

    def test_connection_reconnect(self, mock_psycopg):
        """Test reconnection when connection is closed."""
        conn = HologresConnection("hologres://user:pass@host:80/db")
        _ = conn.conn
        conn._conn.closed = True
        mock_psycopg["connect"].reset_mock()
        _ = conn.conn
        mock_psycopg["connect"].assert_called_once()

    def test_connection_close(self, mock_psycopg):
        """Test close method."""
        conn = HologresConnection("hologres://user:pass@host:80/db")
        _ = conn.conn
        conn.close()
        mock_psycopg["conn"].close.assert_called_once()
        assert conn._conn is None

    def test_connection_close_no_connection(self):
        """Test close without active connection."""
        conn = HologresConnection("hologres://user:pass@host/db")
        conn.close()

    def test_connection_context_manager(self, mock_psycopg):
        """Test context manager usage."""
        with HologresConnection("hologres://user:pass@host:80/db") as conn:
            _ = conn.conn
        mock_psycopg["conn"].close.assert_called_once()

    def test_connection_execute(self, mock_psycopg):
        """Test execute method."""
        mock_psycopg["cursor"].description = [("id",), ("name",)]
        mock_psycopg["cursor"].fetchall.return_value = [{"id": 1, "name": "Alice"}]

        conn = HologresConnection("hologres://user:pass@host:80/db")
        result = conn.execute("SELECT * FROM t")

        assert result == [{"id": 1, "name": "Alice"}]
        mock_psycopg["cursor"].execute.assert_called_with("SELECT * FROM t", None)

    def test_connection_execute_with_params(self, mock_psycopg):
        """Test execute method with params."""
        mock_psycopg["cursor"].description = [("id",)]
        mock_psycopg["cursor"].fetchall.return_value = [{"id": 1}]

        conn = HologresConnection("hologres://user:pass@host:80/db")
        result = conn.execute("SELECT * FROM t WHERE id = %s", (1,))

        mock_psycopg["cursor"].execute.assert_called_with("SELECT * FROM t WHERE id = %s", (1,))

    def test_connection_execute_no_results(self, mock_psycopg):
        """Test execute method with no results."""
        mock_psycopg["cursor"].description = None

        conn = HologresConnection("hologres://user:pass@host:80/db")
        result = conn.execute("INSERT INTO t VALUES (1)")

        assert result == []

    def test_connection_execute_many(self, mock_psycopg):
        """Test execute_many method."""
        conn = HologresConnection("hologres://user:pass@host:80/db")
        conn.execute_many("INSERT INTO t VALUES (%s)", [(1,), (2,)])

        mock_psycopg["cursor"].executemany.assert_called_with("INSERT INTO t VALUES (%s)", [(1,), (2,)])


class TestGetConnection:
    """Tests for get_connection function."""

    def test_get_connection_from_profile(self, mock_config, mock_psycopg):
        """Test get_connection resolves from profile."""
        conn = get_connection()
        assert isinstance(conn, HologresConnection)
        assert "testdb" in conn.raw_dsn

    def test_get_connection_named_profile(self, mock_config, mock_psycopg):
        """Test get_connection with named profile."""
        conn = get_connection(profile="default")
        assert isinstance(conn, HologresConnection)

    def test_get_connection_autocommit(self, mock_config, mock_psycopg):
        """Test get_connection with autocommit parameter."""
        conn = get_connection(autocommit=False)
        assert conn.autocommit is False

    def test_get_connection_read_only_default(self, mock_config, mock_psycopg):
        """Test get_connection defaults to read_only=True."""
        conn = get_connection()
        assert conn.read_only is True

    def test_get_connection_read_only_false(self, mock_config, mock_psycopg):
        """Test get_connection with read_only=False."""
        conn = get_connection(read_only=False)
        assert conn.read_only is False

    def test_get_connection_no_config(self, mock_home):
        """Test get_connection with no config raises DSNError."""
        with pytest.raises(DSNError):
            get_connection()
