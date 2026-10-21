"""上下文快照模块。"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextSnapshot:
    """上下文快照 — 事件发送时冻结的上下文副本。

    Attributes:
        correlation_id: 用于关联同一业务链路的关联 ID。
        data: 数据内容。
        version: 版本号。
    """

    correlation_id: str
    data: dict[str, Any] = field(default_factory=dict)
    version: int = 0

    def get(self, key: str, default: Any = None) -> Any:
        """从快照中获取指定键的值。

        Args:
            key: 缓存或配置键。
            default: 默认。

        Returns:
            处理结果对象。
        """
        return self.data.get(key, default)

    def extract(self, keys: list[str]) -> dict[str, Any]:
        """从快照中提取指定键的子集。

        Args:
            keys: 键。

        Returns:
            结构化结果字典。
        """
        return {k: self.data[k] for k in keys if k in self.data}

    def to_dict(self) -> dict[str, Any]:
        """将快照转换为普通字典。

        Returns:
            结构化结果字典。
        """
        return copy.deepcopy(self.data)


class ContextSnapshotManager:
    """上下文快照领域组件。"""

    def __init__(self, state_store: Any = None) -> None:
        """初始化 ContextSnapshotManager。

        Args:
            state_store: 状态存储。
        """
        self.state_store = state_store
        self._snapshots: dict[str, list[ContextSnapshot]] = {}

    def create_snapshot(
        self,
        correlation_id: str,
        context: dict[str, Any],
    ) -> ContextSnapshot:
        """为指定工作流创建上下文快照。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。
            context: 执行上下文。

        Returns:
            上下文快照结果。
        """
        if correlation_id not in self._snapshots:
            self._snapshots[correlation_id] = []

        version = len(self._snapshots[correlation_id])
        snapshot = ContextSnapshot(
            correlation_id=correlation_id,
            data=copy.deepcopy(context),
            version=version,
        )
        self._snapshots[correlation_id].append(snapshot)

        logger.debug(
            "Snapshot created (correlation_id=%s, version=%d, keys=%s)",
            correlation_id,
            version,
            list(context.keys()),
        )

        return snapshot

    def get_latest_snapshot(self, correlation_id: str) -> ContextSnapshot | None:
        """获取指定工作流的最新快照。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。

        Returns:
            上下文快照无结果。
        """
        snapshots = self._snapshots.get(correlation_id, [])
        return snapshots[-1] if snapshots else None

    def merge_snapshots(
        self,
        correlation_id: str,
        snapshots: list[ContextSnapshot],
    ) -> dict[str, Any]:
        """合并快照。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。
            snapshots: 快照。

        Returns:
            结构化结果字典。
        """
        merged: dict[str, Any] = {}
        for snapshot in snapshots:
            merged.update(snapshot.to_dict())

        logger.info(
            "Snapshots merged (correlation_id=%s, count=%d, merged_keys=%s)",
            correlation_id,
            len(snapshots),
            list(merged.keys()),
        )

        return merged

    def cleanup(self, correlation_id: str) -> None:
        """清理指定工作流的所有快照。

        Args:
            correlation_id: 用于关联同一业务链路的关联 ID。
        """
        if correlation_id in self._snapshots:
            del self._snapshots[correlation_id]
            logger.debug("Snapshots cleaned up (correlation_id=%s)", correlation_id)
