"""Sensitive field masking for Hologres CLI."""

from __future__ import annotations

import re
from typing import Any, Callable, Optional

SENSITIVE_PATTERNS: list[tuple[re.Pattern, Callable[[Any], str]]] = []


def _register_pattern(pattern: str, mask_func: Callable[[Any], str]) -> None:
    SENSITIVE_PATTERNS.append((re.compile(pattern, re.IGNORECASE), mask_func))


def _mask_phone(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 7:
        return digits[:3] + "*" * (len(digits) - 7) + digits[-4:]
    return "*" * len(s)


def _mask_email(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    if "@" in s:
        local, domain = s.rsplit("@", 1)
        if local:
            return local[0] + "***@" + domain
    return "***"


def _mask_password(value: Any) -> str:
    return "********"


def _mask_id_card(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    if len(s) >= 7:
        return s[:3] + "*" * (len(s) - 7) + s[-4:]
    return "*" * len(s)


def _mask_bank_card(value: Any) -> str:
    if value is None:
        return ""
    s = str(value)
    digits = re.sub(r"\D", "", s)
    if len(digits) >= 4:
        return "*" * (len(digits) - 4) + digits[-4:]
    return "*" * len(s)


_register_pattern(r"(phone|mobile|tel|cellular)", _mask_phone)
_register_pattern(r"(email|mail|e_mail)", _mask_email)
_register_pattern(r"(password|pwd|passwd|secret|token|api_key|apikey)", _mask_password)
_register_pattern(r"(id_card|idcard|id_number|identity|ssn)", _mask_id_card)
_register_pattern(r"(bank_card|bankcard|credit_card|creditcard|card_number|card_no)", _mask_bank_card)


def get_mask_function(column_name: str) -> Optional[Callable[[Any], str]]:
    for pattern, mask_func in SENSITIVE_PATTERNS:
        if pattern.search(column_name):
            return mask_func
    return None


def mask_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Mask sensitive fields in multiple rows."""
    if not rows:
        return rows
    columns = list(rows[0].keys())
    mask_funcs = {col: get_mask_function(col) for col in columns}
    sensitive_cols = {col for col, func in mask_funcs.items() if func is not None}
    if not sensitive_cols:
        return rows
    result = []
    for row in rows:
        masked_row = {}
        for col, val in row.items():
            func = mask_funcs.get(col)
            if func and val is not None:
                masked_row[col] = func(val)
            else:
                masked_row[col] = val
        result.append(masked_row)
    return result
