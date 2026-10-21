"""记忆对象存储模块。"""

from __future__ import annotations

from copy import copy


class MemoryObjectStore:
    """对象领域组件。"""

    def __init__(self) -> None:
        """初始化 MemoryObjectStore。"""
        self.objects: dict[str, tuple[bytes, str]] = {}

    async def put(self, key: str, data: bytes, content_type: str = "") -> None:
        """写入缓存或对象存储数据。

        Args:
            key: 缓存或配置键。
            data: 待处理数据。
            content_type: 内容 MIME 类型。
        """
        self.objects[key] = (copy(data), content_type)

    async def get(self, key: str) -> bytes:
        """读取对象。

        Args:
            key: 缓存或配置键。

        Returns:
            处理结果对象。

        Raises:
            FileNotFoundError: 操作无法完成时抛出。
        """
        try:
            return copy(self.objects[key][0])
        except KeyError as exc:
            raise FileNotFoundError(key) from exc

    async def presigned_get_url(self, key: str, expires_seconds: int = 300) -> str:
        """处理预签名获取URL。

        Args:
            key: 缓存或配置键。
            expires_seconds: 输入参数。

        Returns:
            字符串结果。

        Raises:
            FileNotFoundError: 操作无法完成时抛出。
        """
        if key not in self.objects:
            raise FileNotFoundError(key)
        return f"memory://{key}?expires={expires_seconds}"

    async def delete(self, key: str) -> None:
        """删除对象。

        Args:
            key: 缓存或配置键。
        """
        self.objects.pop(key, None)
