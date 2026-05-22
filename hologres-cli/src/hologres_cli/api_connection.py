"""HologresApiConnection — execute SQL via Hologram OpenAPI ``ExecuteStatement``.

This module provides a drop-in alternative to :class:`HologresConnection`
(JDBC / psycopg) that runs SQL through the Alibaba Cloud Hologram OpenAPI.

It is used in two scenarios:

1. ``connection_mode = "api"`` — explicit opt-in via profile setting.
2. ``connection_mode = "auto"`` (default) — silent fallback when the JDBC
   path cannot establish a connection (e.g. port 80 firewalled, the user
   is on a cross-region network, or the instance hasn't enabled the
   PostgreSQL gateway).

Prerequisites for the API path:

- Profile must have ``access_key_id`` + ``access_key_secret`` (RAM auth).
- Profile must have ``instance_id`` and ``region_id``.
- The Hologres instance must have ``EnableExecuteStatement`` turned on
  (``hologres instance-manage enable-execute-statement``).
- The RAM account must have the ``hologram:ExecuteStatement`` permission.

The public interface mirrors :class:`HologresConnection` so that
existing call-sites (``conn.execute(sql)``, ``conn.cursor()``,
``conn.close()``, context-manager usage, ``conn.masked_dsn``,
``conn.database``) keep working without modification.
"""

from __future__ import annotations

import re
from typing import Any, Iterator, Optional

from .config_store import ENDPOINT_TEMPLATES


class ApiConnectionError(Exception):
    """Raised when the OpenAPI SQL execution fails or is misconfigured."""
    pass


# Default session GUCs applied to every API-mode statement.
# Mirrors connection.DEFAULT_SESSION_GUCS so behaviour stays consistent
# regardless of which transport is in use.
DEFAULT_API_SESSION_GUCS: list[str] = [
    "SET hg_computing_resource = 'serverless'",
]


def _validate_api_profile(profile: dict[str, Any]) -> None:
    """Validate that the profile has all fields required for API mode.

    Raises :class:`ApiConnectionError` with a precise human-readable
    message when something is missing.
    """
    missing: list[str] = []
    if not profile.get("access_key_id"):
        missing.append("access_key_id")
    if not profile.get("access_key_secret"):
        missing.append("access_key_secret")
    if not profile.get("instance_id"):
        missing.append("instance_id")
    if not profile.get("region_id"):
        missing.append("region_id")
    if not profile.get("database"):
        missing.append("database")
    if missing:
        raise ApiConnectionError(
            "Hologres API connection requires the following profile fields: "
            + ", ".join(missing)
            + ". Run 'hologres config' to configure them."
        )


def _build_masked_dsn(profile: dict[str, Any]) -> str:
    """Return a redacted ``hologres+api://...`` style DSN for logging.

    The host is derived from ``endpoint`` if set, otherwise from
    ``instance_id + region_id + nettype`` using the same templates the
    JDBC path uses; this keeps audit logs comparable across transports.
    """
    host = profile.get("endpoint") or ""
    if not host:
        instance_id = profile.get("instance_id", "")
        region_id = profile.get("region_id", "")
        nettype = profile.get("nettype", "internet")
        template = ENDPOINT_TEMPLATES.get(nettype, ENDPOINT_TEMPLATES["internet"])
        host = template.format(instance_id=instance_id, region_id=region_id)
    user = profile.get("access_key_id", "anon")
    port = profile.get("port", 80)
    database = profile.get("database", "")
    return f"hologres+api://{user}:***@{host}:{port}/{database}"


# ---------------------------------------------------------------------------
# Parameter substitution
# ---------------------------------------------------------------------------

_PARAM_PLACEHOLDER = re.compile(r"%s")


def _quote_literal(value: Any) -> str:
    """Conservatively quote a single SQL literal for inline substitution.

    The OpenAPI ``ExecuteStatement`` endpoint takes a raw SQL string and
    has no separate parameter slot, so we fall back to client-side
    substitution.  Only the small set of types that the rest of the CLI
    actually passes is supported.
    """
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    if isinstance(value, str):
        return "'" + value.replace("'", "''") + "'"
    raise ApiConnectionError(
        f"Unsupported parameter type for API mode: {type(value).__name__}"
    )


def _substitute_params(sql: str, params: Optional[tuple]) -> str:
    """Substitute ``%s`` placeholders with quoted literals.

    Mirrors the subset of psycopg's parameter API that the existing CLI
    relies on.
    """
    if not params:
        return sql
    parts = _PARAM_PLACEHOLDER.split(sql)
    if len(parts) - 1 != len(params):
        raise ApiConnectionError(
            f"Parameter count mismatch: SQL has {len(parts) - 1} placeholders "
            f"but {len(params)} parameter(s) provided."
        )
    out: list[str] = [parts[0]]
    for value, segment in zip(params, parts[1:]):
        out.append(_quote_literal(value))
        out.append(segment)
    return "".join(out)


# ---------------------------------------------------------------------------
# OpenAPI client + low-level call
# ---------------------------------------------------------------------------


