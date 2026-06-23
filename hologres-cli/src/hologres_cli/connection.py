"""Connection management for Hologres CLI.

All connection parameters are resolved from config profiles (~/.hologres/config.json).
DSN format: hologres://[user[:password]@]host[:port]/database[?options]
"""

from __future__ import annotations

import os
import re
from typing import Any, Optional
from urllib.parse import parse_qs, unquote, urlparse

import psycopg
from psycopg.rows import dict_row

from . import credentials
from .api_connection import ApiConnectionError, HologresApiConnection
from .config_store import ConfigError, build_dsn_from_profile, get_current_profile, get_profile

DEFAULT_PORT = 80
SKILL_ENV_VAR = "HOLOGRES_SKILL"
DEFAULT_KEEPALIVES = {
    "keepalives": 1,
    "keepalives_idle": 130,
    "keepalives_interval": 10,
    "keepalives_count": 15,
}

# Default session GUCs applied to every connection for safety and resource control
DEFAULT_SESSION_GUCS = [
    "SET hg_computing_resource = 'serverless'",  # Route queries to serverless computing pool
]

# GUC applied only to DML statements (SELECT/INSERT/UPDATE), NOT to EXPLAIN/EXPLAIN ANALYZE
ADAPTIVE_EXECUTION_GUC = "SET hg_experimental_enable_adaptive_execution = on"


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

    # application_name 格式: hologres-cli[/skill_name][/user_defined]
    # - 无 skill, 无自定义: "hologres-cli"
    # - 有 skill, 无自定义: "hologres-cli/hologres-query-optimizer"
    # - 有 skill, 有自定义: "hologres-cli/hologres-query-optimizer/my-app"
    # - 无 skill, 有自定义: "hologres-cli/my-app"
    user_app_name = params.pop("application_name", None)
    skill_name = os.environ.get(SKILL_ENV_VAR, "")

    parts = ["hologres-cli"]
    if skill_name:
        parts.append(skill_name)
    if user_app_name:
        parts.append(user_app_name)
    params["application_name"] = "/".join(parts)

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


def _resolve_profile_dict(profile: Optional[str]) -> dict[str, Any]:
    """Resolve a profile *name* (or None for current) to a profile dict."""
    try:
        if profile:
            return get_profile(profile)
        return get_current_profile()
    except ConfigError as e:
        raise DSNError(str(e))


def _api_prerequisites_met(profile: dict[str, Any]) -> bool:
    """Return True if the profile has enough info for the API fallback."""
    if (profile.get("auth_mode") or "ram") == "sts":
        # STS 模式：profile 无固定 AK/SK，判断凭证源是否配置（不发网络）。
        # 回退 API 时走 credential 对象路径（单例 client），不依赖注入的临时 AK。
        return bool(
            profile.get("instance_id")
            and profile.get("region_id")
            and profile.get("database")
            and credentials.sts_prerequisites_met(profile)
        )
    return bool(
        profile.get("access_key_id")
        and profile.get("access_key_secret")
        and profile.get("instance_id")
        and profile.get("region_id")
        and profile.get("database")
    )


def get_connection(
    profile: Optional[str] = None,
    autocommit: bool = True,
    read_only: bool = True,
):
    """Get a Hologres connection from a config profile.

    The transport is selected by the profile's ``connection_mode`` field:

    - ``"jdbc"`` — Postgres wire protocol via ``psycopg`` (lazy connect,
      classic behaviour, no fallback).
    - ``"api"``  — Hologram OpenAPI ``ExecuteStatement``.
    - ``"auto"`` (default) — try JDBC first; if the connect attempt
      fails AND the profile has the AK/SK + instance_id needed for the
      API path, transparently fall back to API mode.  Otherwise the
      original JDBC error is re-raised.

    Args:
        profile: Profile name to use. If None, uses the current profile.
        autocommit: Whether to use autocommit mode (JDBC only).
        read_only: Whether to enable read-only protections.  For JDBC
            this issues ``SET default_transaction_read_only = ON`` upon
            connection.  For API mode the same GUC is buffered and
            included on each ``ExecuteStatement`` call.
    """
    prof = _resolve_profile_dict(profile)
    # STS 模式：从凭据源现拉临时凭证，注入到 profile 副本（不入库、不污染 config_store）。
    # 下游 build_dsn_from_profile / HologresApiConnection 透明消费注入后的 prof。
    if prof.get("auth_mode") == "sts":
        prof = dict(prof)
        sts = credentials.resolve_sts_credentials(prof)  # 失败抛 CredentialsError，向上传播
        prof["access_key_id"] = sts["access_key_id"]
        prof["access_key_secret"] = sts["access_key_secret"]
        prof["security_token"] = sts["security_token"]
    mode = (prof.get("connection_mode") or "auto").lower()

    # Pure API mode: no JDBC attempt at all.
    if mode == "api":
        try:
            return HologresApiConnection(prof, autocommit=autocommit, read_only=read_only)
        except ApiConnectionError as exc:
            raise DSNError(str(exc))

    # JDBC mode (with optional fallback for "auto").
    try:
        dsn = build_dsn_from_profile(prof)
    except ConfigError as exc:
        raise DSNError(str(exc))

    jdbc_conn = HologresConnection(dsn, autocommit=autocommit, read_only=read_only)

    if mode != "auto":
        # Strict JDBC mode: keep classic lazy-connect behaviour.
        return jdbc_conn

    # auto: probe JDBC eagerly so we can fall back deterministically.
    try:
        _ = jdbc_conn.conn  # forces psycopg.connect()
        return jdbc_conn
    except Exception as exc:
        try:
            jdbc_conn.close()
        except Exception:
            pass
        if not _api_prerequisites_met(prof):
            raise DSNError(
                "JDBC connection failed and API fallback is unavailable "
                f"(missing access_key_id/access_key_secret/instance_id/region_id/database): {exc}"
            )
        try:
            return HologresApiConnection(
                prof, autocommit=autocommit, read_only=read_only
            )
        except ApiConnectionError as api_exc:
            raise DSNError(
                f"JDBC connection failed ({exc}); API fallback also failed: {api_exc}"
            )
