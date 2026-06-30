"""Integration tests for CloudMonitor CMS metrics via real OpenAPI (acs_hologres).

These tests make REAL calls to Alibaba Cloud CloudMonitor — no mocks.

``metric`` commands read the *current* profile via ``get_current_profile()``
(they do not honor the root ``--profile`` flag), so the runbook must set the
test profile as the current profile. The ``api_test_profile`` fixture gates the
skip (it validates that AK/SK + region_id + instance_id are present).

Profile fields used:
- ``region_id``            — CMS region (metrics.<region>.aliyuncs.com)
- ``access_key_id``/``_secret`` — AK auth (non-sts path in metric._resolve_ak_credential_client)
- ``instance_id``          -- injected into metric dimensions for query/latest
"""

from __future__ import annotations

import json
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


def _pick_instance_metric(region_id: str) -> str | None:
    """Discover a real instance-level metric name from ``metric list`` output.

    Returns the first metric whose dimensions reference ``instanceId`` (or whose
    name carries a Hologres product prefix), so we never hardcode a metric that
    may not exist for this instance type.
    """
    out = _run(["metric", "list", "--region", region_id])
    assert out["ok"] is True, f"metric list failed: {out}"
    for row in out["data"].get("rows", []):
        name = row.get("metric_name", "")
        dims = str(row.get("dimensions", ""))
        if "instanceId" in dims or name.startswith(
            ("standard_", "serverless_", "warehouse_", "follower_", "shared_")
        ):
            return name
    return None


def test_metric_list(api_test_profile: str):
    """``metric list`` returns the acs_hologres metric catalog."""
    prof = get_profile(api_test_profile)
    out = _run(["metric", "list", "--region", prof["region_id"]])
    assert out["ok"] is True
    assert out["data"]["count"] > 0
    assert "metric_name" in out["data"]["rows"][0]


def test_metric_query(api_test_profile: str):
    """``metric query`` issues a real DescribeMetricList call (default last 1h)."""
    prof = get_profile(api_test_profile)
    metric = _pick_instance_metric(prof["region_id"])
    if not metric:
        pytest.skip("No instance-level metric discovered from `metric list`")

    out = _run([
        "metric", "query", metric,
        "--instance-id", prof["instance_id"],
        "--region", prof["region_id"],
    ])
    assert out["ok"] is True
    # 0 datapoints is acceptable (metric may have no data in the window); the
    # real call succeeding is the coverage signal.


def test_metric_latest(api_test_profile: str):
    """``metric latest`` issues a real DescribeMetricLast call."""
    prof = get_profile(api_test_profile)
    metric = _pick_instance_metric(prof["region_id"])
    if not metric:
        pytest.skip("No instance-level metric discovered from `metric list`")

    out = _run([
        "metric", "latest", metric,
        "--instance-id", prof["instance_id"],
        "--region", prof["region_id"],
    ])
    assert out["ok"] is True