def _import_sdk():
    """Lazy import of the alibabacloud SDK pieces needed for the API."""
    from alibabacloud_hologram20220601.client import Client as HologramClient
    from alibabacloud_tea_openapi import models as open_api_models
    from alibabacloud_tea_util import models as util_models
    return HologramClient, open_api_models, util_models


def _create_client(profile: dict[str, Any]) -> Any:
    """Build a Hologram OpenAPI client from a profile dict."""
    HologramClient, open_api_models, _ = _import_sdk()
    config = open_api_models.Config(
        access_key_id=profile.get("access_key_id"),
        access_key_secret=profile.get("access_key_secret"),
    )
    region_id = profile.get("region_id") or "cn-hangzhou"
    config.endpoint = f"hologram.{region_id}.aliyuncs.com"
    config.read_timeout = 60000  # SQL queries can take longer than instance ops.
    return HologramClient(config)


def _execute_statement_via_call_api(
    client: Any,
    instance_id: str,
    statement: str,
    database: str,
    runtime_options: Any = None,
) -> dict[str, Any]:
    """Invoke the ``ExecuteStatement`` OpenAPI through the SDK's generic
    ``call_api`` mechanism.

    The dedicated method ``client.execute_statement`` is only available in
    newer SDK builds, so we always go through ``call_api`` for maximum
    compatibility.
    """
    _, open_api_models, util_models = _import_sdk()
    from alibabacloud_openapi_util.client import Client as OpenApiUtilClient

    if runtime_options is None:
        runtime_options = util_models.RuntimeOptions()

    body: dict[str, Any] = {
        "Statement": statement,
        "Database": database,
    }

    req = open_api_models.OpenApiRequest(
        headers={},
        body=body,
    )
    params = open_api_models.Params(
        action="ExecuteStatement",
        version="2022-06-01",
        protocol="HTTPS",
        pathname=f"/api/v1/instances/{OpenApiUtilClient.get_encode_param(instance_id)}/executeStatement",
        method="POST",
        auth_type="AK",
        style="ROA",
        req_body_type="json",
        body_type="json",
    )
    return client.call_api(params, req, runtime_options)


def _normalize_response(raw: Any) -> dict[str, Any]:
    """Turn whatever ``call_api`` returns into a plain dict."""
    if isinstance(raw, dict):
        body = raw.get("body", raw)
        if isinstance(body, dict):
            return body
        return raw
    body = getattr(raw, "body", None)
    if isinstance(body, dict):
        return body
    if hasattr(raw, "to_map"):
        try:
            mapped = raw.to_map()
            if isinstance(mapped, dict):
                return mapped.get("body", mapped)
        except Exception:
            pass
    return {"raw": raw}


