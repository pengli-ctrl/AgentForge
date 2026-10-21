"""密钥模块。"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

_SECRET_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SecretResolutionError(RuntimeError):
    """密钥解析错误相关组件。"""


@dataclass(frozen=True)
class SecretValue:
    """密钥值相关组件。

    Attributes:
        ref: 引用。
        _value: 值。
        version: 版本号。
    """

    ref: str
    _value: str = field(repr=False)
    version: str = ""

    @property
    def fingerprint(self) -> str:
        """返回指纹。

        Returns:
            字符串结果。
        """
        return hashlib.sha256(self._value.encode("utf-8")).hexdigest()[:12]

    def reveal(self) -> str:
        """返回解密后的密钥明文。

        Returns:
            字符串结果。
        """
        return self._value

    def __str__(self) -> str:
        """返回 SecretValue 的字符串表示。

        Returns:
            字符串结果。
        """
        return f"<secret ref={self.ref!r} version={self.version or self.fingerprint}>"

    def __repr__(self) -> str:
        """返回 SecretValue 的调试字符串表示。

        Returns:
            字符串结果。
        """
        return str(self)


class SecretProvider(Protocol):
    """密钥提供方。

    Attributes:
        scheme: 方案。
    """

    scheme: str

    async def resolve(self, ref: str) -> SecretValue:
        """解析密钥提供方。

        Args:
            ref: 引用。

        Returns:
            密钥值结果。
        """
        ...

    async def rotate(self, ref: str, new_value: str) -> SecretValue:
        """轮换密钥提供方。

        Args:
            ref: 引用。
            new_value: 值。

        Returns:
            密钥值结果。
        """
        ...


class EnvironmentSecretProvider:
    """环境密钥提供方相关组件。"""

    scheme = "env"

    def __init__(self, environment: Mapping[str, str] | None = None) -> None:
        """初始化 EnvironmentSecretProvider。

        Args:
            environment: 环境。
        """
        self._environment = environment if environment is not None else os.environ

    async def resolve(self, ref: str) -> SecretValue:
        """解析环境密钥提供方。

        Args:
            ref: 引用。

        Returns:
            密钥值结果。

        Raises:
            SecretResolutionError: 操作无法完成时抛出。
        """
        name = _env_name(ref)
        value = self._environment.get(name)
        if not value:
            raise SecretResolutionError(f"environment secret is not configured: {name}")
        return SecretValue(ref=ref, _value=value, version=_fingerprint(value))

    async def rotate(self, ref: str, new_value: str) -> SecretValue:
        """轮换环境密钥提供方。

        Args:
            ref: 引用。
            new_value: 值。

        Returns:
            密钥值结果。

        Raises:
            SecretResolutionError: 操作无法完成时抛出。
        """
        name = _env_name(ref)
        if not new_value:
            raise SecretResolutionError("rotated secret must not be empty")
        if isinstance(self._environment, dict):
            self._environment[name] = new_value
        return SecretValue(ref=ref, _value=new_value, version=_fingerprint(new_value))


class VaultSecretProvider:
    """密钥库密钥提供方相关组件。"""

    scheme = "vault"

    def __init__(
        self,
        address: str,
        token: str,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        """初始化 VaultSecretProvider。

        Args:
            address: 输入参数。
            token: 待验证的访问令牌。
            client: 客户端实例。
        """
        self._address = address.rstrip("/")
        self._token = token
        self._client = client

    async def resolve(self, ref: str) -> SecretValue:
        """解析密钥库密钥提供方。

        Args:
            ref: 引用。

        Returns:
            密钥值结果。

        Raises:
            SecretResolutionError: 操作无法完成时抛出。
        """
        path, field_name = _vault_parts(ref)
        client = self._client or httpx.AsyncClient(timeout=5)
        try:
            response = await client.get(
                f"{self._address}/v1/{path}", headers={"X-Vault-Token": self._token}
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            if self._client is None:
                await client.aclose()
        data = payload.get("data", {})
        data = data.get("data", data)
        value = data.get(field_name)
        if not isinstance(value, str) or not value:
            raise SecretResolutionError(f"Vault field not found: {field_name}")
        return SecretValue(ref=ref, _value=value, version=_fingerprint(value))

    async def rotate(self, ref: str, new_value: str) -> SecretValue:
        """轮换密钥库密钥提供方。

        Args:
            ref: 引用。
            new_value: 值。

        Returns:
            密钥值结果。
        """
        path, field_name = _vault_parts(ref)
        client = self._client or httpx.AsyncClient(timeout=5)
        try:
            response = await client.post(
                f"{self._address}/v1/{path}",
                headers={"X-Vault-Token": self._token},
                json={"data": {field_name: new_value}},
            )
            response.raise_for_status()
        finally:
            if self._client is None:
                await client.aclose()
        return SecretValue(ref=ref, _value=new_value, version=_fingerprint(new_value))


class AwsKmsSecretProvider:
    """KMS密钥提供方相关组件。"""

    scheme = "kms"

    def __init__(self, client: Any) -> None:
        """初始化 AwsKmsSecretProvider。

        Args:
            client: 客户端实例。
        """
        self._client = client

    async def resolve(self, ref: str) -> SecretValue:
        """解析KMS密钥提供方。

        Args:
            ref: 引用。

        Returns:
            密钥值结果。

        Raises:
            SecretResolutionError: 操作无法完成时抛出。
        """
        ciphertext = base64.b64decode(ref[len("kms://") :])
        try:
            response = self._client.decrypt(CiphertextBlob=ciphertext)
            value = response["Plaintext"].decode("utf-8")
        except Exception as exc:  # noqa: BLE001 - provider boundary
            raise SecretResolutionError("KMS decryption failed") from exc
        return SecretValue(ref=ref, _value=value, version=_fingerprint(value))

    async def rotate(self, ref: str, new_value: str) -> SecretValue:
        """轮换KMS密钥提供方。

        Args:
            ref: 引用。
            new_value: 值。

        Raises:
            SecretResolutionError: 操作无法完成时抛出。

        Returns:
            密钥值结果。
        """
        raise SecretResolutionError("KMS rotation must be performed by the KMS key policy")


class SecretResolver:
    """密钥解析器相关组件。"""

    def __init__(self, providers: Mapping[str, SecretProvider] | None = None) -> None:
        """初始化 SecretResolver。

        Args:
            providers: 提供方。
        """
        self._providers = dict(providers or {})
        environment = EnvironmentSecretProvider()
        self._providers.setdefault(environment.scheme, environment)
        self._providers.setdefault("secret", self._providers["env"])

    def register(self, provider: SecretProvider) -> None:
        """注册密钥解析器。

        Args:
            provider: 提供方。
        """
        self._providers[provider.scheme] = provider

    async def resolve(self, ref: str) -> SecretValue:
        """解析密钥解析器。

        Args:
            ref: 引用。

        Returns:
            密钥值结果。

        Raises:
            SecretResolutionError: 操作无法完成时抛出。
        """
        scheme = _scheme(ref)
        provider = self._providers.get(scheme)
        if provider is None:
            raise SecretResolutionError(f"no secret provider registered for {scheme}://")
        return await provider.resolve(ref)

    async def rotate(self, ref: str, new_value: str) -> SecretValue:
        """轮换密钥解析器。

        Args:
            ref: 引用。
            new_value: 值。

        Returns:
            密钥值结果。

        Raises:
            SecretResolutionError: 操作无法完成时抛出。
        """
        scheme = _scheme(ref)
        provider = self._providers.get(scheme)
        if provider is None:
            raise SecretResolutionError(f"no secret provider registered for {scheme}://")
        return await provider.rotate(ref, new_value)


def _scheme(ref: str) -> str:
    """处理方案。

    Args:
        ref: 引用。

    Returns:
        字符串结果。

    Raises:
        SecretResolutionError: 操作无法完成时抛出。
    """
    if "://" not in ref:
        raise SecretResolutionError("secret reference must include a scheme")
    return ref.split("://", 1)[0]


def _env_name(ref: str) -> str:
    """处理环境名称。

    Args:
        ref: 引用。

    Returns:
        字符串结果。

    Raises:
        SecretResolutionError: 操作无法完成时抛出。
    """
    name = ref.rsplit("://", 1)[-1]
    if not _SECRET_NAME.fullmatch(name):
        raise SecretResolutionError("invalid environment secret name")
    return name


def _vault_parts(ref: str) -> tuple[str, str]:
    """处理密钥库分片。

    Args:
        ref: 引用。

    Returns:
        结果元组。

    Raises:
        SecretResolutionError: 操作无法完成时抛出。
    """
    body = ref[len("vault://") :]
    if "#" not in body:
        raise SecretResolutionError("Vault reference must include #field")
    path, field_name = body.rsplit("#", 1)
    if not path or not field_name:
        raise SecretResolutionError("invalid Vault reference")
    return path.strip("/"), field_name


def _fingerprint(value: str) -> str:
    """计算指纹内容指纹。

    Args:
        value: 待处理值。

    Returns:
        字符串结果。
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


__all__ = [
    "AwsKmsSecretProvider",
    "EnvironmentSecretProvider",
    "SecretProvider",
    "SecretResolutionError",
    "SecretResolver",
    "SecretValue",
    "VaultSecretProvider",
]
