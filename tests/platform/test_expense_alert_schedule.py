"""测试报销告警调度测试模块。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.modules.expense.workflows.invoice_gate_sweep import (
    ExpenseInvoiceGateSweepWorkflow,
)
from agentforge.platform.modules.support.workflows.sla_sweep import SupportSlaSweepWorkflow
from agentforge.platform.runtime import build_memory_container
from agentforge.platform.settings import get_settings


class RecordingWorkflowClient:
    """记录工作流启动与信号调用的测试客户端。"""

    def __init__(self) -> None:
        """初始化记录。"""
        self.schedules: list[dict] = []

    async def start_workflow(self, workflow, arg, **kwargs):
        """启动工作流。

        Args:
            workflow: 工作流定义或实例。
            arg: 输入参数。
            kwargs: 关键字参数。

        Returns:
            处理结果。
        """
        return kwargs.get("workflow_id") or "workflow-1"

    async def signal_workflow(self, workflow_id, signal, arg=None) -> None:
        """发送信号工作流。

        Args:
            workflow_id: 工作流 ID。
            signal: 信号。
            arg: 输入参数。
        """
        return None

    async def ensure_schedule(self, workflow, arg, **kwargs) -> str:
        """确保调度。

        Args:
            workflow: 工作流定义或实例。
            arg: 输入参数。
            kwargs: 关键字参数。

        Returns:
            字符串结果。
        """
        self.schedules.append({"workflow": workflow, "arg": arg, **kwargs})
        return str(kwargs["schedule_id"])


def test_expense_module_registers_invoice_alert_sweep_schedule(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证报销模块注册发票告警扫描调度对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_ALERT_SWEEP_MINUTES", "5")
    monkeypatch.setenv("AGENTFORGE_SUPPORT_SLA_SWEEP_MINUTES", "7")
    get_settings.cache_clear()
    try:
        workflow_client = RecordingWorkflowClient()
        app = create_platform_app(build_memory_container(workflow_client=workflow_client))
        with TestClient(app):
            pass

        schedules = {item["schedule_id"]: item for item in workflow_client.schedules}
        assert set(schedules) == {"expense-invoice-gate-sweep", "support-sla-sweep"}
        expense_schedule = schedules["expense-invoice-gate-sweep"]
        assert expense_schedule["workflow"] is ExpenseInvoiceGateSweepWorkflow
        assert expense_schedule["interval_seconds"] == 300
        assert expense_schedule["task_queue"] == "expense-copilot"
        support_schedule = schedules["support-sla-sweep"]
        assert support_schedule["workflow"] is SupportSlaSweepWorkflow
        assert support_schedule["interval_seconds"] == 420
        assert support_schedule["task_queue"] == "support-copilot"
    finally:
        get_settings.cache_clear()


def test_expense_invoice_alert_sweep_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """验证报销发票告警扫描可以为停用对应的测试场景。

    Args:
        monkeypatch: pytest 提供的猴子补丁对象。
    """
    monkeypatch.setenv("AGENTFORGE_EXPENSE_INVOICE_ALERT_SWEEP_MINUTES", "0")
    monkeypatch.setenv("AGENTFORGE_SUPPORT_SLA_SWEEP_MINUTES", "0")
    get_settings.cache_clear()
    try:
        workflow_client = RecordingWorkflowClient()
        app = create_platform_app(build_memory_container(workflow_client=workflow_client))
        with TestClient(app):
            pass

        assert workflow_client.schedules == []
    finally:
        get_settings.cache_clear()