def _rows_from_response(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Parse the ``data`` payload into ``[{col: value, ...}, ...]``.

    The server may return data in several shapes; we try the documented
    variant first, then degrade gracefully.
    """
    data = body.get("data") if isinstance(body, dict) else None
    if data is None:
        return []
    if isinstance(data, bool):
        # EnableExecuteStatement-style boolean payload — nothing to expose.
        return []
    if isinstance(data, list):
        # Already a list of dicts.
        if data and isinstance(data[0], dict):
            return data
        return [{"value": item} for item in data]
    if isinstance(data, dict):
        columns_meta = (
            data.get("columns")
            or data.get("Columns")
            or data.get("columnMetaList")
            or []
        )
        rows = (
            data.get("rows")
            or data.get("Rows")
            or data.get("rowList")
            or []
        )
        column_names: list[str] = []
        for col in columns_meta:
            if isinstance(col, dict):
                name = col.get("name") or col.get("Name") or col.get("columnName")
                if name:
                    column_names.append(str(name))
            elif isinstance(col, str):
                column_names.append(col)
        result: list[dict[str, Any]] = []
        for row in rows:
            if isinstance(row, dict):
                result.append(row)
            elif isinstance(row, (list, tuple)):
                if column_names and len(column_names) == len(row):
                    result.append({column_names[i]: row[i] for i in range(len(row))})
                else:
                    result.append({f"col_{i}": v for i, v in enumerate(row)})
            else:
                result.append({"value": row})
        return result
    return []


# ---------------------------------------------------------------------------
# Cursor + connection shims
# ---------------------------------------------------------------------------


class _ApiCursor:
    """Minimal cursor shim providing the methods the rest of the CLI uses.

    Only ``execute()``, ``executemany()``, ``fetchall()``, ``description``,
    ``rowcount``, and the context-manager protocol are supported.
    """

    def __init__(self, owner: "HologresApiConnection") -> None:
        self._owner = owner
        self._rows: list[dict[str, Any]] = []
        self.description: Optional[list[tuple]] = None
        self.rowcount: int = -1

    def __enter__(self) -> "_ApiCursor":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None

    def close(self) -> None:
        self._rows = []

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        rows = self._owner._run_sql(sql, params)
        self._rows = rows
        self.rowcount = len(rows)
        if rows:
            self.description = [(name,) for name in rows[0].keys()]
        else:
            self.description = None

    def executemany(self, sql: str, params_list: list[tuple]) -> None:
        for params in params_list:
            self.execute(sql, params)

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    def fetchone(self) -> Optional[dict[str, Any]]:
        return self._rows[0] if self._rows else None

    def __iter__(self) -> Iterator[dict[str, Any]]:
        return iter(self._rows)


class _ApiSessionShim:
    """Stand-in for ``psycopg.Connection`` exposed via ``conn.conn``.

    The hologres-cli command modules occasionally call
    ``conn.conn.execute(SET ...)`` to apply session GUCs.  Since the API
    is stateless, we capture those statements and prepend them to the
    next executed SQL so the runtime behaviour matches the JDBC path.
    """

    def __init__(self, owner: "HologresApiConnection") -> None:
        self._owner = owner
        self.closed = False

    def execute(self, sql: str, params: Optional[tuple] = None) -> None:
        # Buffer the statement to be prepended on the next user query.
        if params:
            sql = _substitute_params(sql, params)
        self._owner._pending_session_sql.append(sql.rstrip(";").strip())

    def cursor(self, *args, **kwargs) -> _ApiCursor:
        return self._owner.cursor()

    def close(self) -> None:
        self.closed = True


class HologresApiConnection:
    """Connection wrapper that runs SQL via the Hologram ``ExecuteStatement`` API.

    Public interface intentionally mirrors :class:`HologresConnection` so
    that callers can swap implementations transparently.
    """

    def __init__(
        self,
        profile: dict[str, Any],
        autocommit: bool = True,
        read_only: bool = True,
    ) -> None:
        _validate_api_profile(profile)
        self._profile = dict(profile)  # defensive copy
        self.autocommit = autocommit
        self.read_only = read_only
        self.raw_dsn = _build_masked_dsn(profile)
        self.masked_dsn = self.raw_dsn  # already redacted
        self._client: Any = None
        self._closed = False
        self._pending_session_sql: list[str] = list(DEFAULT_API_SESSION_GUCS)
        if read_only:
            self._pending_session_sql.append("SET default_transaction_read_only = ON")
        self._session_shim = _ApiSessionShim(self)

    # ------------------------------------------------------------------
    # Public, JDBC-compatible interface
    # ------------------------------------------------------------------

    @property
    def database(self) -> str:
        return self._profile.get("database", "")

    @property
    def conn(self) -> _ApiSessionShim:
        """Return a session shim that absorbs ``SET ...`` statements.

        Mirrors :attr:`HologresConnection.conn` so callers that do
        ``conn.conn.execute(SET ...)`` keep working under API mode.
        """
        return self._session_shim

    def cursor(self) -> _ApiCursor:
        if self._closed:
            raise ApiConnectionError("Connection is closed.")
        return _ApiCursor(self)

    def execute(self, sql: str, params: Optional[tuple] = None) -> list[dict[str, Any]]:
        return self._run_sql(sql, params)

    def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        for params in params_list:
            self._run_sql(sql, params)

    def close(self) -> None:
        self._closed = True
        self._client = None

    def __enter__(self) -> "HologresApiConnection":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                self._client = _create_client(self._profile)
            except ImportError as exc:
                raise ApiConnectionError(
                    "alibabacloud_hologram20220601 + alibabacloud-tea-openapi "
                    "are required for API mode. Install with: "
                    "pip install alibabacloud_hologram20220601 alibabacloud-tea-openapi"
                ) from exc
            except Exception as exc:
                raise ApiConnectionError(
                    f"Failed to initialise Hologram OpenAPI client: {exc}"
                ) from exc
        return self._client

    def _compose_sql(self, sql: str) -> str:
        """Prepend any buffered session GUCs to *sql*, separated by ``;``."""
        sql = sql.strip().rstrip(";")
        if not self._pending_session_sql:
            return sql
        prefix = ";\n".join(s for s in self._pending_session_sql if s)
        return prefix + ";\n" + sql if prefix else sql

    def _run_sql(self, sql: str, params: Optional[tuple] = None) -> list[dict[str, Any]]:
        if self._closed:
            raise ApiConnectionError("Connection is closed.")
        if params:
            sql = _substitute_params(sql, params)
        full_sql = self._compose_sql(sql)
        client = self._get_client()
        try:
            raw = _execute_statement_via_call_api(
                client,
                instance_id=self._profile["instance_id"],
                statement=full_sql,
                database=self.database,
            )
        except Exception as exc:
            # Surface SDK error messages without leaking the SQL body.
            msg = getattr(exc, "message", None) or str(exc)
            code = getattr(exc, "code", None)
            details = f" (code={code})" if code else ""
            raise ApiConnectionError(
                f"ExecuteStatement API call failed{details}: {msg}"
            ) from exc

        body = _normalize_response(raw)

        if isinstance(body, dict) and body.get("success") is False:
            err_code = body.get("errorCode") or "API_ERROR"
            err_msg = body.get("errorMessage") or "Unknown API error"
            raise ApiConnectionError(
                f"ExecuteStatement returned failure ({err_code}): {err_msg}"
            )

        return _rows_from_response(body)
