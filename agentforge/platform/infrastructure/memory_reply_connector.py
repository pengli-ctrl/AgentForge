"""AgentForge 平台基础设施层：memory_reply_connector。

本模块封装 memory_reply_connector 对应外部系统或基础设施协议，提供稳定、可替换的适配接口。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：MemoryReplyConnector。
"""

from __future__ import annotations


class MemoryReplyConnector:
    """MemoryReplyConnector。

    MemoryReplyConnector 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 send_text()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self.messages: list[dict[str, str]] = []

    async def send_text(self, target: str, text: str, idempotency_key: str) -> dict:
        """执行 send_text 对应的逻辑，并返回处理结果。

        Args:
            target: str，调用方传入的 target 参数。
            text: str，调用方传入的 text 参数。
            idempotency_key: str，调用方传入的 idempotency_key 参数。

        Returns:
            dict，函数执行后的结果。
        """
        self.messages.append(
            {
                "target": target,
                "text": text,
                "idempotency_key": idempotency_key,
            }
        )
        return {"message_id": f"mem-{len(self.messages)}"}
