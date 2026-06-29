"""STS 临时凭证解析层（功能 1 + 功能 2 共用）。

基于官方 alibabacloud-credentials 包的 ``CredentialClient`` 单例：

- **功能 1**：STS 三元组连接（标准 STS 环境变量 ``ALIBABA_CLOUD_ACCESS_KEY_ID/
  ACCESS_KEY_SECRET/SECURITY_TOKEN`` / 默认链）。
- **功能 2**：``ALIBABA_CLOUD_CREDENTIALS_URI`` 免密获取 + SDK 内置过期自动刷新。

设计要点：

- ``CredentialClient`` 必须**单例**（模块级缓存）——否则 Session 凭证
  (``credentials_uri``) 的自动刷新失效。
- 临时凭证（AK/SK/SecurityToken）**永不入库** ``config.json``：每次进程启动现拉，
  进程内共享单例、过期由 SDK 自动刷新。CLI 场景的"轮转"由此保证。
- profile 可选存 ``credentials_uri``；为空时走默认链（标准 STS 环境变量 → OIDC →
  ``~/.aliyun/config.json`` → ECS 元数据 → ``ALIBABA_CLOUD_CREDENTIALS_URI``）。
"""

from __future__ import annotations

import os
import threading
from typing import Any, Optional

from .errors import ErrorCode


class CredentialsError(Exception):
    """携带 ``ErrorCode`` 的凭证解析异常，供调用层转 ``output.error()``。"""

    def __init__(self, error_code: ErrorCode, message: str) -> None:
        self.error_code = error_code  # ErrorCode 成员（其 value 即 ErrorMeta）
        self.code = error_code.value.code  # 字符串码，便于字符串式 output.error
        super().__init__(message)


def _import_credentials_sdk():
    """Lazy import alibabacloud-credentials pieces.

    仿 ``commands.metric._import_cms_sdk`` 的 lazy 模式（无依赖时不炸模块 import）；
    同时作为测试 patch 点（``mocker.patch.object(credentials, "_import_credentials_sdk", ...)``）。
    """
    from alibabacloud_credentials.client import Client as CredentialClient
    from alibabacloud_credentials.models import Config as CredentialConfig

    return CredentialClient, CredentialConfig


# 进程级单例缓存：key 为 credentials_uri（None 表示默认链）。
# 必须单例，否则 credentials_uri Session provider 的自动刷新失效。
_credential_client_cache: dict[Optional[str], Any] = {}
_cache_lock = threading.Lock()


def get_credential_client(profile: dict[str, Any]) -> Any:
    """返回单例 ``CredentialClient``（功能 2 轮转核心）。

    - ``profile['credentials_uri']`` 非空 → 显式
      ``Config(type='credentials_uri', credentials_uri=...)``（按 uri 缓存单例）。
    - 否则 → ``CredentialClient()`` 默认链（key=None 缓存）：自动识别标准 STS 环境变量 /
      OIDC / ``~/.aliyun/config.json`` / ECS 元数据 / ``ALIBABA_CLOUD_CREDENTIALS_URI``。

    失败抛 ``CredentialsError``（``CREDENTIALS_URI_INVALID`` / ``CREDENTIALS_PROVIDER_INIT_FAILED``）。
    供 OpenAPI 路径 ``Config(credential=...)`` 使用。
    """
    creds_uri = (profile.get("credentials_uri") or "").strip()
    cache_key: Optional[str] = creds_uri or None

    # Fast path: 无锁查缓存
    cached = _credential_client_cache.get(cache_key)
    if cached is not None:
        return cached

    with _cache_lock:
        # double-check after acquiring lock
        cached = _credential_client_cache.get(cache_key)
        if cached is not None:
            return cached

        try:
            CredentialClient, CredentialConfig = _import_credentials_sdk()
            if creds_uri:
                client = CredentialClient(
                    CredentialConfig(type="credentials_uri", credentials_uri=creds_uri)
                )
            else:
                client = CredentialClient()
        except CredentialsError:
            raise
        except Exception as exc:
            if creds_uri:
                raise CredentialsError(
                    ErrorCode.CREDENTIALS_URI_INVALID,
                    f"credentials_uri provider 初始化失败: {exc}",
                ) from exc
            raise CredentialsError(
                ErrorCode.CREDENTIALS_PROVIDER_INIT_FAILED,
                f"默认凭证链初始化失败: {exc}",
            ) from exc

        _credential_client_cache[cache_key] = client
        return client


def resolve_sts_credentials(profile: dict[str, Any]) -> dict[str, str]:
    """从单例 client 取 STS 三元组（JDBC/psycopg 路径用）。

    每次调用都 ``get_credential()``——SDK 在缓存未过期时返回缓存值，过期时自动刷新。
    返回 ``{access_key_id, access_key_secret, security_token}``。

    - ``get_credential()`` 异常 → ``STS_FETCH_ERROR``(reetryable)
    - ``security_token`` 为空 → ``STS_TOKEN_INCOMPLETE``（凭据源返回长期 AK 而非 STS）
    """
    client = get_credential_client(profile)
    try:
        cred = client.get_credential()
        ak = cred.get_access_key_id()
        sk = cred.get_access_key_secret()
        token = cred.get_security_token()
    except Exception as exc:
        raise CredentialsError(
            ErrorCode.STS_FETCH_ERROR,
            f"获取 STS 临时凭证失败: {exc}",
        ) from exc

    if not ak or not sk or not token:
        raise CredentialsError(
            ErrorCode.STS_TOKEN_INCOMPLETE,
            "STS 凭证不完整（AccessKeyId/AccessKeySecret/SecurityToken 均不可为空）。"
            " 凭据源可能返回了长期 AK 而非 STS 临时凭证。",
        )

    return {
        "access_key_id": ak,
        "access_key_secret": sk,
        "security_token": token,
    }


def sts_prerequisites_met(profile: dict[str, Any]) -> bool:
    """纯静态判断（不发网络）：是否具备 STS 先决条件。

    ``profile['credentials_uri']`` 非空 或 环境变量 ``ALIBABA_CLOUD_CREDENTIALS_URI`` 非空 → True。
    供 ``_api_prerequisites_met`` / 向导校验复用。
    """
    if (profile.get("credentials_uri") or "").strip():
        return True
    if (os.environ.get("ALIBABA_CLOUD_CREDENTIALS_URI") or "").strip():
        return True
    return False


def reset_credential_client_cache() -> None:
    """仅测试用：清空单例缓存，避免跨用例污染。"""
    with _cache_lock:
        _credential_client_cache.clear()
