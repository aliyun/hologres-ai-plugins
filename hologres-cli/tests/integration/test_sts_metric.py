"""真实 CMS 云监控 + STS 临时凭证集成测试（metric 链路接入 STS）。

验证 ``auth_mode=sts`` 时，``hologres metric list`` 走
``credentials.get_credential_client``（env STS / credentials_uri）成功访问真实 CMS，
与 SQL 链路行为一致。

环境变量（缺则 skip）：
  ALIBABA_CLOUD_ACCESS_KEY_ID / ALIBABA_CLOUD_ACCESS_KEY_SECRET / ALIBABA_CLOUD_SECURITY_TOKEN
  HOLOGRES_TEST_REGION（可选，默认 cn-hangzhou）
"""

from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from hologres_cli import credentials
from hologres_cli.commands import metric
from hologres_cli.main import cli

pytestmark = pytest.mark.integration

_STS_ENV = [
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "ALIBABA_CLOUD_SECURITY_TOKEN",
]


@pytest.fixture
def sts_metric_profile(monkeypatch):
    monkeypatch.delenv("ALIBABA_CLOUD_CREDENTIALS_URI", raising=False)
    missing = [k for k in _STS_ENV if not os.environ.get(k)]
    if missing:
        pytest.skip(f"缺少 STS 环境变量: {missing}")
    region = os.environ.get("HOLOGRES_TEST_REGION", "cn-hangzhou")
    return {
        "auth_mode": "sts",
        "region_id": region,
        "credentials_uri": "",
    }


def test_metric_list_via_sts(sts_metric_profile, mocker):
    """sts profile + env STS → 真实 metric list 返回 Hologres 指标（count > 0）。"""
    mocker.patch.object(metric, "get_current_profile", return_value=dict(sts_metric_profile))
    credentials.reset_credential_client_cache()
    runner = CliRunner()
    result = runner.invoke(cli, ["metric", "list", "--region", sts_metric_profile["region_id"]])
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert out["ok"] is True
    assert out["data"]["count"] > 0
