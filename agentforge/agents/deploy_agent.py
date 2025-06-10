"""部署 Agent — 执行部署操作、验证部署结果。

V3 架构中的部署能力 Agent，在博客文章的 V3 架构总览中被提及。
负责在代码审查、测试和文档生成完成后执行部署操作。

部署安全原则（来自博客文章中的容错设计）：
- 部署是高风险操作，必须经过 Trust Boundary 校验
- 所有测试通过后才允许部署
- 部署操作记录完整审计日志
- 支持回滚机制

上下文隔离：
- 只从 context_snapshot 中提取部署配置和测试结果
- 不接收原始代码内容
"""

from __future__ import annotations

import logging
from typing import Any

from agentforge.core.agent import Agent
from agentforge.core.base_tool import ToolRegistry

logger = logging.getLogger(__name__)


class DeployAgent(Agent):
    """部署 Agent — 执行部署操作并验证部署结果。

    职责：
    - 验证前置条件（测试通过率、安全扫描结果）
    - 执行部署操作（Docker 镜像构建、服务更新）
    - 部署后健康检查
    - 生成部署报告和变更记录

    上下文隔离：
    - 只提取 context_snapshot 中的 deploy_config、test_result 和 security_scan_result
    - 不接收原始代码内容
    - 输出事件只携带部署结果摘要和部署状态

    安全设计：
    - 测试通过率 < 0.8 时拒绝部署
    - 安全扫描存在 critical 漏洞时拒绝部署
    - 部署失败自动回滚

    Args:
        llm_gateway: LLM 网关实例。
        tool_registry: 工具注册表（可选）。
    """

    REQUIRED_CONTEXT_KEYS = ["deploy_config", "test_result", "security_scan_result"]

    # 部署前置条件阈值
    MIN_PASS_RATE: float = 0.8
    BLOCKED_SEVERITY: str = "critical"

    def __init__(
        self,
        llm_gateway: Any,
        tool_registry: ToolRegistry | None = None,
    ) -> None:
        super().__init__(
            llm_gateway=llm_gateway,
            name="deploy",
            tool_registry=tool_registry or ToolRegistry(),
            max_iterations=3,
            token_budget=4000,
        )

        self.prompt_template = (
            "你是一个部署助手。请根据以下信息执行部署操作。\\n\\n"
            "## 任务\\n{task}\\n\\n"
            "## 上下文（部署配置和测试结果）\\n{context}\\n\\n"
            "## 部署要求\\n"
            "1. 验证前置条件（测试通过率、安全扫描结果）\\n"
            "2. 生成部署计划\\n"
            "3. 执行部署操作\\n"
            "4. 部署后健康检查\\n"
            "5. 生成部署报告\\n"
        )

    def _extract_context(self, context_snapshot: dict[str, Any]) -> dict[str, Any]:
        """从上下文快照中提取部署需要的上下文。

        只提取部署配置、测试结果和安全扫描结果。

        Args:
            context_snapshot: 完整的上下文快照。

        Returns:
            包含部署配置和测试结果的上下文子集。
        """
        return {k: context_snapshot[k] for k in self.REQUIRED_CONTEXT_KEYS if k in context_snapshot}

    async def execute(self, event: Any) -> Any:
        """执行部署任务 — 带前置条件校验。

        在标准 Agent 执行流程前，先检查前置条件：
        - 测试通过率必须 >= MIN_PASS_RATE
        - 安全扫描不能有 critical 级别漏洞

        Args:
            event: 接收到的 Agent 事件。

        Returns:
            输出事件，携带部署结果。
        """
        relevant_context = self._extract_context(event.context_snapshot)

        # 前置条件校验
        check_result = self._check_preconditions(relevant_context)
        if not check_result["passed"]:
            from agentforge.core.event_types import AgentEvent, EventType

            logger.warning(
                "Deploy blocked by preconditions (reason=%s, correlation_id=%s)",
                check_result["reason"],
                event.correlation_id,
            )
            return AgentEvent(
                event_type=EventType.AGENT_FAILED,
                source_agent=self.name,
                payload={
                    "result": check_result,
                    "error": check_result["reason"],
                },
                correlation_id=event.correlation_id,
                context_snapshot={
                    "deploy_result": {
                        "status": "blocked",
                        "reason": check_result["reason"],
                    }
                },
            )

        # 前置条件通过，执行标准流程
        return await super().execute(event)

    def _check_preconditions(self, context: dict[str, Any]) -> dict[str, Any]:
        """检查部署前置条件。

        Args:
            context: 部署上下文。

        Returns:
            检查结果字典，包含 passed 和 reason 字段。
        """
        # 检查测试通过率
        test_result = context.get("test_result", {})
        pass_rate = test_result.get("pass_rate", 0.0)
        if pass_rate < self.MIN_PASS_RATE:
            return {
                "passed": False,
                "reason": f"Test pass rate {pass_rate} < {self.MIN_PASS_RATE}",
            }

        # 检查安全扫描结果
        security_result = context.get("security_scan_result", {})
        severity = security_result.get("severity", "info")
        if severity == self.BLOCKED_SEVERITY:
            return {
                "passed": False,
                "reason": f"Security scan found {self.BLOCKED_SEVERITY} vulnerabilities",
            }

        return {"passed": True, "reason": ""}

    def _build_downstream_context(
        self,
        original_snapshot: dict[str, Any],
        relevant_context: dict[str, Any],
        tool_results: list,
    ) -> dict[str, Any]:
        """构造下游 Agent 需要的上下文快照。

        Args:
            original_snapshot: 原始上下文快照。
            relevant_context: 当前 Agent 提取的上下文。
            tool_results: 工具执行结果。

        Returns:
            传递给下游 Agent 的上下文快照。
        """
        downstream = {
            "deploy_result": {
                "status": "success",
                "summary": self._summarize(None, tool_results),
            }
        }
        return downstream

    def _build_initial_messages(self, task: str) -> list[dict[str, str]]:
        """构造初始消息列表。

        Args:
            task: 任务描述。

        Returns:
            消息列表。
        """
        return [
            {"role": "system", "content": "You are a deployment assistant."},
            {"role": "user", "content": task},
        ]
