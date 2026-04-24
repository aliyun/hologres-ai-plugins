"""Shared pytest fixtures for Hologres CLI tests."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_env_dsn(monkeypatch):
    """Fixture to set/unset HOLOGRES_DSN environment variable."""
    def _set_dsn(dsn_value):
        if dsn_value is None:
            monkeypatch.delenv("HOLOGRES_DSN", raising=False)
        else:
            monkeypatch.setenv("HOLOGRES_DSN", dsn_value)
    return _set_dsn


@pytest.fixture
def clean_env(monkeypatch):
    """Remove HOLOGRES_DSN from environment."""
    monkeypatch.delenv("HOLOGRES_DSN", raising=False)


@pytest.fixture
def temp_config_dir(tmp_path):
    """Fixture to provide a temporary config directory."""
    config_dir = tmp_path / ".hologres"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def temp_config_file(temp_config_dir):
    """Fixture to provide a temporary config file."""
    return temp_config_dir / "config.env"


@pytest.fixture
def temp_log_dir(tmp_path):
    """Fixture to provide a temporary log directory."""
    log_dir = tmp_path / ".hologres"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def mock_home(tmp_path, monkeypatch):
    """Mock Path.home() to return tmp_path."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return tmp_path


@pytest.fixture
def mock_psycopg_connection():
    """Fixture to mock psycopg.Connection."""
    mock_conn = MagicMock()
    mock_conn.closed = False
    mock_conn.close.return_value = None
    mock_conn.commit.return_value = None
    mock_conn.rollback.return_value = None
    # Allow psycopg.sql.Composable.as_string() to use fallback encoding path
    mock_conn.connection = None
    return mock_conn


@pytest.fixture
def mock_psycopg_cursor():
    """Fixture to mock psycopg.Cursor."""
    mock_cursor = MagicMock()
    mock_cursor.description = None
    mock_cursor.fetchall.return_value = []
    mock_cursor.execute.return_value = None
    mock_cursor.copy.return_value = None
    return mock_cursor


@pytest.fixture
def mock_psycopg(mocker, mock_psycopg_connection, mock_psycopg_cursor):
    """Mock psycopg module for unit tests."""
    mock_psycopg_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_psycopg_cursor)
    mock_psycopg_connection.cursor.return_value.__exit__ = MagicMock(return_value=None)

    mock_connect = mocker.patch("psycopg.connect", return_value=mock_psycopg_connection)
    return {"connect": mock_connect, "conn": mock_psycopg_connection, "cursor": mock_psycopg_cursor}


@pytest.fixture
def sample_dsn():
    """Sample DSN string for testing."""
    return "hologres://testuser:testpass@example.hologres.aliyuncs.com:80/testdb"


@pytest.fixture
def sample_dsn_no_password():
    """Sample DSN without password for testing."""
    return "hologres://testuser@example.hologres.aliyuncs.com:80/testdb"


@pytest.fixture
def sample_dsn_postgresql():
    """Sample DSN with postgresql:// scheme."""
    return "postgresql://testuser:testpass@example.hologres.aliyuncs.com:80/testdb"


@pytest.fixture
def sample_rows():
    """Sample row data for testing."""
    return [
        {"id": 1, "name": "Alice", "email": "alice@example.com"},
        {"id": 2, "name": "Bob", "email": "bob@example.com"},
    ]


@pytest.fixture
def sample_sensitive_rows():
    """Sample rows with sensitive data for masking tests."""
    return [
        {
            "id": 1,
            "phone": "13812345678",
            "email": "test@example.com",
            "password": "secret123",
            "id_card": "330102199001011234",
            "bank_card": "6222021234567890123",
            "normal_field": "normal_value",
        },
    ]


@pytest.fixture
def cli_runner():
    """Create Click CLI test runner."""
    from click.testing import CliRunner
    return CliRunner()


@pytest.fixture
def mock_connection_class(mocker, mock_psycopg_connection, mock_psycopg_cursor):
    """Mock the HologresConnection class."""
    mock_psycopg_connection.cursor.return_value.__enter__ = MagicMock(return_value=mock_psycopg_cursor)
    mock_psycopg_connection.cursor.return_value.__exit__ = MagicMock(return_value=None)
    mock_psycopg_connection.masked_dsn = "hologres://testuser:***@example.hologres.aliyuncs.com:80/testdb"

    # Patch at the module level where it's used
    mock_connect = mocker.patch("psycopg.connect", return_value=mock_psycopg_connection)
    return mock_psycopg_connection


@pytest.fixture
def mock_get_connection(mocker, mock_connection_class):
    """Mock get_connection function for all command modules."""
    from hologres_cli.connection import HologresConnection

    mock_conn = MagicMock(spec=HologresConnection)
    mock_conn.masked_dsn = "hologres://testuser:***@example.hologres.aliyuncs.com:80/testdb"
    mock_conn.execute.return_value = []
    mock_conn.close.return_value = None
    mock_conn.conn = mock_connection_class
    mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=MagicMock())
    mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=None)

    # Patch get_connection in all modules that import it
    mocker.patch("hologres_cli.connection.get_connection", return_value=mock_conn)
    mocker.patch("hologres_cli.commands.sql.get_connection", return_value=mock_conn)
    mocker.patch("hologres_cli.commands.schema.get_connection", return_value=mock_conn)
    mocker.patch("hologres_cli.commands.data.get_connection", return_value=mock_conn)
    mocker.patch("hologres_cli.commands.status.get_connection", return_value=mock_conn)
    mocker.patch("hologres_cli.commands.warehouse.get_connection", return_value=mock_conn)
    mocker.patch("hologres_cli.commands.table.get_connection", return_value=mock_conn)
    mocker.patch("hologres_cli.commands.view.get_connection", return_value=mock_conn)
    mocker.patch("hologres_cli.commands.extension.get_connection", return_value=mock_conn)
    return mock_conn
