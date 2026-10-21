"""记忆发票门禁告警仓储模块。"""

from __future__ import annotations

from copy import deepcopy

from agentforge.platform.modules.expense.domain.invoice import (
    InvoiceGateAlertState,
    InvoiceGateAlertStateStatus,
)


class MemoryExpenseInvoiceGateAlertRepository:
    """报销发票门禁告警仓储，负责持久化读写。"""

    def __init__(self) -> None:
        """初始化 MemoryExpenseInvoiceGateAlertRepository。"""
        self._alerts: dict[str, InvoiceGateAlertState] = {}

    async def save(self, alert: InvoiceGateAlertState) -> None:
        """保存报销发票门禁告警。

        Args:
            alert: 告警。
        """
        existing = self._alerts.get(alert.alert_id)
        if existing is not None:
            self._alerts[alert.alert_id] = deepcopy(alert)
            return
        if alert.status == InvoiceGateAlertStateStatus.ACTIVE:
            for candidate in self._alerts.values():
                if (
                    candidate.tenant_id == alert.tenant_id
                    and candidate.alert_key == alert.alert_key
                    and candidate.status == InvoiceGateAlertStateStatus.ACTIVE
                ):
                    return
        self._alerts[alert.alert_id] = deepcopy(alert)

    async def get(self, tenant_id: str, alert_id: str) -> InvoiceGateAlertState | None:
        """读取报销发票门禁告警。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert_id: 告警 ID。

        Returns:
            发票门禁告警状态无结果。
        """
        alert = self._alerts.get(alert_id)
        if alert is None or alert.tenant_id != tenant_id:
            return None
        return deepcopy(alert)

    async def find_active(
        self,
        tenant_id: str,
        alert_key: str,
    ) -> InvoiceGateAlertState | None:
        """查找活跃。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert_key: 告警键。

        Returns:
            发票门禁告警状态无结果。
        """
        for alert in self._alerts.values():
            if (
                alert.tenant_id == tenant_id
                and alert.alert_key == alert_key
                and alert.status == InvoiceGateAlertStateStatus.ACTIVE
            ):
                return deepcopy(alert)
        return None

    async def count_occurrences(self, tenant_id: str, alert_key: str) -> int:
        """统计报销发票门禁告警。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            alert_key: 告警键。

        Returns:
            整数结果。
        """
        return sum(
            1
            for alert in self._alerts.values()
            if alert.tenant_id == tenant_id and alert.alert_key == alert_key
        )

    async def list_all(
        self,
        tenant_id: str,
        limit: int = 10_000,
    ) -> list[InvoiceGateAlertState]:
        """查询全部。

        Args:
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结果列表。
        """
        alerts = [alert for alert in self._alerts.values() if alert.tenant_id == tenant_id]
        alerts.sort(
            key=lambda alert: (alert.created_at, alert.alert_id),
            reverse=True,
        )
        return [deepcopy(alert) for alert in alerts[:limit]]

    async def list_tenants(self) -> list[str]:
        """查询租户。

        Returns:
            结果列表。
        """
        return sorted({alert.tenant_id for alert in self._alerts.values()})

    async def list_active(self, tenant_id: str) -> list[InvoiceGateAlertState]:
        """查询活跃。

        Args:
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结果列表。
        """
        alerts = [
            alert
            for alert in self._alerts.values()
            if alert.tenant_id == tenant_id and alert.status == InvoiceGateAlertStateStatus.ACTIVE
        ]
        alerts.sort(key=lambda alert: (alert.created_at, alert.alert_id))
        return [deepcopy(alert) for alert in alerts]
