"""Unified output formatting for Hologres CLI.

Supports JSON, table, CSV, and JSONL formats.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from typing import Any, Optional

from tabulate import tabulate

FORMAT_JSON = "json"
FORMAT_TABLE = "table"
FORMAT_CSV = "csv"
FORMAT_JSONL = "jsonl"
VALID_FORMATS = [FORMAT_JSON, FORMAT_TABLE, FORMAT_CSV, FORMAT_JSONL]


def success(data: Any, format: str = FORMAT_JSON, message: Optional[str] = None) -> str:
    """Format a successful response."""
    response = {"ok": True, "data": data}
    if message:
        response["message"] = message
    return _format_output(response, format)


def success_rows(
    rows: list[dict[str, Any]],
    format: str = FORMAT_JSON,
    columns: Optional[list[str]] = None,
    message: Optional[str] = None,
    total_count: Optional[int] = None,
) -> str:
    """Format a successful response with row data."""
    if format == FORMAT_TABLE:
        return _format_table(rows, columns)
    elif format == FORMAT_CSV:
        return _format_csv(rows, columns)
    elif format == FORMAT_JSONL:
        return _format_jsonl(rows)
    else:
        response: dict[str, Any] = {
            "ok": True,
            "data": {"rows": rows, "count": len(rows)},
        }
        if total_count is not None:
            response["data"]["total_count"] = total_count
        if message:
            response["message"] = message
        return json.dumps(response, indent=2, ensure_ascii=False, default=str)


def error(code: str, message: str, format: str = FORMAT_JSON, details: Optional[dict] = None) -> str:
    """Format an error response."""
    error_obj: dict[str, Any] = {"code": code, "message": message}
    if details:
        error_obj["details"] = details
    response = {"ok": False, "error": error_obj}
    return json.dumps(response, indent=2, ensure_ascii=False, default=str)


def _format_output(response: dict[str, Any], format: str) -> str:
    """Format a response dictionary."""
    if format == FORMAT_TABLE:
        data = response.get("data")
        if isinstance(data, list):
            return _format_table(data)
        elif isinstance(data, dict):
            rows = [{"key": k, "value": v} for k, v in data.items()]
            return _format_table(rows, ["key", "value"])
        else:
            return str(data)
    elif format == FORMAT_CSV:
        data = response.get("data")
        if isinstance(data, list):
            return _format_csv(data)
        return str(data)
    elif format == FORMAT_JSONL:
        data = response.get("data")
        if isinstance(data, list):
            return _format_jsonl(data)
        return json.dumps(data, ensure_ascii=False, default=str)
    else:
        return json.dumps(response, indent=2, ensure_ascii=False, default=str)


def _format_table(rows: list[dict[str, Any]], columns: Optional[list[str]] = None) -> str:
    """Format rows as a human-readable table."""
    if not rows:
        return "(no rows)"
    if columns is None:
        columns = list(rows[0].keys())
    table_data = [[row.get(col, "") for col in columns] for row in rows]
    return tabulate(table_data, headers=columns, tablefmt="simple")


def _format_csv(rows: list[dict[str, Any]], columns: Optional[list[str]] = None) -> str:
    """Format rows as CSV."""
    if not rows:
        return ""
    if columns is None:
        columns = list(rows[0].keys())
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=columns, extrasaction='ignore')
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue()


def _format_jsonl(rows: list[dict[str, Any]]) -> str:
    """Format rows as JSON Lines."""
    lines = [json.dumps(row, ensure_ascii=False, default=str) for row in rows]
    return "\n".join(lines)


def print_output(output: str, file=None) -> None:
    """Print output to stdout."""
    print(output, file=file or sys.stdout)


def connection_error(message: str, format: str = FORMAT_JSON) -> str:
    return error("CONNECTION_ERROR", message, format)


def query_error(message: str, format: str = FORMAT_JSON, details: Optional[dict] = None) -> str:
    return error("QUERY_ERROR", message, format, details)


def limit_required_error(format: str = FORMAT_JSON) -> str:
    return error("LIMIT_REQUIRED", "Query returns more than 100 rows. Please add a LIMIT clause.", format)


def write_guard_error(format: str = FORMAT_JSON) -> str:
    return error("WRITE_GUARD_ERROR", "Write operations require the --write flag.", format)


def dangerous_write_error(operation: str, format: str = FORMAT_JSON) -> str:
    return error("DANGEROUS_WRITE_BLOCKED", f"{operation} without WHERE clause is blocked.", format)
