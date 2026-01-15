"""
Context Snapshot 管理器 — V3 状态隔离的关键组件。

Context Snapshot 采用读时快照——事件发送时冻结一份上下文副本，
接收方基于这份冻结副本工作。不是强一致性（不锁全局状态），
是最终一致性 + 快照隔离的折中：每个 Agent 看到的是"发送时刻的一致视图"，
但多个 Agent 并发修改的合并由 Orchestrator 在结果聚合阶段处理。

在我们的场景中，大多数 Agent 的工作流是 DAG（无并发写），所以快照隔离足够；
只有极少数场景（两个 Agent 同时修改同一文件）需要 Orchestrator 做 merge。
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ContextSnapshot:
    """上下文快照 — 事件发送时冻结的上下文副本。

    每个快照是不可变的，接收方基于这份冻结副本工作，
    不会看到其他 Agent 的并发修改。

    Attributes:
        correlation_id: 关联 ID，同一工作流共享。
        data: 快照数据（深拷贝，确保不可变）。
        version: 快照版本号。
    """

    correlation_id: str
    data: dict[str, Any] = field(default_factory=dict)
    version: int = 0

    def get(self, key: str, default: Any = None) -> Any:
        """从快照中获取指定键的值。

        Args:
            key: 数据键。
            default: 默认值。

        Returns:
            键对应的值，或默认值。
        """
        return self.data.get(key, default)

    def extract(self, keys: list[str]) -> dict[str, Any]:
        """从快照中提取指定键的子集。

        Agent 用此方法只获取自己需要的上下文，而不是接收全量数据。

        Args:
            keys: 需要提取的键列表。

        Returns:
            包含指定键值对的字典。
        """
        return {k: self.data[k] for k in keys if k in self.data}

    def to_dict(self) -> dict[str, Any]:
        """将快照转换为普通字典。"""
        return copy.deepcopy(self.data)


class ContextSnapshotManager:
    """Context Snapshot 管理器 — 管理工作流中的上下文快照生命周期。

    负责创建、读取和合并上下文快照。每个工作流（correlation_id）
    维护一个快照版本链，支持：
    - 创建快照（冻结当前上下文）
    - 读取快照（获取指定版本的上下文）
    - 合并快照（Orchestrator 在结果聚合阶段处理并发修改）

    Args:
        state_store: 状态存储后端（Redis 等）。
    """

    def __init__(self, state_store: Any = None) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            state_store: Any，调用方传入的 state_store 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.state_store = state_store
        self._snapshots: dict[str, list[ContextSnapshot]] = {}

    def create_snapshot(
        self,
        correlation_id: str,
        context: dict[str, Any],
    ) -> ContextSnapshot:
        """为指定工作流创建上下文快照。

        深拷贝当前上下文，确保快照不可变。
        接收方基于这份冻结副本工作，不会看到后续的修改。

        Args:
            correlation_id: 工作流关联 ID。
            context: 当前上下文数据。

        Returns:
            新创建的上下文快照。
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
            correlation_id: 工作流关联 ID。

        Returns:
            最新的上下文快照，如果不存在则返回 None。
        """
        snapshots = self._snapshots.get(correlation_id, [])
        return snapshots[-1] if snapshots else None

    def merge_snapshots(
        self,
        correlation_id: str,
        snapshots: list[ContextSnapshot],
    ) -> dict[str, Any]:
        """合并多个 Agent 的快照 — Orchestrator 在结果聚合阶段使用。

        当多个 Agent 并发修改同一上下文时，Orchestrator 负责合并。
        合并策略：后写入的覆盖先写入的（last-write-wins）。

        Args:
            correlation_id: 工作流关联 ID。
            snapshots: 需要合并的快照列表。

        Returns:
            合并后的上下文字典。
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
            correlation_id: 工作流关联 ID。
        """
        if correlation_id in self._snapshots:
            del self._snapshots[correlation_id]
            logger.debug("Snapshots cleaned up (correlation_id=%s)", correlation_id)
