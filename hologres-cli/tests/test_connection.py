"""Tests for connection module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hologres_cli.connection import (
    DSNError,
    HologresConnection,
    _read_dsn_from_config,
    get_connection,
    mask_dsn_password,
    parse_dsn,
    resolve_raw_dsn,
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


class TestReadDsnFromConfig:
    """Tests for _read_dsn_from_config function."""

    def test_read_dsn_from_config_valid(self, tmp_path):
        """Test valid config file."""
        config_file = tmp_path / "config.env"
        config_file.write_text("HOLOGRES_DSN=hologres://user:pass@host/db\n")
        result = _read_dsn_from_config(config_file)
        assert result == "hologres://user:pass@host/db"

    def test_read_dsn_from_config_with_quotes(self, tmp_path):
        """Test config with quoted value."""
        config_file = tmp_path / "config.env"
        config_file.write_text('HOLOGRES_DSN="hologres://user:pass@host/db"\n')
        result = _read_dsn_from_config(config_file)
        assert result == "hologres://user:pass@host/db"

    def test_read_dsn_from_config_with_single_quotes(self, tmp_path):
        """Test config with single quoted value."""
        config_file = tmp_path / "config.env"
        config_file.write_text("HOLOGRES_DSN='hologres://user:pass@host/db'\n")
        result = _read_dsn_from_config(config_file)
        assert result == "hologres://user:pass@host/db"

    def test_read_dsn_from_config_with_comments(self, tmp_path):
        """Test config with comments."""
        config_file = tmp_path / "config.env"
        config_file.write_text("# This is a comment\nHOLOGRES_DSN=hologres://user:pass@host/db\n")
        result = _read_dsn_from_config(config_file)
        assert result == "hologres://user:pass@host/db"

    def test_read_dsn_from_config_missing_file(self, tmp_path):
        """Test non-existent file returns None."""
        config_file = tmp_path / "nonexistent.env"
        result = _read_dsn_from_config(config_file)
        assert result is None

    def test_read_dsn_from_config_empty_file(self, tmp_path):
        """Test empty file returns None."""
        config_file = tmp_path / "config.env"
        config_file.write_text("")
        result = _read_dsn_from_config(config_file)
        assert result is None

    def test_read_dsn_from_config_shell_escapes(self, tmp_path):
        """Test config with shell escapes."""
        config_file = tmp_path / "config.env"
        config_file.write_text('HOLOGRES_DSN="hologres://user:p\\$ss@host/db"\n')
        result = _read_dsn_from_config(config_file)
        assert result == "hologres://user:p$ss@host/db"

    def test_read_dsn_from_config_no_key(self, tmp_path):
        """Test config without HOLOGRES_DSN key."""
        config_file = tmp_path / "config.env"
        config_file.write_text("OTHER_KEY=value\n")
        result = _read_dsn_from_config(config_file)
        assert result is None

    def test_read_dsn_from_config_multiline(self, tmp_path):
        """Test config with multiple lines."""
        config_file = tmp_path / "config.env"
        config_file.write_text("OTHER_KEY=value\nHOLOGRES_DSN=hologres://user:pass@host/db\nANOTHER=val\n")
        result = _read_dsn_from_config(config_file)
        assert result == "hologres://user:pass@host/db"


class TestResolveRawDsn:
    """Tests for resolve_raw_dsn function."""

    def test_resolve_raw_dsn_explicit(self, clean_env):
        """Test explicit DSN is returned directly."""
        dsn = "hologres://user:pass@host/db"
        result = resolve_raw_dsn(dsn)
        assert result == dsn

    def test_resolve_raw_dsn_from_env(self, mock_env_dsn, tmp_path):
        """Test DSN from environment variable."""
        mock_env_dsn("hologres://envuser:envpass@envhost/envdb")
        # Clear config file
        with patch("hologres_cli.connection.CONFIG_FILE", tmp_path / "nonexistent.env"):
            result = resolve_raw_dsn(None)
        assert result == "hologres://envuser:envpass@envhost/envdb"

    def test_resolve_raw_dsn_from_config_file(self, clean_env, tmp_path):
        """Test DSN from config file."""
        config_file = tmp_path / "config.env"
        config_file.write_text("HOLOGRES_DSN=hologres://configuser:configpass@confighost/configdb\n")
        with patch("hologres_cli.connection.CONFIG_FILE", config_file):
            result = resolve_raw_dsn(None)
        assert result == "hologres://configuser:configpass@confighost/configdb"

    def test_resolve_raw_dsn_priority_explicit_over_env(self, mock_env_dsn):
        """Test explicit DSN takes priority over environment."""
        mock_env_dsn("hologres://env:pass@host/db")
        result = resolve_raw_dsn("hologres://explicit:pass@host/db")
        assert result == "hologres://explicit:pass@host/db"

    def test_resolve_raw_dsn_priority_env_over_config(self, mock_env_dsn, tmp_path):
        """Test environment DSN takes priority over config file."""
        mock_env_dsn("hologres://env:pass@host/db")
        config_file = tmp_path / "config.env"
        config_file.write_text("HOLOGRES_DSN=hologres://config:pass@host/db\n")
        with patch("hologres_cli.connection.CONFIG_FILE", config_file):
            result = resolve_raw_dsn(None)
        assert result == "hologres://env:pass@host/db"

    def test_resolve_raw_dsn_no_source(self, clean_env, tmp_path):
        """Test no DSN available raises DSNError."""
        with patch("hologres_cli.connection.CONFIG_FILE", tmp_path / "nonexistent.env"):
            with pytest.raises(DSNError) as exc_info:
                resolve_raw_dsn(None)
        assert "No DSN configured" in str(exc_info.value)


class TestHologresConnection:
    """Tests for HologresConnection class."""

    def test_connection_init(self):
        """Test connection initialization."""
        conn = HologresConnection("hologres://user:pass@host/db")
        assert conn.raw_dsn == "hologres://user:pass@host/db"
        assert conn.autocommit is True
        assert conn._conn is None

    def test_connection_init_autocommit_false(self):
        """Test connection with autocommit=False."""
        conn = HologresConnection("hologres://user:pass@host/db", autocommit=False)
        assert conn.autocommit is False

    def test_connection_masked_dsn(self):
        """Test masked_dsn property."""
        conn = HologresConnection("hologres://user:secretpass@host/db")
        assert conn.masked_dsn == "hologres://user:***@host/db"

    def test_connection_lazy_connection(self, mock_psycopg):
        """Test lazy connection creation."""
        conn = HologresConnection("hologres://user:pass@host:80/db")
        # Connection not created yet
        assert conn._conn is None
        # Access conn property triggers connection
        _ = conn.conn
        assert conn._conn is not None
        mock_psycopg["connect"].assert_called_once()

    def test_connection_reconnect(self, mock_psycopg):
        """Test reconnection when connection is closed."""
        conn = HologresConnection("hologres://user:pass@host:80/db")
        _ = conn.conn
        # Simulate closed connection
        conn._conn.closed = True
        # Access conn again should reconnect
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
        # Should not raise
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

    def test_get_connection_default(self, clean_env, tmp_path, mock_psycopg):
        """Test get_connection with explicit DSN."""
        with patch("hologres_cli.connection.CONFIG_FILE", tmp_path / "nonexistent.env"):
            conn = get_connection("hologres://user:pass@host/db")
        assert isinstance(conn, HologresConnection)
        assert conn.raw_dsn == "hologres://user:pass@host/db"

    def test_get_connection_autocommit(self, clean_env, tmp_path, mock_psycopg):
        """Test get_connection with autocommit parameter."""
        with patch("hologres_cli.connection.CONFIG_FILE", tmp_path / "nonexistent.env"):
            conn = get_connection("hologres://user:pass@host/db", autocommit=False)
        assert conn.autocommit is False

    def test_get_connection_from_env(self, mock_env_dsn, tmp_path, mock_psycopg):
        """Test get_connection resolves DSN from environment."""
        mock_env_dsn("hologres://envuser:envpass@envhost/envdb")
        with patch("hologres_cli.connection.CONFIG_FILE", tmp_path / "nonexistent.env"):
            conn = get_connection()
        assert conn.raw_dsn == "hologres://envuser:envpass@envhost/envdb"
