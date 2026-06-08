"""Unified error code registry for Hologres CLI.

Every error code carries machine-readable metadata so that AI agents can
automatically decide whether to retry and how to fix the problem.

Usage::

    from .errors import ErrorCode

    # In output helpers:
    error(ErrorCode.CONNECTION_ERROR, "Connection refused")

    # Backward-compatible string usage still works:
    error("CONNECTION_ERROR", "Connection refused")
"""

from __future__ import annotations

from enum import Enum
from typing import NamedTuple, Optional


class ErrorMeta(NamedTuple):
    """Metadata attached to each error code."""

    code: str
    retryable: bool
    hint: str  # AI-parseable fix suggestion


class ErrorCode(Enum):
    """Unified error codes with retry and hint metadata.

    Categories:
        Connection  — network / auth failures
        Config      — profile / configuration issues
        Validation  — input parameter errors
        Safety      — SQL safety guardrail blocks
        Query       — SQL execution errors
        Resource    — not-found errors
        Storage     — OSS / volume errors
        State       — no-op / idempotent state
        Internal    — unexpected failures
    """

    # --- Connection ---
    CONNECTION_ERROR = ErrorMeta(
        "CONNECTION_ERROR", True,
        "Check profile config or network. Retry with: hologres config",
    )
    CONNECTION_TIMEOUT = ErrorMeta(
        "CONNECTION_TIMEOUT", True,
        "Server may be busy. Retry after a short delay.",
    )

    # --- Auth & Config ---
    CONFIG_ERROR = ErrorMeta(
        "CONFIG_ERROR", False,
        "Run 'hologres config' to set up a valid profile.",
    )
    PROFILE_NOT_FOUND = ErrorMeta(
        "PROFILE_NOT_FOUND", False,
        "Specified profile does not exist. Use 'hologres config list' to see available profiles.",
    )

    # --- Input Validation ---
    INVALID_INPUT = ErrorMeta(
        "INVALID_INPUT", False,
        "Fix the input parameters and retry.",
    )
    INVALID_ARGS = ErrorMeta(
        "INVALID_ARGS", False,
        "Check command arguments. Run with --help for usage.",
    )

    # --- SQL Safety Guards ---
    WRITE_GUARD_ERROR = ErrorMeta(
        "WRITE_GUARD_ERROR", False,
        "Add --write flag to allow write operations.",
    )
    DANGEROUS_WRITE_BLOCKED = ErrorMeta(
        "DANGEROUS_WRITE_BLOCKED", False,
        "Add a WHERE clause to limit scope, or use --write --no-limit-check.",
    )
    LIMIT_REQUIRED = ErrorMeta(
        "LIMIT_REQUIRED", False,
        "Add LIMIT clause to query, or use --no-limit-check.",
    )

    # --- Query Execution ---
    QUERY_ERROR = ErrorMeta(
        "QUERY_ERROR", True,
        "Check SQL syntax or table/column names. May be transient; retry once.",
    )
    QUERY_TIMEOUT = ErrorMeta(
        "QUERY_TIMEOUT", True,
        "Query exceeded time limit. Simplify query or add filters.",
    )

    # --- Resource Not Found ---
    TABLE_NOT_FOUND = ErrorMeta(
        "TABLE_NOT_FOUND", False,
        "Table does not exist. Verify schema and table name with 'hologres table list'.",
    )
    NOT_FOUND = ErrorMeta(
        "NOT_FOUND", False,
        "Resource not found. Check the name or run the corresponding list command.",
    )
    FILE_NOT_FOUND = ErrorMeta(
        "FILE_NOT_FOUND", False,
        "File path does not exist. Verify the path.",
    )

    # --- Storage ---
    OSS_ERROR = ErrorMeta(
        "OSS_ERROR", True,
        "OSS operation failed. Check credentials and network, then retry.",
    )

    # --- State ---
    NO_CHANGES = ErrorMeta(
        "NO_CHANGES", False,
        "No modification needed. Specify at least one property to change.",
    )

    # --- Internal ---
    INTERNAL_ERROR = ErrorMeta(
        "INTERNAL_ERROR", True,
        "Unexpected error. Retry once; if persists, report a bug.",
    )


# Fast lookup: code string -> ErrorMeta
_CODE_TO_META: dict[str, ErrorMeta] = {
    member.value.code: member.value for member in ErrorCode
}


def lookup_error_meta(code: str) -> Optional[ErrorMeta]:
    """Look up ErrorMeta by code string. Returns None if not registered."""
    return _CODE_TO_META.get(code)
