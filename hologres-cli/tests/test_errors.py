"""Tests for unified error code registry and AI-parseable error output."""

from __future__ import annotations

import json

import pytest

from hologres_cli.errors import ErrorCode, ErrorMeta, lookup_error_meta
from hologres_cli.output import (
    connection_error,
    dangerous_write_error,
    error,
    limit_required_error,
    query_error,
    write_guard_error,
)


class TestErrorCodeRegistry:
    """Tests for ErrorCode enum and metadata."""

    def test_all_codes_are_unique(self):
        """All error code strings must be unique."""
        codes = [member.value.code for member in ErrorCode]
        assert len(codes) == len(set(codes)), f"Duplicate codes found: {codes}"

    def test_all_members_have_error_meta(self):
        """Each enum member value must be an ErrorMeta tuple."""
        for member in ErrorCode:
            assert isinstance(member.value, ErrorMeta)
            assert isinstance(member.value.code, str)
            assert isinstance(member.value.retryable, bool)
            assert isinstance(member.value.hint, str)
            assert len(member.value.hint) > 0, f"{member.name} has empty hint"

    def test_code_string_matches_enum_name(self):
        """The code string in ErrorMeta should match the enum member name."""
        for member in ErrorCode:
            assert member.value.code == member.name

    def test_retryable_codes(self):
        """Known retryable codes should be marked as retryable."""
        retryable_codes = [
            ErrorCode.CONNECTION_ERROR,
            ErrorCode.CONNECTION_TIMEOUT,
            ErrorCode.QUERY_ERROR,
            ErrorCode.QUERY_TIMEOUT,
            ErrorCode.OSS_ERROR,
            ErrorCode.INTERNAL_ERROR,
        ]
        for code in retryable_codes:
            assert code.value.retryable is True, f"{code.name} should be retryable"

    def test_non_retryable_codes(self):
        """Known non-retryable codes should NOT be marked as retryable."""
        non_retryable_codes = [
            ErrorCode.INVALID_INPUT,
            ErrorCode.INVALID_ARGS,
            ErrorCode.WRITE_GUARD_ERROR,
            ErrorCode.DANGEROUS_WRITE_BLOCKED,
            ErrorCode.LIMIT_REQUIRED,
            ErrorCode.TABLE_NOT_FOUND,
            ErrorCode.NOT_FOUND,
            ErrorCode.FILE_NOT_FOUND,
            ErrorCode.NO_CHANGES,
            ErrorCode.CONFIG_ERROR,
            ErrorCode.PROFILE_NOT_FOUND,
        ]
        for code in non_retryable_codes:
            assert code.value.retryable is False, f"{code.name} should NOT be retryable"


class TestLookupErrorMeta:
    """Tests for lookup_error_meta function."""

    def test_lookup_known_code(self):
        """Known code strings should resolve to their ErrorMeta."""
        meta = lookup_error_meta("CONNECTION_ERROR")
        assert meta is not None
        assert meta.code == "CONNECTION_ERROR"
        assert meta.retryable is True
        assert "config" in meta.hint.lower() or "network" in meta.hint.lower()

    def test_lookup_all_registered_codes(self):
        """All registered codes should be findable via lookup."""
        for member in ErrorCode:
            meta = lookup_error_meta(member.value.code)
            assert meta is not None
            assert meta == member.value

    def test_lookup_unknown_code_returns_none(self):
        """Unknown code strings should return None."""
        assert lookup_error_meta("TOTALLY_UNKNOWN") is None
        assert lookup_error_meta("") is None


class TestErrorOutputFormat:
    """Tests for error() function output with retryable/hint fields."""

    def test_error_with_enum(self):
        """Passing ErrorCode enum should produce full metadata."""
        result = error(ErrorCode.CONNECTION_ERROR, "Connection refused")
        data = json.loads(result)
        assert data["ok"] is False
        assert data["error"]["code"] == "CONNECTION_ERROR"
        assert data["error"]["message"] == "Connection refused"
        assert data["error"]["retryable"] is True
        assert len(data["error"]["hint"]) > 0

    def test_error_with_string_known_code(self):
        """Passing a known string code should auto-resolve metadata."""
        result = error("QUERY_ERROR", "Syntax error near 'FROM'")
        data = json.loads(result)
        assert data["ok"] is False
        assert data["error"]["code"] == "QUERY_ERROR"
        assert data["error"]["message"] == "Syntax error near 'FROM'"
        assert data["error"]["retryable"] is True
        assert len(data["error"]["hint"]) > 0

    def test_error_with_string_unknown_code(self):
        """Passing an unknown string code should still work with defaults."""
        result = error("CUSTOM_ERROR", "Something custom")
        data = json.loads(result)
        assert data["ok"] is False
        assert data["error"]["code"] == "CUSTOM_ERROR"
        assert data["error"]["message"] == "Something custom"
        assert data["error"]["retryable"] is False
        assert data["error"]["hint"] == ""

    def test_error_with_details(self):
        """Details dict should be included when provided."""
        result = error(ErrorCode.QUERY_ERROR, "Failed", details={"sql": "SELECT 1"})
        data = json.loads(result)
        assert data["error"]["details"] == {"sql": "SELECT 1"}

    def test_error_without_details(self):
        """No 'details' key when not provided."""
        result = error(ErrorCode.QUERY_ERROR, "Failed")
        data = json.loads(result)
        assert "details" not in data["error"]

    def test_connection_error_helper(self):
        """connection_error() helper should use CONNECTION_ERROR enum."""
        result = connection_error("Refused")
        data = json.loads(result)
        assert data["error"]["code"] == "CONNECTION_ERROR"
        assert data["error"]["retryable"] is True
        assert len(data["error"]["hint"]) > 0

    def test_query_error_helper(self):
        """query_error() helper should use QUERY_ERROR enum."""
        result = query_error("Bad SQL")
        data = json.loads(result)
        assert data["error"]["code"] == "QUERY_ERROR"
        assert data["error"]["retryable"] is True

    def test_limit_required_error_helper(self):
        """limit_required_error() should use LIMIT_REQUIRED enum."""
        result = limit_required_error()
        data = json.loads(result)
        assert data["error"]["code"] == "LIMIT_REQUIRED"
        assert data["error"]["retryable"] is False
        assert "LIMIT" in data["error"]["hint"] or "limit" in data["error"]["hint"]

    def test_write_guard_error_helper(self):
        """write_guard_error() should use WRITE_GUARD_ERROR enum."""
        result = write_guard_error()
        data = json.loads(result)
        assert data["error"]["code"] == "WRITE_GUARD_ERROR"
        assert data["error"]["retryable"] is False
        assert "--write" in data["error"]["hint"]

    def test_dangerous_write_error_helper(self):
        """dangerous_write_error() should use DANGEROUS_WRITE_BLOCKED enum."""
        result = dangerous_write_error("DELETE")
        data = json.loads(result)
        assert data["error"]["code"] == "DANGEROUS_WRITE_BLOCKED"
        assert data["error"]["retryable"] is False
        assert "WHERE" in data["error"]["hint"]

    def test_output_is_valid_json(self):
        """All error output must be valid JSON."""
        for member in ErrorCode:
            result = error(member, "Test message")
            data = json.loads(result)  # Should not raise
            assert isinstance(data, dict)
            assert "ok" in data
            assert "error" in data
