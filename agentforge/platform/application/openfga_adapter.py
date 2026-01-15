"""AgentForge 平台应用服务层：openfga_adapter。

本模块封装 openfga_adapter 对应外部系统或基础设施协议，提供稳定、可替换的适配接口。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：OpenFGAClient。
"""

from __future__ import annotations

from agentforge.platform.domain.policy import RelationTuple


class OpenFGAClient:
    """OpenFGAClient。

    OpenFGAClient 封装外部系统或基础设施协议，向上提供稳定、可测试的接口。

    主要成员：
    - 方法 write()。
    - 方法 delete()。
    - 方法 list_tuples()。
    - 方法 check()。
    - 方法 acheck()。

    设计约束：
    - 保持接口稳定，不向调用方暴露不必要的数据结构。
    - 涉及租户、权限、审计或成本的逻辑必须显式处理。
    """

    def __init__(self) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Returns:
            None，函数执行后的结果。
        """
        self._tuples: set[tuple[str, str, str, str, str, str]] = set()

    def write(self, tenant_id: str, tuples: list[RelationTuple]) -> None:
        """执行 write 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            tuples: list[RelationTuple]，调用方传入的 tuples 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        for tup in tuples:
            if tup.tenant_id != tenant_id:
                raise ValueError("relation tuple tenant mismatch")
            self._tuples.add(self._key(tup))

    def delete(self, tenant_id: str, tuples: list[RelationTuple]) -> None:
        """执行 delete 对应的核心操作，并保持调用契约稳定。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            tuples: list[RelationTuple]，调用方传入的 tuples 参数。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        for tup in tuples:
            if tup.tenant_id != tenant_id:
                raise ValueError("relation tuple tenant mismatch")
            self._tuples.discard(self._key(tup))

    def list_tuples(self, tenant_id: str) -> list[RelationTuple]:
        """查询并返回列表结果，并返回调用方需要的结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。

        Returns:
            list[RelationTuple]，函数执行后的结果。
        """
        return [
            RelationTuple(
                tenant_id=tenant_id,
                object_type=parts[0],
                object_id=parts[1],
                relation=parts[2],
                subject_type=parts[3],
                subject_id=parts[4],
            )
            for parts in self._tuples
            if parts[0] == tenant_id
        ]

    def check(
        self, tenant_id: str, obj_type: str, obj_id: str, relation: str, subject: str
    ) -> bool:
        """执行 check 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            obj_type: str，调用方传入的 obj_type 参数。
            obj_id: str，调用方传入的 obj_id 参数。
            relation: str，调用方传入的 relation 参数。
            subject: str，调用方传入的 subject 参数。

        Returns:
            bool，函数执行后的结果。
        """
        key = (
            tenant_id,
            obj_type,
            obj_id,
            relation,
            "user",
            subject,
        )
        return self._has_tuple(key)

    async def acheck(
        self,
        tenant_id: str,
        obj_type: str,
        obj_id: str,
        relation: str,
        subject: str,
    ) -> bool:
        """执行 acheck 对应的逻辑，并返回处理结果。

        Args:
            tenant_id: str，调用方传入的 tenant_id 参数。
            obj_type: str，调用方传入的 obj_type 参数。
            obj_id: str，调用方传入的 obj_id 参数。
            relation: str，调用方传入的 relation 参数。
            subject: str，调用方传入的 subject 参数。

        Returns:
            bool，函数执行后的结果。
        """
        return self.check(tenant_id, obj_type, obj_id, relation, subject)

    def _has_tuple(self, key: tuple[str, str, str, str, str, str]) -> bool:
        """执行 _has_tuple 对应的逻辑，并返回处理结果。

        Args:
            key: tuple[str, str, str, str, str, str]，调用方传入的 key 参数。

        Returns:
            bool，函数执行后的结果。
        """
        return key in self._tuples

    @staticmethod
    def _key(tup: RelationTuple) -> tuple[str, str, str, str, str, str]:
        """执行 _key 对应的逻辑，并返回处理结果。

        Args:
            tup: RelationTuple，调用方传入的 tup 参数。

        Returns:
            tuple[str, str, str, str, str, str]，函数执行后的结果。
        """
        return (
            tup.tenant_id,
            tup.object_type,
            tup.object_id,
            tup.relation,
            tup.subject_type,
            tup.subject_id,
        )
