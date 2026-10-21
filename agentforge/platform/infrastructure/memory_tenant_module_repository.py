"""记忆租户模块仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.domain.tenant_module import TenantModuleState


class MemoryTenantModuleRepository:
    """租户模块仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryTenantModuleRepository。"""
        self._states: dict[tuple[str, str], TenantModuleState] = {}

    async def get(self, tenant_id: str, module_name: str) -> TenantModuleState | None:
        """读取租户模块。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            module_name: 模块名称。

        Returns:
            租户模块状态无结果。
        """
        state = self._states.get((tenant_id, module_name))
        return deepcopy(state) if state is not None else None

    async def list(self, tenant_id: str) -> list[TenantModuleState]:
        """查询租户模块。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        states = [state for (tid, _), state in self._states.items() if tid == tenant_id]
        return [deepcopy(state) for state in sorted(states, key=lambda item: item.module_name)]

    async def save(self, state: TenantModuleState) -> None:
        """保存租户模块。

        Args:
            state: 当前状态。
        """
        self._states[(state.tenant_id, state.module_name)] = deepcopy(state)
