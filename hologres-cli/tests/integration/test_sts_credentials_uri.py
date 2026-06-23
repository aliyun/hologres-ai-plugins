"""Integration test: STS 临时凭证从 credentials_uri 端点真实拉取（功能 2）。

验证 alibabacloud-credentials 的 credentials_uri provider 端到端链路：
起本地 HTTP 返回 STS JSON → resolve_sts_credentials 解析出三元组。

标 ``@pytest.mark.integration``，``pytest -m unit`` 不会跑（默认跳过）；
手动触发：``pytest tests/integration/test_sts_credentials_uri.py -v``。
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import pytest

from hologres_cli import credentials

pytestmark = pytest.mark.integration


class _StsHandler(BaseHTTPRequestHandler):
    """返回一份远期过期的 STS JSON（与阿里云 credentials_uri 约定的驼峰字段一致）。"""

    response: dict[str, Any] = {
        "Code": "Success",
        "AccessKeyId": "STS.INTEG_AK",
        "AccessKeySecret": "integ_sk",
        "SecurityToken": "integ_token",
        "Expiration": "2099-01-01T00:00:00Z",
    }

    def do_GET(self) -> None:
        body = json.dumps(self.response).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:  # 静默测试日志
        pass


@pytest.fixture
def sts_http_server():
    server = HTTPServer(("127.0.0.1", 0), _StsHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{port}/sts"
    server.shutdown()
    server.server_close()


def test_credentials_uri_fetch_and_parse(sts_http_server):
    """显式 credentials_uri → provider HTTP GET → 解析出三元组。"""
    credentials.reset_credential_client_cache()
    out = credentials.resolve_sts_credentials({"credentials_uri": sts_http_server})
    assert out["access_key_id"] == "STS.INTEG_AK"
    assert out["access_key_secret"] == "integ_sk"
    assert out["security_token"] == "integ_token"
