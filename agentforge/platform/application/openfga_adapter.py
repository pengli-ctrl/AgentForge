"""适配器模块。"""

from __future__ import annotations

from agentforge.platform.domain.policy import RelationTuple


class OpenFGAClient:
    """打开FGA 客户端相关组件。"""

    def __init__(self) -> None:
        """初始化 OpenFGAClient。"""
        self._tuples: set[tuple[str, str, str, str, str, str]] = set()

    def write(self, tenant_id: str, tuples: list[RelationTuple]) -> None:
        """写入打开FGA 客户端。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            tuples: 输入参数。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        for tup in tuples:
            if tup.tenant_id != tenant_id:
                raise ValueError("relation tuple tenant mismatch")
            self._tuples.add(self._key(tup))

    def delete(self, tenant_id: str, tuples: list[RelationTuple]) -> None:
        """删除打开FGA 客户端。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            tuples: 输入参数。

        Raises:
            ValueError: 输入值或业务状态不合法时抛出。
        """
        for tup in tuples:
            if tup.tenant_id != tenant_id:
                raise ValueError("relation tuple tenant mismatch")
            self._tuples.discard(self._key(tup))

    def list_tuples(self, tenant_id: str) -> list[RelationTuple]:
        """查询打开FGA 客户端。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
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
        """检查打开FGA 客户端。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            obj_type: 对象类型。
            obj_id: 对象 ID。
            relation: 关系。
            subject: 输入参数。

        Returns:
            操作是否成功。
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
        """判断异步检查是否成立。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            obj_type: 对象类型。
            obj_id: 对象 ID。
            relation: 关系。
            subject: 输入参数。

        Returns:
            操作是否成功。
        """
        return self.check(tenant_id, obj_type, obj_id, relation, subject)

    def _has_tuple(self, key: tuple[str, str, str, str, str, str]) -> bool:
        """判断关系元组是否已存在于授权后端。

        Args:
            key: 缓存或配置键。

        Returns:
            操作是否成功。
        """
        return key in self._tuples

    @staticmethod
    def _key(tup: RelationTuple) -> tuple[str, str, str, str, str, str]:
        """执行键。

        Args:
            tup: 输入参数。

        Returns:
            结果元组。
        """
        return (
            tup.tenant_id,
            tup.object_type,
            tup.object_id,
            tup.relation,
            tup.subject_type,
            tup.subject_id,
        )
