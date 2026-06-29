"""Tests for credentials module (STS 临时凭证，功能 1 + 功能 2)."""

from __future__ import annotations

import pytest

from hologres_cli import credentials
from hologres_cli.errors import ErrorCode

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fake SDK helpers —— 通过 patch _import_credentials_sdk 注入假实现，
# 不触碰真实 alibabacloud-credentials 包。
# ---------------------------------------------------------------------------

class FakeCredential:
    def __init__(self, ak="STS.AKID", sk="sk", token="tok"):
        self._ak, self._sk, self._tok = ak, sk, token

    def get_access_key_id(self):
        return self._ak

    def get_access_key_secret(self):
        return self._sk

    def get_security_token(self):
        return self._tok


class FakeCredentialClient:
    """记录构造 config + get_credential 调用次数，可控制返回/抛异常。"""
    last = None

    def __init__(self, config=None):
        self.config = config
        self.calls = 0
        self._cred = FakeCredential()
        self._exc = None
        FakeCredentialClient.last = self

    def get_credential(self):
        self.calls += 1
        if self._exc:
            raise self._exc
        return self._cred


@pytest.fixture
def fake_sdk(mocker):
    """Patch _import_credentials_sdk 返回假类。"""
    mocker.patch.object(
        credentials, "_import_credentials_sdk",
        return_value=(FakeCredentialClient, dict),
    )
    FakeCredentialClient.last = None
    return FakeCredentialClient


@pytest.fixture(autouse=True)
def _isolate_cache(monkeypatch):
    """每用例前后清空单例缓存 + 删环境变量，防 mock/状态泄漏。"""
    monkeypatch.delenv("ALIBABA_CLOUD_CREDENTIALS_URI", raising=False)
    credentials.reset_credential_client_cache()
    yield
    credentials.reset_credential_client_cache()


# ---------------------------------------------------------------------------
# L1: get_credential_client（单例 + provider 构造）
# ---------------------------------------------------------------------------

class TestGetCredentialClient:
    def test_default_chain_singleton(self, fake_sdk):
        c1 = credentials.get_credential_client({"credentials_uri": ""})
        c2 = credentials.get_credential_client({"credentials_uri": ""})
        assert c1 is c2

    def test_explicit_uri_singleton(self, fake_sdk):
        c1 = credentials.get_credential_client({"credentials_uri": "http://a"})
        c2 = credentials.get_credential_client({"credentials_uri": "http://a"})
        assert c1 is c2

    def test_different_uri_different_instance(self, fake_sdk):
        c1 = credentials.get_credential_client({"credentials_uri": "http://a"})
        c2 = credentials.get_credential_client({"credentials_uri": "http://b"})
        assert c1 is not c2

    def test_default_vs_uri_different_instance(self, fake_sdk):
        c1 = credentials.get_credential_client({"credentials_uri": ""})
        c2 = credentials.get_credential_client({"credentials_uri": "http://a"})
        assert c1 is not c2

    def test_explicit_uri_passes_credentials_uri_config(self, fake_sdk):
        credentials.get_credential_client({"credentials_uri": "http://x"})
        assert FakeCredentialClient.last.config == {
            "type": "credentials_uri", "credentials_uri": "http://x",
        }

    def test_default_chain_no_config_arg(self, fake_sdk):
        credentials.get_credential_client({"credentials_uri": ""})
        assert FakeCredentialClient.last.config is None


