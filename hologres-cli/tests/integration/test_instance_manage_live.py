"""Integration tests for the Hologram instance-management OpenAPI (real calls).

These tests make REAL calls to the Hologram OpenAPI — no mocks. They cover the
``instance-manage`` command group, which is independent of ``connection_mode``
(it builds its own Hologram client from the profile's AK/SK + region_id).

``instance-manage`` honors the root ``--profile`` flag (via _resolve_profile),
which must precede the command group (it is a root-group option, not a
subcommand option): ``cli --profile <name> instance-manage <sub>``.

Safety note: ``disable-execute-statement`` is the only command with a lasting
side effect — it turns OFF the ExecuteStatement feature that the API-mode SQL
tests depend on. ``test_disable_then_reenable`` re-enables in a ``finally``,
and a module-scoped autouse fixture re-enables again at teardown so the
instance can never be left disabled even if a test crashes mid-flight.
"""

from __future__ import annotations

import json
import time
from typing import Any

import pytest
from click.testing import CliRunner

from hologres_cli.config_store import get_profile
from hologres_cli.main import cli

pytestmark = pytest.mark.integration


def _run(args: list[str]) -> dict[str, Any]:
    """Invoke the CLI and return the parsed JSON envelope; assert exit 0."""
    runner = CliRunner()
    result = runner.invoke(cli, args)
    assert result.exit_code == 0, f"CLI exited {result.exit_code}: {result.output}"
    return json.loads(result.output)


def _im(profile_name: str, *sub: str) -> list[str]:
    """Build args with the root --profile flag BEFORE the instance-manage group."""
    return ["--profile", profile_name, "instance-manage", *sub]


def _enabled_state(data: Any) -> bool | None:
    """Interpret a GetExecuteStatementEnabled body as a bool, or None if unknown shape.

    The Hologram response wraps the value in a ``data`` field
    (``GetExecuteStatementEnabledResponseBody`` = {data, success, ...}); tolerate
    both top-level and ``data``-nested boolean shapes.
    """
    if isinstance(data, bool):
        return data
    if isinstance(data, dict):
        for key in (
            "Enabled", "enabled", "Enable", "enable",
            "ExecuteStatementEnabled", "executeStatementEnabled",
        ):
            if key in data:
                return bool(data[key])
        inner = data.get("data")
        if isinstance(inner, bool):
            return inner
        if isinstance(inner, dict):
            for key in ("Enabled", "enabled", "Enable", "enable"):
                if key in inner:
                    return bool(inner[key])
    return None


def _get_enabled(profile_name: str) -> Any:
    out = _run(_im(profile_name, "get-execute-statement-enabled"))
    assert out["ok"] is True, f"get-execute-statement-enabled failed: {out}"
    return out["data"]


@pytest.fixture(scope="module", autouse=True)
def _ensure_enabled_at_teardown(api_test_profile: str):
    """Safety net: guarantee ExecuteStatement is (re-)enabled when this module
    finishes, protecting the API-mode SQL tests from a half-disabled instance."""
    yield
    try:
        _run(_im(api_test_profile, "enable-execute-statement"))
    except Exception:
        # Best-effort restore; do not let teardown mask the real test failure.
        pass


class TestInstanceManageReadOnly:
    """Read-only Hologram OpenAPI calls (list / get / get-enabled)."""

    def test_list(self, api_test_profile: str):
        """``instance-manage list`` issues a real ListInstances call.

        The returned set may be empty for some account/region scopings even when
        ``get`` can reach the instance, so we only assert the call succeeds and
        the envelope is well-formed.
        """
        out = _run(_im(api_test_profile, "list"))
        assert out["ok"] is True
        assert "data" in out

    def test_get(self, api_test_profile: str):
        prof = get_profile(api_test_profile)
        out = _run(_im(api_test_profile, "get"))
        assert out["ok"] is True
        # Body shape is the full instance detail; the target id must appear.
        assert prof["instance_id"] in json.dumps(out["data"])

    def test_get_execute_statement_enabled(self, api_test_profile: str):
        data = _get_enabled(api_test_profile)
        assert data is not None


def test_enable_is_idempotent(api_test_profile: str):
    """Enabling an already-enabled instance is a no-op and returns ok."""
    out = _run(_im(api_test_profile, "enable-execute-statement"))
    assert out["ok"] is True, f"enable-execute-statement failed: {out}"
    # State should be enabled afterwards (best-effort; tolerant of unknown shape).
    state = _enabled_state(_get_enabled(api_test_profile))
    if state is False:
        pytest.fail("ExecuteStatement reported disabled right after enable")


def test_disable_then_reenable(api_test_profile: str):
    """Real disable call, then unconditional re-enable in finally."""
    disabled = _run(_im(api_test_profile, "disable-execute-statement"))
    assert disabled["ok"] is True, f"disable-execute-statement failed: {disabled}"

    try:
        # Best-effort: do not hard-assert the disabled boolean — Hologres may
        # have propagation delay. We only exercise the real get-enabled call.
        _get_enabled(api_test_profile)
    finally:
        # Unconditional restore, then poll for the enabled state.
        enabled = _run(_im(api_test_profile, "enable-execute-statement"))
        assert enabled["ok"] is True, f"re-enable failed: {enabled}"

        final = None
        for _ in range(5):
            final = _enabled_state(_get_enabled(api_test_profile))
            if final is True:
                break
            time.sleep(2)
        if final is False:
            pytest.fail("ExecuteStatement remained disabled after re-enable")
        # final is True (confirmed) or None (unknown shape) → pass
