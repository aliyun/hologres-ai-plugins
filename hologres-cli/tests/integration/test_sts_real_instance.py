"""真实 STS 三元组连真实 Hologres 实例的集成测试。

三元组与实例信息都从环境变量读（勿硬编码、勿提交）：

  STS 三元组（标准阿里云环境变量，默认链第 1 步识别）：
    ALIBABA_CLOUD_ACCESS_KEY_ID
    ALIBABA_CLOUD_ACCESS_KEY_SECRET
    ALIBABA_CLOUD_SECURITY_TOKEN

  实例信息：
    HOLOGRES_TEST_REGION        e.g. cn-hangzhou
    HOLOGRES_TEST_INSTANCE      e.g. hgprecn-cn-xxx
    HOLOGRES_TEST_DATABASE      e.g. mydb
    HOLOGRES_TEST_NETTYPE       可选，默认 internet
    HOLOGRES_TEST_MODE          可选，默认 jdbc（也可 api / auto）

跑（缺环境变量自动 skip）::

    pytest tests/integration/test_sts_real_instance.py -v -s
"""

from __future__ import annotations

import os

import pytest

from hologres_cli import connection, credentials
from hologres_cli.connection import get_connection

pytestmark = pytest.mark.integration

_STS_ENV = [
    "ALIBABA_CLOUD_ACCESS_KEY_ID",
    "ALIBABA_CLOUD_ACCESS_KEY_SECRET",
    "ALIBABA_CLOUD_SECURITY_TOKEN",
]
_INSTANCE_ENV = ["HOLOGRES_TEST_REGION", "HOLOGRES_TEST_INSTANCE", "HOLOGRES_TEST_DATABASE"]


@pytest.fixture
def sts_env_only(monkeypatch):
    """仅要求 STS 三元组环境变量（不连实例）。"""
    missing = [k for k in _STS_ENV if not os.environ.get(k)]
    if missing:
        pytest.skip(f"缺少 STS 环境变量: {missing}")


@pytest.fixture
def real_sts_profile(sts_env_only):
    """实例信息 + 三元组齐全的 sts profile。"""
    missing = [k for k in _INSTANCE_ENV if not os.environ.get(k)]
    if missing:
        pytest.skip(f"缺少实例环境变量: {missing}")
    return {
        "auth_mode": "sts",
        "region_id": os.environ["HOLOGRES_TEST_REGION"],
        "instance_id": os.environ["HOLOGRES_TEST_INSTANCE"],
        "database": os.environ["HOLOGRES_TEST_DATABASE"],
        "nettype": os.environ.get("HOLOGRES_TEST_NETTYPE", "internet"),
        "connection_mode": os.environ.get("HOLOGRES_TEST_MODE", "jdbc"),
        "credentials_uri": "",  # 标准三元组走 ALIBABA_CLOUD_* 环境变量
    }


def test_resolve_sts_from_env(sts_env_only):
    """验证默认链从标准 STS 环境变量解析出三元组（不连实例）。"""
    credentials.reset_credential_client_cache()
    out = credentials.resolve_sts_credentials({"credentials_uri": ""})
    assert out["access_key_id"].startswith("STS.")
    assert out["access_key_secret"]
    assert out["security_token"]


def test_select_one_via_sts(real_sts_profile, mocker):
    """端到端：sts 三元组 → get_connection → SELECT 1 连真实实例。"""
    mocker.patch.object(connection, "_resolve_profile_dict", return_value=dict(real_sts_profile))
    credentials.reset_credential_client_cache()
    conn = get_connection()
    try:
        rows = conn.execute("SELECT 1 AS n")
        assert rows and rows[0]["n"] == 1
    finally:
        conn.close()
