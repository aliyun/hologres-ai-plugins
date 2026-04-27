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
from typing import Generator, Optional

import pytest

from hologres_cli.connection import HologresConnection


@pytest.fixture(scope="session")
def test_profile() -> Optional[str]:
    """Get profile name from TEST_PROFILE_NAME env var, or None."""
    return os.environ.get("TEST_PROFILE_NAME")


@pytest.fixture(scope="session")
def integration_dsn(test_profile) -> str:
    """Get DSN for integration tests.

    Priority:
    1. TEST_PROFILE_NAME -> resolve DSN from profile
    2. HOLOGRES_TEST_DSN env var (legacy)
    3. Skip test
    """
    if test_profile:
        from hologres_cli.connection import resolve_dsn
        return resolve_dsn(test_profile)

    dsn = os.environ.get("HOLOGRES_TEST_DSN")
    if not dsn:
        pytest.skip("TEST_PROFILE_NAME or HOLOGRES_TEST_DSN not set, skipping integration test")
    return dsn


@pytest.fixture
def integration_conn(integration_dsn: str) -> Generator[HologresConnection, None, None]:
    """Create a real Hologres connection for integration tests.

    Connection is automatically closed after the test.
    """
    conn = HologresConnection(integration_dsn)
    yield conn
    conn.close()


@pytest.fixture
def integration_conn_no_autocommit(integration_dsn: str) -> Generator[HologresConnection, None, None]:
    """Create a real Hologres connection without autocommit for transaction tests."""
    conn = HologresConnection(integration_dsn, autocommit=False)
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
