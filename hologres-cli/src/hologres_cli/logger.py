"""Audit logging for Hologres CLI."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

CONFIG_DIR = Path.home() / ".hologres"
LOG_FILE = CONFIG_DIR / "sql-history.jsonl"
MAX_LOG_SIZE = 10 * 1024 * 1024

SENSITIVE_LITERAL_PATTERNS = [
    (re.compile(r"'1[3-9]\d{9}'"), "'[PHONE]'"),
    (re.compile(r"'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'"), "'[EMAIL]'"),
    (re.compile(r"'\d{17}[\dXx]'"), "'[ID_CARD]'"),
    (re.compile(r"'\d{15}'"), "'[ID_CARD]'"),
    (re.compile(r"'\d{16,19}'"), "'[CARD]'"),
    (re.compile(r"(password|pwd|passwd|secret|token)\s*=\s*'[^']*'", re.IGNORECASE), r"\1='[REDACTED]'"),
]


def ensure_log_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def redact_sql(sql: str) -> str:
    redacted = sql
    for pattern, replacement in SENSITIVE_LITERAL_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def log_operation(
    operation: str,
    sql: Optional[str] = None,
    dsn_masked: Optional[str] = None,
    success: bool = True,
    row_count: Optional[int] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
    duration_ms: Optional[float] = None,
    extra: Optional[dict[str, Any]] = None,
) -> None:
    try:
        ensure_log_dir()
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_SIZE:
            _rotate_log()
        entry: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "operation": operation,
            "success": success,
        }
        if sql:
            entry["sql"] = redact_sql(sql)
        if dsn_masked:
            entry["dsn"] = dsn_masked
        if row_count is not None:
            entry["row_count"] = row_count
        if error_code:
            entry["error_code"] = error_code
        if error_message:
            entry["error_message"] = error_message
        if duration_ms is not None:
            entry["duration_ms"] = round(duration_ms, 2)
        if extra:
            entry["extra"] = extra
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _rotate_log() -> None:
    try:
        backup = LOG_FILE.with_suffix(".jsonl.old")
        if backup.exists():
            backup.unlink()
        LOG_FILE.rename(backup)
    except Exception:
        try:
            LOG_FILE.write_text("")
        except Exception:
            pass


def read_recent_logs(count: int = 100) -> list[dict[str, Any]]:
    if not LOG_FILE.exists():
        return []
    try:
        entries = []
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries[-count:] if len(entries) > count else entries
    except Exception:
        return []
