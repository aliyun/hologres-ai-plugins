"""Tests for logger module."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from hologres_cli.logger import (
    CONFIG_DIR,
    LOG_FILE,
    MAX_LOG_SIZE,
    _rotate_log,
    ensure_log_dir,
    log_operation,
    read_recent_logs,
    redact_sql,
)


class TestRedactSql:
    """Tests for redact_sql function."""

    def test_redact_sql_phone(self):
        """Test SQL with phone number is redacted."""
        result = redact_sql("INSERT INTO users VALUES ('13812345678')")
        assert "13812345678" not in result
        assert "'[PHONE]'" in result

    def test_redact_sql_email(self):
        """Test SQL with email is redacted."""
        result = redact_sql("INSERT INTO users VALUES ('test@example.com')")
        assert "test@example.com" not in result
        assert "'[EMAIL]'" in result

    def test_redact_sql_id_card_18(self):
        """Test SQL with 18-digit ID card is redacted."""
        result = redact_sql("INSERT INTO users VALUES ('330102199001011234')")
        assert "330102199001011234" not in result
        assert "'[ID_CARD]'" in result

    def test_redact_sql_id_card_15(self):
        """Test SQL with 15-digit ID card is redacted."""
        result = redact_sql("INSERT INTO users VALUES ('330102900101123')")
        assert "330102900101123" not in result
        assert "'[ID_CARD]'" in result

    def test_redact_sql_bank_card(self):
        """Test SQL with bank card is redacted."""
        result = redact_sql("INSERT INTO users VALUES ('6222021234567890123')")
        # 19-digit card matches bank card pattern
        assert "'[CARD]'" in result

    def test_redact_sql_password_assignment(self):
        """Test password= assignment is redacted."""
        result = redact_sql("UPDATE users SET password='secret123'")
        assert "secret123" not in result
        assert "password='[REDACTED]'" in result

    def test_redact_sql_token_assignment(self):
        """Test token= assignment is redacted."""
        result = redact_sql("UPDATE users SET token='abc123'")
        assert "abc123" not in result
        assert "token='[REDACTED]'" in result

    def test_redact_sql_no_sensitive(self):
        """Test SQL without sensitive data is unchanged."""
        sql = "SELECT * FROM users WHERE id = 1"
        result = redact_sql(sql)
        assert result == sql

    def test_redact_sql_multiple_patterns(self):
        """Test SQL with multiple sensitive patterns."""
        result = redact_sql("INSERT INTO users VALUES ('13812345678', 'test@example.com')")
        assert "'[PHONE]'" in result
        assert "'[EMAIL]'" in result

    def test_redact_sql_pwd_assignment(self):
        """Test pwd= assignment is redacted."""
        result = redact_sql("UPDATE users SET pwd='secret'")
        assert "pwd='[REDACTED]'" in result

    def test_redact_sql_secret_assignment(self):
        """Test secret= assignment is redacted."""
        result = redact_sql("UPDATE users SET secret='mysecret'")
        assert "secret='[REDACTED]'" in result

    def test_redact_sql_case_insensitive_password(self):
        """Test case insensitive password assignment."""
        result = redact_sql("UPDATE users SET PASSWORD='secret'")
        assert "'[REDACTED]'" in result


class TestEnsureLogDir:
    """Tests for ensure_log_dir function."""

    def test_ensure_log_dir_creates(self, tmp_path, monkeypatch):
        """Test directory is created when it doesn't exist."""
        log_dir = tmp_path / ".hologres"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        ensure_log_dir()
        assert log_dir.exists()

    def test_ensure_log_dir_exists(self, tmp_path, monkeypatch):
        """Test no error when directory exists."""
        log_dir = tmp_path / ".hologres"
        log_dir.mkdir()
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        # Should not raise
        ensure_log_dir()


class TestLogOperation:
    """Tests for log_operation function."""

    def test_log_operation_basic(self, tmp_path, monkeypatch):
        """Test basic operation log."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        log_operation("test_op")

        assert log_file.exists()
        content = log_file.read_text()
        entry = json.loads(content.strip())
        assert entry["operation"] == "test_op"
        assert entry["success"] is True

    def test_log_operation_with_sql(self, tmp_path, monkeypatch):
        """Test operation log with SQL."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        log_operation("sql", sql="SELECT * FROM users")

        content = log_file.read_text()
        entry = json.loads(content.strip())
        assert entry["sql"] == "SELECT * FROM users"

    def test_log_operation_with_sql_redaction(self, tmp_path, monkeypatch):
        """Test SQL is redacted in log."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        log_operation("sql", sql="INSERT INTO t VALUES ('13812345678')")

        content = log_file.read_text()
        entry = json.loads(content.strip())
        assert "13812345678" not in entry["sql"]
        assert "'[PHONE]'" in entry["sql"]

    def test_log_operation_with_dsn(self, tmp_path, monkeypatch):
        """Test operation log with DSN."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        log_operation("sql", dsn_masked="hologres://user:***@host/db")

        content = log_file.read_text()
        entry = json.loads(content.strip())
        assert entry["dsn"] == "hologres://user:***@host/db"

    def test_log_operation_with_error(self, tmp_path, monkeypatch):
        """Test operation log with error info."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        log_operation("sql", success=False, error_code="QUERY_ERROR", error_message="Syntax error")

        content = log_file.read_text()
        entry = json.loads(content.strip())
        assert entry["success"] is False
        assert entry["error_code"] == "QUERY_ERROR"
        assert entry["error_message"] == "Syntax error"

    def test_log_operation_with_duration(self, tmp_path, monkeypatch):
        """Test operation log with duration."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        log_operation("sql", duration_ms=123.456)

        content = log_file.read_text()
        entry = json.loads(content.strip())
        assert entry["duration_ms"] == 123.46  # Rounded to 2 decimal places

    def test_log_operation_with_extra(self, tmp_path, monkeypatch):
        """Test operation log with extra fields."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        log_operation("sql", extra={"table": "users", "rows_affected": 5})

        content = log_file.read_text()
        entry = json.loads(content.strip())
        assert entry["extra"]["table"] == "users"
        assert entry["extra"]["rows_affected"] == 5

    def test_log_operation_creates_dir(self, tmp_path, monkeypatch):
        """Test log directory is created if it doesn't exist."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        assert not log_dir.exists()
        log_operation("test")
        assert log_dir.exists()

    def test_log_operation_exception_handling(self, tmp_path, monkeypatch):
        """Test log_operation doesn't raise on file write error."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        # Make the path a directory to cause write error
        log_dir.mkdir()
        log_file.mkdir()

        # Should not raise
        log_operation("test")

    def test_log_operation_row_count(self, tmp_path, monkeypatch):
        """Test operation log with row count."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.CONFIG_DIR", log_dir)
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        log_operation("sql", row_count=100)

        content = log_file.read_text()
        entry = json.loads(content.strip())
        assert entry["row_count"] == 100


