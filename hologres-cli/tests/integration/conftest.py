"""Integration test fixtures for hologres-cli.

These fixtures create real database connections for integration testing.
Set TEST_PROFILE_NAME environment variable (preferred) or HOLOGRES_TEST_DSN (legacy).

Example:
    export TEST_PROFILE_NAME="default"
    # or legacy:
    export HOLOGRES_TEST_DSN="hologres://user:password@host:port/database"
"""

from __future__ import annotations

import os
import time
from typing import Generator

import pytest

from hologres_cli.connection import HologresConnection


@pytest.fixture(scope="session")
def test_profile() -> str:
    """Get profile name from TEST_PROFILE_NAME env var. Skips if not set."""
    profile = os.environ.get("TEST_PROFILE_NAME")
    if not profile:
        pytest.skip("TEST_PROFILE_NAME not set, skipping integration test")
    return profile


@pytest.fixture(scope="session")
def integration_dsn() -> str:
    """Get DSN for integration tests.

    Priority:
    1. TEST_PROFILE_NAME -> resolve DSN from profile
    2. HOLOGRES_TEST_DSN env var (legacy)
    3. Skip test
    """
    profile_name = os.environ.get("TEST_PROFILE_NAME")
    if profile_name:
        from hologres_cli.connection import resolve_dsn
        return resolve_dsn(profile_name)

    dsn = os.environ.get("HOLOGRES_TEST_DSN")
    if not dsn:
        pytest.skip("TEST_PROFILE_NAME or HOLOGRES_TEST_DSN not set, skipping integration test")
    return dsn


@pytest.fixture
def integration_conn(integration_dsn: str) -> Generator[HologresConnection, None, None]:
    """Create a real Hologres connection for integration tests.

    Connection is automatically closed after the test.
    """
    conn = HologresConnection(integration_dsn, read_only=False)
    yield conn
    conn.close()


@pytest.fixture
def integration_conn_no_autocommit(integration_dsn: str) -> Generator[HologresConnection, None, None]:
    """Create a real Hologres connection without autocommit for transaction tests."""
    conn = HologresConnection(integration_dsn, autocommit=False, read_only=False)
    yield conn
    conn.close()


@pytest.fixture
def test_table(integration_conn: HologresConnection) -> Generator[str, None, None]:
    """Create a temporary test table, automatically cleaned up after test.

    Returns the table name for use in tests.
    """
    table_name = "test_cli_integration"

    # Drop if exists and create fresh
    integration_conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    integration_conn.execute(f"""
        CREATE TABLE {table_name} (
            id INT PRIMARY KEY,
            name VARCHAR(100),
            phone VARCHAR(20),
            email VARCHAR(100),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    yield table_name

    # Cleanup
    integration_conn.execute(f"DROP TABLE IF EXISTS {table_name}")


@pytest.fixture
def test_table_with_data(test_table: str, integration_conn: HologresConnection) -> str:
    """Create test table with sample data.

    Returns the table name.
    """
    integration_conn.execute(f"""
        INSERT INTO {test_table} (id, name, phone, email) VALUES
        (1, 'Alice', '13812345678', 'alice@example.com'),
        (2, 'Bob', '15987654321', 'bob@example.com'),
        (3, 'Charlie', '18611112222', 'charlie@example.com')
    """)
    return test_table


@pytest.fixture
def unique_table_name() -> str:
    """Generate a unique table name for tests that need isolation."""
    timestamp = int(time.time() * 1000000)
    return f"test_cli_{timestamp}"


# ---------------------------------------------------------------------------
# API connection fixtures (for ExecuteStatement OpenAPI integration tests)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def api_test_profile() -> str:
    """Get API-mode profile name from env var.

    Priority:
    1. TEST_API_PROFILE_NAME — dedicated API profile
    2. TEST_PROFILE_NAME — existing profile (fixture forces connection_mode=api in-memory)
    3. Skip test
    """
    profile_name = os.environ.get("TEST_API_PROFILE_NAME") or os.environ.get("TEST_PROFILE_NAME")
    if not profile_name:
        pytest.skip("TEST_API_PROFILE_NAME or TEST_PROFILE_NAME not set, skipping API integration test")

    # Validate API prerequisites
    from hologres_cli.config_store import get_profile
    from hologres_cli.api_connection import _validate_api_profile, ApiConnectionError

    try:
        prof = get_profile(profile_name)
    except Exception:
        pytest.skip(f"Profile '{profile_name}' not found")

    try:
        _validate_api_profile(prof)
    except ApiConnectionError as exc:
        pytest.skip(f"Profile '{profile_name}' lacks API prerequisites: {exc}")

    return profile_name


@pytest.fixture
def api_conn(api_test_profile: str) -> Generator:
    """Create a real HologresApiConnection for integration tests (read_only=False)."""
    from hologres_cli.config_store import get_profile
    from hologres_cli.api_connection import HologresApiConnection

    prof = dict(get_profile(api_test_profile))
    prof["connection_mode"] = "api"
    conn = HologresApiConnection(prof, read_only=False)
    yield conn
    conn.close()


@pytest.fixture
def api_conn_readonly(api_test_profile: str) -> Generator:
    """Create a real HologresApiConnection with read_only=True."""
    from hologres_cli.config_store import get_profile
    from hologres_cli.api_connection import HologresApiConnection

    prof = dict(get_profile(api_test_profile))
    prof["connection_mode"] = "api"
    conn = HologresApiConnection(prof, read_only=True)
    yield conn
    conn.close()


@pytest.fixture
def api_test_table(api_conn) -> Generator[str, None, None]:
    """Create a temporary test table via API connection, auto-cleanup."""
    table_name = "test_api_integration"
    api_conn.execute(f"DROP TABLE IF EXISTS {table_name}")
    api_conn.execute(f"""
        CREATE TABLE {table_name} (
            id INT PRIMARY KEY,
            name VARCHAR(100),
            phone VARCHAR(20),
            email VARCHAR(100),
            created_at TIMESTAMPTZ DEFAULT NOW()
        )
    """)
    yield table_name
    api_conn.execute(f"DROP TABLE IF EXISTS {table_name}")


@pytest.fixture
def api_test_table_with_data(api_test_table: str, api_conn) -> str:
    """Create API test table with sample data."""
    api_conn.execute(f"""
        INSERT INTO {api_test_table} (id, name, phone, email) VALUES
        (1, 'Alice', '13812345678', 'alice@example.com'),
        (2, 'Bob', '15987654321', 'bob@example.com'),
        (3, 'Charlie', '18611112222', 'charlie@example.com')
    """)
    return api_test_table
