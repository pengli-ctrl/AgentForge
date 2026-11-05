"""提供架构升级所需的可替换端口。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class AuthPort(Protocol):
    """定义身份认证适配协议。"""

    async def authenticate(self, token: str) -> Mapping[str, Any]:
        """解析认证令牌。

        Args:
            token: 认证令牌。

        Returns:
            认证声明。
        """
        ...


class PolicyPort(Protocol):
    """定义授权策略适配协议。"""

    async def authorize(
        self,
        *,
        tenant_id: str,
        principal: str,
        action: str,
        resource_type: str,
        resource_id: str,
        context: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """执行授权判断。

        Args:
            tenant_id: 租户标识。
            principal: 操作主体。
            action: 操作名称。
            resource_type: 资源类型。
            resource_id: 资源标识。
            context: 附加上下文。

        Returns:
            授权判断结果。
        """
        ...


class RateLimitPort(Protocol):
    """定义限流适配协议。"""

    async def acquire(self, key: str, *, cost: int = 1) -> bool:
        """获取限流额度。

        Args:
            key: 限流键。
            cost: 消耗额度。

        Returns:
            是否允许。
        """
        ...

    async def release(self, key: str, *, cost: int = 1) -> None:
        """释放限流额度。

        Args:
            key: 限流键。
            cost: 消耗额度。
        """
        ...


class ContextStorePort(Protocol):
    """定义上下文存储适配协议。"""

    async def write(self, key: str, value: Any) -> None:
        """写入上下文。

        Args:
            key: 上下文键。
            value: 上下文值。
        """
        ...

    async def read(self, key: str) -> Any | None:
        """读取上下文。

        Args:
            key: 上下文键。

        Returns:
            上下文值。
        """
        ...

    async def delete(self, key: str) -> bool:
        """删除上下文。

        Args:
            key: 上下文键。

        Returns:
            是否删除。
        """
        ...

    async def clear(self) -> None:
        """清空上下文。"""
        ...


class PromptRegistryPort(Protocol):
    """定义提示词注册表适配协议。"""

    async def resolve(self, name: str, *, label: str = "production") -> Mapping[str, Any]:
        """解析提示词版本。

        Args:
            name: 提示词名称。
            label: 发布标签。

        Returns:
            提示词记录。
        """
        ...


class RagParserPort(Protocol):
    """定义文档解析适配协议。"""

    async def parse(
        self, content: bytes, *, content_type: str = "", filename: str = ""
    ) -> Mapping[str, Any]:
        """解析文档内容。

        Args:
            content: 文件字节。
            content_type: 文件类型。
            filename: 文件名。

        Returns:
            解析结果。
        """
        ...


class DagExecutorPort(Protocol):
    """定义 DAG 执行适配协议。"""

    async def execute(self, dag: Mapping[str, Any], *, context_id: str) -> Mapping[str, Any]:
        """执行 DAG。

        Args:
            dag: DAG 定义。
            context_id: 上下文标识。

        Returns:
            执行结果。
        """
        ...
