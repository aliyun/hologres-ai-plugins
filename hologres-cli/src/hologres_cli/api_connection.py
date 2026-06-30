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

from . import credentials
from .config_store import ENDPOINT_TEMPLATES, split_endpoint_host_port


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
    auth_mode = profile.get("auth_mode", "ram")
    missing: list[str] = []
    if auth_mode != "sts":
        # 非 sts 模式需要显式 AK/SK；sts 的临时凭证由 get_connection 注入或
        # credential 对象现取，此处静态校验凭证源是否配置。
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
    if auth_mode == "sts" and not credentials.sts_prerequisites_met(profile):
        raise ApiConnectionError(
            "sts 模式需配置 profile.credentials_uri 或设置环境变量 "
            "ALIBABA_CLOUD_CREDENTIALS_URI / ALIBABA_CLOUD_ACCESS_KEY_ID 等。"
        )


def _build_masked_dsn(profile: dict[str, Any]) -> str:
    """Return a redacted ``hologres+api://...`` style DSN for logging.

    The host is derived from ``endpoint`` if set, otherwise from
    ``instance_id + region_id + nettype`` using the same templates the
    JDBC path uses; this keeps audit logs comparable across transports.
    """
    host = profile.get("endpoint") or ""
    if host:
        # 与 JDBC 路径一致:剥离用户粘入的 ``:port``,port 始终取 port 字段。
        host, _embedded_port = split_endpoint_host_port(host)
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

    The OpenAPI ``ExecuteStatement`` endpoint supports server-side
    parameterised queries (``$1``/``$2`` placeholders via the
    ``parameters`` array), but the rest of the CLI uses psycopg-style
    ``%s`` placeholders with client-side substitution.  We keep the
    client-side approach for compatibility; only the small set of types
    that the CLI actually passes is supported.
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
    """Build a Hologram OpenAPI client from a profile dict.

    STS 模式用 credential 对象（``Config(credential=...)``），SDK 全权取凭证 + 签名 +
    自动刷新，OpenAPI 路径不出现 security_token 字段、不依赖 SDK 隐式分支；
    其他模式用显式 AK/SK 字段（保持原行为）。
    """
    HologramClient, open_api_models, _ = _import_sdk()
    if profile.get("auth_mode") == "sts":
        config = open_api_models.Config(credential=credentials.get_credential_client(profile))
    else:
        config = open_api_models.Config(
            access_key_id=profile.get("access_key_id"),
            access_key_secret=profile.get("access_key_secret"),
        )
    region_id = profile.get("region_id") or "cn-hangzhou"
    config.endpoint = f"hologram.{region_id}.aliyuncs.com"
    config.read_timeout = 60000  # HTTP-level timeout (ms); server caps queryTimeout at 30s.
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

    We build the request body manually with the exact camelCase field
    names required by the server (``sql``, ``dbName``, ``maxRows``,
    ``queryTimeout``).  The SDK's typed ``execute_statement`` method
    would do this automatically, but ``call_api`` keeps us independent
    of SDK model changes and lets us control every field.
    """
    _, open_api_models, util_models = _import_sdk()
    from alibabacloud_openapi_util.client import Client as OpenApiUtilClient

    if runtime_options is None:
        runtime_options = util_models.RuntimeOptions()

    # Field names must match the official API schema exactly (camelCase):
    # https://help.aliyun.com/zh/hologres/developer-reference/api-hologram-2022-06-01-executestatement
    body: dict[str, Any] = {
        "sql": statement,
        "dbName": database,
        "maxRows": 1000,       # API maximum; avoids silent truncation at default 200
        "queryTimeout": 30,    # API maximum in seconds (hard cap)
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

    The documented ExecuteStatement response structure is::

        {
          "data": {
            "results": [{
              "columnMetadata": [{"name": "id", "type": "int4", "nullable": true}],
              "records": [["1", "hello"], ["2", "world"]],
              "count": 2,
              "truncated": false
            }]
          }
        }

    We try this structure first, then fall back to legacy shapes that
    earlier SDK versions or non-standard endpoints may return.
    """
    data = body.get("data") if isinstance(body, dict) else None
    if data is None:
        return []
    if isinstance(data, bool):
        # EnableExecuteStatement-style boolean payload — nothing to expose.
        return []

    # ---- Top-level data error: {success: false, errorCode, errorMessage} ----
    if isinstance(data, dict) and data.get("success") is False:
        err_code = data.get("errorCode") or "SQL_ERROR"
        err_msg = data.get("errorMessage") or "Query failed"
        raise ApiConnectionError(
            f"ExecuteStatement query error ({err_code}): {err_msg}"
        )

    # ---- Documented structure: data.results[0].records / columnMetadata ----
    if isinstance(data, dict):
        results = data.get("results") or []
        if results and isinstance(results[0], dict):
            result_obj = results[0]

            # Check for per-statement error before extracting rows.
            if result_obj.get("success") is False:
                err_code = result_obj.get("errorCode") or "SQL_ERROR"
                err_msg = result_obj.get("errorMessage") or "Query failed"
                raise ApiConnectionError(
                    f"ExecuteStatement query error ({err_code}): {err_msg}"
                )

            meta = result_obj.get("columnMetadata") or []
            records = result_obj.get("records") or []
            col_names: list[str] = []
            for i, col in enumerate(meta):
                if isinstance(col, dict):
                    name = col.get("name") or col.get("Name") or f"col_{i}"
                else:
                    name = str(col) if col else f"col_{i}"
                col_names.append(str(name))

            rows: list[dict[str, Any]] = []
            for rec in records:
                if isinstance(rec, dict):
                    rows.append(rec)
                elif isinstance(rec, (list, tuple)):
                    if col_names and len(col_names) == len(rec):
                        rows.append({col_names[i]: rec[i] for i in range(len(rec))})
                    else:
                        rows.append({f"col_{i}": v for i, v in enumerate(rec)})
                else:
                    rows.append({"value": rec})
            return rows

    # ---- Fallback: already a list of dicts ----
    if isinstance(data, list):
        if data and isinstance(data[0], dict):
            return data
        return [{"value": item} for item in data]

    # ---- Fallback: legacy flat dict with columns/rows keys ----
    if isinstance(data, dict):
        columns_meta = (
            data.get("columns")
            or data.get("Columns")
            or data.get("columnMetaList")
            or []
        )
        legacy_rows = (
            data.get("rows")
            or data.get("Rows")
            or data.get("rowList")
            or []
        )
        legacy_col_names: list[str] = []
        for col in columns_meta:
            if isinstance(col, dict):
                name = col.get("name") or col.get("Name") or col.get("columnName")
                if name:
                    legacy_col_names.append(str(name))
            elif isinstance(col, str):
                legacy_col_names.append(col)
        result: list[dict[str, Any]] = []
        for row in legacy_rows:
            if isinstance(row, dict):
                result.append(row)
            elif isinstance(row, (list, tuple)):
                if legacy_col_names and len(legacy_col_names) == len(row):
                    result.append({legacy_col_names[i]: row[i] for i in range(len(row))})
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