class TestRotateLog:
    """Tests for _rotate_log function."""

    def test_rotate_log(self, tmp_path, monkeypatch):
        """Test log rotation."""
        log_dir = tmp_path / ".hologres"
        log_dir.mkdir()
        log_file = log_dir / "sql-history.jsonl"
        log_file.write_text('{"test": "data"}\n')
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        _rotate_log()

        assert not log_file.exists()
        backup = log_dir / "sql-history.jsonl.old"
        assert backup.exists()
        assert backup.read_text() == '{"test": "data"}\n'

    def test_rotate_log_no_existing_backup(self, tmp_path, monkeypatch):
        """Test rotation when no existing backup."""
        log_dir = tmp_path / ".hologres"
        log_dir.mkdir()
        log_file = log_dir / "sql-history.jsonl"
        log_file.write_text('{"test": "data"}\n')
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        _rotate_log()

        backup = log_dir / "sql-history.jsonl.old"
        assert backup.exists()

    def test_rotate_log_replaces_existing_backup(self, tmp_path, monkeypatch):
        """Test rotation replaces existing backup."""
        log_dir = tmp_path / ".hologres"
        log_dir.mkdir()
        log_file = log_dir / "sql-history.jsonl"
        backup = log_dir / "sql-history.jsonl.old"

        # Create existing backup
        backup.write_text('{"old": "backup"}\n')
        log_file.write_text('{"test": "new"}\n')
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        _rotate_log()

        assert backup.read_text() == '{"test": "new"}\n'

    def test_rotate_log_exception_handling(self, tmp_path, monkeypatch):
        """Test rotation handles exceptions gracefully."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)
        # Don't create directory or file - rotation should handle gracefully

        # Should not raise
        _rotate_log()


class TestReadRecentLogs:
    """Tests for read_recent_logs function."""

    def test_read_recent_logs_empty(self, tmp_path, monkeypatch):
        """Test empty log file returns empty list."""
        log_dir = tmp_path / ".hologres"
        log_dir.mkdir()
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        result = read_recent_logs()
        assert result == []

    def test_read_recent_logs_no_file(self, tmp_path, monkeypatch):
        """Test non-existent log file returns empty list."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        result = read_recent_logs()
        assert result == []

    def test_read_recent_logs_with_data(self, tmp_path, monkeypatch):
        """Test reading logs with data."""
        log_dir = tmp_path / ".hologres"
        log_dir.mkdir()
        log_file = log_dir / "sql-history.jsonl"
        log_file.write_text('{"id": 1}\n{"id": 2}\n{"id": 3}\n')
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        result = read_recent_logs()
        assert len(result) == 3
        assert result[0]["id"] == 1

    def test_read_recent_logs_count_limit(self, tmp_path, monkeypatch):
        """Test count parameter limits results."""
        log_dir = tmp_path / ".hologres"
        log_dir.mkdir()
        log_file = log_dir / "sql-history.jsonl"
        log_file.write_text('{"id": 1}\n{"id": 2}\n{"id": 3}\n')
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        result = read_recent_logs(count=2)
        assert len(result) == 2
        assert result[0]["id"] == 2
        assert result[1]["id"] == 3

    def test_read_recent_logs_invalid_json(self, tmp_path, monkeypatch):
        """Test invalid JSON lines are skipped."""
        log_dir = tmp_path / ".hologres"
        log_dir.mkdir()
        log_file = log_dir / "sql-history.jsonl"
        log_file.write_text('{"id": 1}\ninvalid json\n{"id": 2}\n')
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)

        result = read_recent_logs()
        assert len(result) == 2
        assert result[0]["id"] == 1
        assert result[1]["id"] == 2

    def test_read_recent_logs_exception_handling(self, tmp_path, monkeypatch):
        """Test exception handling returns empty list."""
        log_dir = tmp_path / ".hologres"
        log_file = log_dir / "sql-history.jsonl"
        monkeypatch.setattr("hologres_cli.logger.LOG_FILE", log_file)
        # Don't create directory

        result = read_recent_logs()
        assert result == []
