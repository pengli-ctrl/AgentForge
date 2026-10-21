"""S3对象存储模块。"""

from __future__ import annotations

import asyncio
from typing import Any

from agentforge.platform.settings import Settings


class S3ObjectStore:
    """S3对象领域组件。"""

    def __init__(
        self,
        *,
        endpoint_url: str,
        access_key: str,
        secret_key: str,
        bucket: str,
        region: str = "us-east-1",
        use_ssl: bool = False,
        client: Any | None = None,
    ) -> None:
        """初始化 S3ObjectStore。

        Args:
            endpoint_url: 端点URL。
            access_key: 访问键。
            secret_key: 密钥键。
            bucket: 存储桶。
            region: 输入参数。
            use_ssl: 输入参数。
            client: 客户端实例。
        """
        self._endpoint_url = endpoint_url
        self._access_key = access_key
        self._secret_key = secret_key
        self._bucket = bucket
        self._region = region
        self._use_ssl = use_ssl
        self._client = client
        self._bucket_ready = client is not None

    @classmethod
    def from_settings(cls, settings: Settings) -> "S3ObjectStore":
        """从配置构造当前对象。

        Args:
            settings: 应用配置。

        Returns:
            对象结果。
        """
        return cls(
            endpoint_url=settings.object_store_endpoint,
            access_key=settings.object_store_access_key,
            secret_key=settings.object_store_secret_key,
            bucket=settings.object_store_bucket,
            region=settings.object_store_region,
            use_ssl=settings.object_store_use_ssl,
        )

    async def put(self, key: str, data: bytes, content_type: str = "") -> None:
        """写入缓存或对象存储数据。

        Args:
            key: 缓存或配置键。
            data: 待处理数据。
            content_type: 内容 MIME 类型。
        """
        client = await self._get_client()
        await asyncio.to_thread(
            client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=data,
            ContentType=content_type or "application/octet-stream",
        )

    async def get(self, key: str) -> bytes:
        """读取S3对象。

        Args:
            key: 缓存或配置键。

        Returns:
            处理结果对象。
        """
        client = await self._get_client()

        def _read() -> bytes:
            """读取S3对象。

            Returns:
                处理结果对象。
            """
            response = client.get_object(Bucket=self._bucket, Key=key)
            return response["Body"].read()

        return await asyncio.to_thread(_read)

    async def presigned_get_url(self, key: str, expires_seconds: int = 300) -> str:
        """处理预签名获取URL。

        Args:
            key: 缓存或配置键。
            expires_seconds: 输入参数。

        Returns:
            字符串结果。
        """
        client = await self._get_client()
        return await asyncio.to_thread(
            client.generate_presigned_url,
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_seconds,
        )

    async def delete(self, key: str) -> None:
        """删除S3对象。

        Args:
            key: 缓存或配置键。
        """
        client = await self._get_client()
        await asyncio.to_thread(client.delete_object, Bucket=self._bucket, Key=key)

    async def _get_client(self):
        """获取客户端。

        Returns:
            处理结果。

        Raises:
            RuntimeError: 运行时依赖或状态不满足要求时抛出。
        """
        if self._client is not None:
            await self._ensure_bucket()
            return self._client
        try:
            import boto3
            from botocore.config import Config
        except ImportError as exc:
            raise RuntimeError("boto3 is required for S3ObjectStore") from exc
        self._client = boto3.client(
            "s3",
            endpoint_url=self._endpoint_url,
            aws_access_key_id=self._access_key,
            aws_secret_access_key=self._secret_key,
            region_name=self._region,
            use_ssl=self._use_ssl,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )
        await self._ensure_bucket()
        return self._client

    async def _ensure_bucket(self) -> None:
        """确保存储桶。"""
        if self._bucket_ready:
            return
        assert self._client is not None

        def _create_if_missing() -> None:
            """创建缺失。"""
            try:
                self._client.head_bucket(Bucket=self._bucket)
            except Exception:
                self._client.create_bucket(Bucket=self._bucket)

        await asyncio.to_thread(_create_if_missing)
        self._bucket_ready = True
