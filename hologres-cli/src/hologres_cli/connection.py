"""Connection management for Hologres CLI.

Supports DSN format: hologres://[user[:password]@]host[:port]/database[?options]
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

import psycopg
from psycopg.rows import dict_row

CONFIG_DIR = Path.home() / ".hologres"
CONFIG_FILE = CONFIG_DIR / "config.env"

DEFAULT_PORT = 80
DEFAULT_KEEPALIVES = {
    "keepalives": 1,
    "keepalives_idle": 130,
    "keepalives_interval": 10,
    "keepalives_count": 15,
}


class ConnectionError(Exception):
    """Exception raised for connection errors."""
    pass


class DSNError(Exception):
    """Exception raised for DSN parsing errors."""
    pass


def resolve_raw_dsn(dsn: Optional[str] = None) -> str:
    """Resolve DSN from multiple sources in priority order.

    1. CLI --dsn flag
    2. HOLOGRES_DSN environment variable
    3. ~/.hologres/config.env file
    4. Fail with helpful error message
    """
    if dsn:
        return dsn

    env_dsn = os.environ.get("HOLOGRES_DSN")
    if env_dsn:
        return env_dsn

    if CONFIG_FILE.exists():
        dsn_from_file = _read_dsn_from_config(CONFIG_FILE)
        if dsn_from_file:
            return dsn_from_file

    raise DSNError(
        "No DSN configured. Please provide a DSN using one of these methods:\n"
        "  1. --dsn flag: hologres --dsn 'hologres://user:pass@host:port/db' ...\n"
        "  2. HOLOGRES_DSN environment variable\n"
        "  3. ~/.hologres/config.env file with HOLOGRES_DSN=..."
    )


def _read_dsn_from_config(config_path: Path, key: str = "HOLOGRES_DSN") -> Optional[str]:
    """Read DSN from a config.env file by key name."""
    prefix = f"{key}="
    try:
        content = config_path.read_text()
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("#") or not line:
                continue
            if line.startswith(prefix):
                value = line[len(prefix):].strip()
                if (value.startswith('"') and value.endswith('"')) or \
                   (value.startswith("'") and value.endswith("'")):
                    value = value[1:-1]
                # Handle common shell escapes (\$ -> $, \" -> ", etc.)
                value = value.replace("\\$", "$").replace('\\"', '"').replace("\\\\", "\\")
                return value
    except Exception:
        pass
    return None


def resolve_instance_dsn(instance_name: str) -> str:
    """Resolve DSN for a named instance from config.env.

    Looks up HOLOGRES_DSN_<instance_name> in:
      1. Environment variable
      2. ~/.hologres/config.env

    Config example:
      HOLOGRES_DSN_myinstance="hologres://user:pass@host:port/db"
    """
    env_key = f"HOLOGRES_DSN_{instance_name}"

    # 1. Check environment variable
    env_dsn = os.environ.get(env_key)
    if env_dsn:
        return env_dsn

    # 2. Check config file
    if CONFIG_FILE.exists():
        dsn = _read_dsn_from_config(CONFIG_FILE, key=env_key)
        if dsn:
            return dsn

    raise DSNError(
        f"No DSN configured for instance '{instance_name}'.\n"
        f"Please add the following to ~/.hologres/config.env:\n"
        f"  {env_key}=\"hologres://user:pass@host:port/database\"\n"
        f"Or set environment variable: export {env_key}=\"hologres://...\""
    )


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
            elif key in ("connect_timeout", "options"):
                params[key] = value

    return params


def mask_dsn_password(dsn: str) -> str:
    """Mask password in DSN for logging purposes."""
    return re.sub(r"(://[^:]+:)[^@]+(@)", r"\1***\2", dsn)


class HologresConnection:
    """Connection wrapper for Hologres using psycopg3."""

    def __init__(self, dsn: str, autocommit: bool = True):
        self.raw_dsn = dsn
        self.masked_dsn = mask_dsn_password(dsn)
        self.autocommit = autocommit
        self._conn: Optional[psycopg.Connection] = None
        self._params = parse_dsn(dsn)

    @property
    def conn(self) -> psycopg.Connection:
        """Get or create the connection."""
        if self._conn is None or self._conn.closed:
            self._conn = psycopg.connect(**self._params, autocommit=self.autocommit)
        return self._conn

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


def get_connection(dsn: Optional[str] = None, autocommit: bool = True) -> HologresConnection:
    """Get a Hologres connection. Resolves DSN from multiple sources."""
    resolved_dsn = resolve_raw_dsn(dsn)
    return HologresConnection(resolved_dsn, autocommit=autocommit)