class TestGetCredentialClientErrors:
    def test_explicit_uri_init_failure_maps_invalid(self, mocker):
        class BoomClient:
            def __init__(self, config=None):
                raise RuntimeError("bad uri")
        mocker.patch.object(credentials, "_import_credentials_sdk",
                            return_value=(BoomClient, dict))
        with pytest.raises(credentials.CredentialsError) as exc:
            credentials.get_credential_client({"credentials_uri": "http://x"})
        assert exc.value.code == ErrorCode.CREDENTIALS_URI_INVALID.value.code
        assert exc.value.error_code.value.retryable is False

    def test_default_chain_init_failure_maps_provider_failed(self, mocker):
        class BoomClient:
            def __init__(self, config=None):
                raise RuntimeError("no ecs metadata")
        mocker.patch.object(credentials, "_import_credentials_sdk",
                            return_value=(BoomClient, dict))
        with pytest.raises(credentials.CredentialsError) as exc:
            credentials.get_credential_client({"credentials_uri": ""})
        assert exc.value.code == ErrorCode.CREDENTIALS_PROVIDER_INIT_FAILED.value.code
        assert exc.value.error_code.value.retryable is True


# ---------------------------------------------------------------------------
# L1: resolve_sts_credentials（三元组 + 错误映射 + 轮转半验证）
# ---------------------------------------------------------------------------

class TestResolveStsCredentials:
    def test_returns_three_fields(self, fake_sdk):
        out = credentials.resolve_sts_credentials({"credentials_uri": ""})
        assert set(out) == {"access_key_id", "access_key_secret", "security_token"}
        assert out["access_key_id"] == "STS.AKID"
        assert out["security_token"] == "tok"

    def test_get_credential_failure_maps_fetch_error(self, fake_sdk):
        client = credentials.get_credential_client({"credentials_uri": ""})
        client._exc = RuntimeError("network down")
        with pytest.raises(credentials.CredentialsError) as exc:
            credentials.resolve_sts_credentials({"credentials_uri": ""})
        assert exc.value.code == ErrorCode.STS_FETCH_ERROR.value.code
        assert exc.value.error_code.value.retryable is True

    def test_missing_token_maps_incomplete(self, fake_sdk):
        client = credentials.get_credential_client({"credentials_uri": ""})
        client._cred = FakeCredential(token="")
        with pytest.raises(credentials.CredentialsError) as exc:
            credentials.resolve_sts_credentials({"credentials_uri": ""})
        assert exc.value.code == ErrorCode.STS_TOKEN_INCOMPLETE.value.code

    def test_each_resolve_calls_get_credential(self, fake_sdk):
        """轮转前提：每次 resolve 都 get_credential() 现拉最新三元组，不缓存到磁盘。"""
        credentials.resolve_sts_credentials({"credentials_uri": ""})
        assert FakeCredentialClient.last.calls == 1
        credentials.resolve_sts_credentials({"credentials_uri": ""})
        assert FakeCredentialClient.last.calls == 2

    def test_singleton_no_duplicate_client(self, fake_sdk):
        """多次 resolve 只构造 1 个 client 实例 → SDK 刷新缓存可生效。"""
        credentials.resolve_sts_credentials({"credentials_uri": ""})
        first = FakeCredentialClient.last
        credentials.resolve_sts_credentials({"credentials_uri": ""})
        assert FakeCredentialClient.last is first


# ---------------------------------------------------------------------------
# L0: sts_prerequisites_met（纯静态判断）
# ---------------------------------------------------------------------------

class TestStsPrerequisitesMet:
    def test_uri_field(self):
        assert credentials.sts_prerequisites_met({"credentials_uri": "http://x"}) is True

    def test_uri_field_empty(self):
        assert credentials.sts_prerequisites_met({"credentials_uri": ""}) is False

    def test_uri_field_whitespace(self):
        assert credentials.sts_prerequisites_met({"credentials_uri": "  "}) is False

    def test_env_var(self, monkeypatch):
        monkeypatch.setenv("ALIBABA_CLOUD_CREDENTIALS_URI", "http://x")
        assert credentials.sts_prerequisites_met({}) is True

    def test_neither(self):
        # _isolate_cache autouse 已 delenv
        assert credentials.sts_prerequisites_met({}) is False


class TestResetCache:
    def test_reset_clears_cache(self, fake_sdk):
        c1 = credentials.get_credential_client({"credentials_uri": ""})
        credentials.reset_credential_client_cache()
        c2 = credentials.get_credential_client({"credentials_uri": ""})
        assert c1 is not c2
