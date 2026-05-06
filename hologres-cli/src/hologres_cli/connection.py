"""Connection management for Hologres CLI.

All connection parameters are resolved from config profiles (~/.hologres/config.json).
DSN format: hologres://[user[:password]@]host[:port]/database[?options]
"""

from __future__ import annotations

import re
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

import psycopg
from psycopg.rows import dict_row

from .config_store import ConfigError, build_dsn_from_profile, get_current_profile, get_profile

DEFAULT_PORT = 80
DEFAULT_KEEPALIVES = {
    "keepalives": 1,
    "keepalives_idle": 130,
    "keepalives_interval": 10,
    "keepalives_count": 15,
}

# Default session GUCs applied to every connection for safety and resource control
DEFAULT_SESSION_GUCS = [
    "SET hg_experimental_enable_adaptive_execution = on",  # Adaptive execution to prevent OOM
    "SET hg_computing_resource = 'serverless'",  # Route queries to serverless computing pool
]


class ConnectionError(Exception):
    """Exception raised for connection errors."""
    pass


class DSNError(Exception):
    """Exception raised for DSN parsing or configuration errors."""
    pass


def resolve_dsn(profile_name: Optional[str] = None) -> str:
    """Resolve DSN from config profile.

    Priority:
    1. Named profile (--profile flag)
    2. Current profile from config.json
    3. Fail with helpful error message
    """
    try:
        if profile_name:
            profile = get_profile(profile_name)
        else:
            profile = get_current_profile()
        return build_dsn_from_profile(profile)
    except ConfigError as e:
        raise DSNError(str(e))


def parse_dsn(dsn: str) -> dict[str, Any]:
    """Parse a Hologres DSN into connection parameters.

    DSN format: hologres://[user[:password]@]host[:port]/database[?options]
    """
    if dsn.startswith("hologres://"):
        dsn_normalized = "postgresql://" + dsn[len("hologres://"):]
    elif dsn.startswith("postgresql://") or dsn.startswith("postgres://"):
        dsn_normalized = dsn
    else:
        raise DSNError(
            f"Invalid DSN scheme. Expected 'hologres://' or 'postgresql://', got: {dsn[:20]}..."
        )

    try:
        parsed = urlparse(dsn_normalized)
    except Exception as e:
        raise DSNError(f"Failed to parse DSN: {e}")

    if not parsed.hostname:
        raise DSNError("DSN must include a hostname")

    if not parsed.path or parsed.path == "/":
        raise DSNError("DSN must include a database name (e.g., /mydatabase)")

    params: dict[str, Any] = {
        "host": parsed.hostname,
        "port": parsed.port or DEFAULT_PORT,
        "dbname": parsed.path.lstrip("/"),
    }

    if parsed.username:
        params["user"] = unquote(parsed.username)
    if parsed.password:
        params["password"] = unquote(parsed.password)

    params.update(DEFAULT_KEEPALIVES)

    if parsed.query:
        query_params = parse_qs(parsed.query)
        for key, values in query_params.items():
            value = values[0] if values else ""
            if key in ("keepalives", "keepalives_idle", "keepalives_interval", "keepalives_count"):
                try:
                    params[key] = int(value)
                except ValueError:
                    raise DSNError(f"Invalid integer value for {key}: {value}")
            elif key in ("connect_timeout", "options", "application_name"):
                params[key] = value

    # application_name: 始终以 "hologres-cli" 为前缀
    # - DSN 未指定 -> "hologres-cli"
    # - DSN 已指定 -> "hologres-cli/<user_defined>"
    user_app_name = params.pop("application_name", None)
    if user_app_name:
        params["application_name"] = f"hologres-cli/{user_app_name}"
    else:
        params["application_name"] = "hologres-cli"

    return params


def mask_dsn_password(dsn: str) -> str:
    """Mask password in DSN for logging purposes."""
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", dsn)


class HologresConnection:
    """Connection wrapper for Hologres using psycopg3."""

    def __init__(self, dsn: str, autocommit: bool = True, read_only: bool = True):
        self.raw_dsn = dsn
        self.masked_dsn = mask_dsn_password(dsn)
        self.autocommit = autocommit
        self.read_only = read_only
        self._conn: Optional[psycopg.Connection] = None
        self._params = parse_dsn(dsn)

    @property
    def conn(self) -> psycopg.Connection:
        """Get or create the connection.

        When read_only=True (default), the session is set to read-only mode
        via ``SET default_transaction_read_only = ON``.  This provides
        database-level protection against accidental writes.

        All connections also set default session GUCs:
        - hg_experimental_enable_adaptive_execution=on (prevent OOM)
        - hg_computing_resource='serverless' (use serverless computing pool)
        """
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(**self._params, autocommit=self.autocommit)
            # Apply default session GUCs for safety and resource control
            for guc in DEFAULT_SESSION_GUCS:
                self._conn.execute(guc)
            if self.read_only:
                self._conn.execute("SET default_transaction_read_only = ON")
        return self._conn

    @property
    def database(self) -> str:
        """Return the database name from the connection DSN."""
        return self._params["dbname"]

    def cursor(self) -> psycopg.Cursor:
        """Create a cursor with dict row factory."""
        return self.conn.cursor(row_factory=dict_row)

    def execute(self, sql: str, params: Optional[tuple] = None) -> list[dict[str, Any]]:
        """Execute a SQL query and return results as list of dicts."""
        with self.cursor() as cur:
            cur.execute(sql, params)
            if cur.description:
                return cur.fetchall()
            return []

    def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute a SQL query multiple times with different parameters."""
        with self.cursor() as cur:
            cur.executemany(sql, params_list)

    def close(self) -> None:
        """Close the connection."""
        if self._conn and not self._conn.closed:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> "HologresConnection":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()


def get_connection(
    profile: Optional[str] = None,
    autocommit: bool = True,
    read_only: bool = True,
) -> HologresConnection:
    """Get a Hologres connection from config profile.

    Args:
        profile: Profile name to use. If None, uses current profile.
        autocommit: Whether to use autocommit mode.
        read_only: Whether to set the connection to read-only mode.
                   Default True — the session executes
                   ``SET default_transaction_read_only = ON`` upon creation,
                   so any write statement (INSERT / UPDATE / DELETE / DDL)
                   will be rejected by the database engine.
                   Pass ``read_only=False`` for commands that need write access.
    """
    resolved_dsn = resolve_dsn(profile)
    return HologresConnection(resolved_dsn, autocommit=autocommit, read_only=read_only)
