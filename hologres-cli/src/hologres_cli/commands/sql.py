"""SQL execution command with safety guardrails."""

from __future__ import annotations

import re
import time
from typing import Any, Optional

import click

from ..connection import DSNError, get_connection
from ..logger import log_operation
from ..masking import mask_rows
from ..output import (
    FORMAT_JSON,
    connection_error,
    error,
    limit_required_error,
    print_output,
    query_error,
    success,
    success_rows,
)

DEFAULT_ROW_LIMIT = 100
PROBE_LIMIT = 101
MAX_FIELD_LENGTH = 1000

WRITE_KEYWORDS = {"INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE", "GRANT", "REVOKE"}
LIMIT_PATTERN = re.compile(r"\bLIMIT\s+\d+", re.IGNORECASE)
SELECT_PATTERN = re.compile(r"^\s*SELECT\b", re.IGNORECASE)


@click.command("sql")
@click.argument("query")
@click.option("--with-schema", "with_schema", is_flag=True, help="Include schema context")
@click.option("--no-limit-check", "no_limit_check", is_flag=True, help="Disable row limit check")
@click.option("--no-mask", "no_mask", is_flag=True, help="Disable sensitive field masking")
@click.pass_context
def sql_cmd(ctx: click.Context, query: str, with_schema: bool,
            no_limit_check: bool, no_mask: bool) -> None:
    """Execute a read-only SQL query with safety guardrails.

    Write operations (INSERT, UPDATE, DELETE, DROP, etc.) are blocked.

    \b
    Examples:
      hologres sql "SELECT * FROM users LIMIT 10"
      hologres sql --no-limit-check "SELECT * FROM large_table"
    """
    profile = ctx.obj.get("profile")
    fmt = ctx.obj.get("format", FORMAT_JSON)

    statements = _split_statements(query)
    if len(statements) > 1:
        results = []
        for stmt in statements:
            r = _execute_single(stmt, profile, fmt, with_schema, no_limit_check, no_mask)
            results.append(r)
        if fmt == FORMAT_JSON:
            print_output(success({"statements": results, "count": len(results)}))
    else:
        _execute_single(query, profile, fmt, with_schema, no_limit_check, no_mask, print_result=True)


def _execute_single(query: str, profile, fmt, with_schema, no_limit_check, no_mask,
                     print_result=False) -> dict[str, Any]:
    start_time = time.time()
    try:
        conn = get_connection(profile=profile)
    except DSNError as e:
        if print_result:
            print_output(connection_error(str(e), fmt))
        return {"error": {"code": "CONNECTION_ERROR", "message": str(e)}}

    query = query.strip()

    # Block all write operations
    if _is_write_operation(query):
        log_operation("sql", sql=query, dsn_masked=conn.masked_dsn, success=False,
                      error_code="WRITE_BLOCKED")
        msg = "Write operations (INSERT, UPDATE, DELETE, DROP, etc.) are not allowed"
        if print_result:
            print_output(error("WRITE_BLOCKED", msg, fmt))
        conn.close()
        return {"error": {"code": "WRITE_BLOCKED", "message": msg}}

    try:
        is_select = _is_select(query)

        if is_select and not no_limit_check and not _has_limit(query):
            probe_query = _add_limit(query, PROBE_LIMIT)
            probe_rows = conn.execute(probe_query)
            if len(probe_rows) > DEFAULT_ROW_LIMIT:
                duration_ms = (time.time() - start_time) * 1000
                log_operation("sql", sql=query, dsn_masked=conn.masked_dsn, success=False,
                              error_code="LIMIT_REQUIRED", duration_ms=duration_ms)
                if print_result:
                    print_output(limit_required_error(fmt))
                conn.close()
                return {"error": {"code": "LIMIT_REQUIRED", "message": "Too many rows"}}
            rows = probe_rows
        else:
            rows = conn.execute(query)

        duration_ms = (time.time() - start_time) * 1000

        if rows and isinstance(rows, list) and rows and isinstance(rows[0], dict):
            rows = _truncate_large_fields(rows)
            if not no_mask:
                rows = mask_rows(rows)

        log_operation("sql", sql=query, dsn_masked=conn.masked_dsn, success=True,
                      row_count=len(rows) if rows else 0, duration_ms=duration_ms)

        result = {"rows": rows, "count": len(rows) if rows else 0}
        if print_result:
            if with_schema and rows:
                schema_info = [{"name": k, "type": type(v).__name__} for k, v in rows[0].items()]
                result["schema"] = schema_info
                print_output(success(result, fmt))
            else:
                print_output(success_rows(rows, fmt))
        return result

    except Exception as e:
        duration_ms = (time.time() - start_time) * 1000
        log_operation("sql", sql=query, dsn_masked=conn.masked_dsn, success=False,
                      error_code="QUERY_ERROR", error_message=str(e), duration_ms=duration_ms)
        if print_result:
            print_output(query_error(str(e), fmt))
        return {"error": {"code": "QUERY_ERROR", "message": str(e)}}
    finally:
        conn.close()


def _split_statements(query: str) -> list[str]:
    statements = []
    current = []
    in_string = False
    string_char = None
    for char in query:
        if char in ("'", '"') and not in_string:
            in_string = True
            string_char = char
            current.append(char)
        elif char == string_char and in_string:
            in_string = False
            string_char = None
            current.append(char)
        elif char == ";" and not in_string:
            stmt = "".join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
        else:
            current.append(char)
    stmt = "".join(current).strip()
    if stmt:
        statements.append(stmt)
    return statements


def _is_write_operation(query: str) -> bool:
    match = re.match(r"^\s*(\w+)", query, re.IGNORECASE)
    if match:
        return match.group(1).upper() in WRITE_KEYWORDS
    return False


def _is_select(query: str) -> bool:
    return bool(SELECT_PATTERN.match(query))



def _has_limit(query: str) -> bool:
    return bool(LIMIT_PATTERN.search(query))


def _add_limit(query: str, limit: int) -> str:
    if _has_limit(query):
        return query
    return f"{query.rstrip(';').strip()} LIMIT {limit}"


def _truncate_large_fields(rows: list[dict[str, Any]], max_len: int = MAX_FIELD_LENGTH) -> list[dict[str, Any]]:
    result = []
    for row in rows:
        new_row = {}
        for key, value in row.items():
            if isinstance(value, str) and len(value) > max_len:
                new_row[key] = value[:max_len] + f"... [truncated, {len(value)} chars]"
            elif isinstance(value, bytes) and len(value) > max_len:
                new_row[key] = f"[binary data, {len(value)} bytes]"
            else:
                new_row[key] = value
        result.append(new_row)
    return result
