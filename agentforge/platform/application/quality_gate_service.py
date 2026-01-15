"""AgentForge 平台应用服务层：quality_gate_service。

本模块实现 quality_gate_service 应用服务，编排多个领域对象和基础设施组件完成业务流程。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
- 主要类：QualityGateService。
"""

from __future__ import annotations

from agentforge.platform.domain.quality import (
    QualityGateResult,
    QualityGateVerdict,
    ReleaseCandidate,
)
from agentforge.platform.domain.retrieval import RetrievalReport


class QualityGateService:
    """发布质量门禁。

    基于离线评估报告（召回评估 + 分类评估）对发布候选做门槛判定：
    - BLOCK：存在硬性失败项（召回/引用/分类不达标，或出现高风险漏报）。
    - HOLD：仅触发软性告警（低于理想目标但高于硬底线）。
    - PASS：全部达标。

    纯函数式判定，不写库；便于单测与 CI 回归复用。
    """

    # 硬底线：低于该值直接 BLOCK。
    HARD_RECALL = 0.6
    HARD_CITATION = 0.6
    HARD_CLASSIFICATION = 0.75
    HARD_HIGH_RISK_MISS = 0.0  # 高风险漏报必须为 0
    # 理想目标：低于该值但高于硬底线 → HOLD。
    TARGET_RECALL = 0.8
    TARGET_CITATION = 0.85
    TARGET_CLASSIFICATION = 0.9
    # P0-5：priority / 结构化合法率 / risk 也「真正判级」，不再是仅展示不拦截。
    HARD_PRIORITY = 0.7
    TARGET_PRIORITY = 0.9
    HARD_STRUCTURED = 0.8
    TARGET_STRUCTURED = 1.0
    HARD_RISK_ACCURACY = 0.75
    TARGET_RISK_ACCURACY = 0.9

    def gate_retrieval(self, report: RetrievalReport) -> QualityGateResult:
        """执行 gate_retrieval 对应的逻辑，并返回处理结果。

        Args:
            report: RetrievalReport，调用方传入的 report 参数。

        Returns:
            QualityGateResult，函数执行后的结果。
        """
        metrics = {
            "recall_at_k": report.recall_at_k,
            "precision_at_k": report.precision_at_k,
            "citation_accuracy": report.citation_accuracy,
        }
        passed: list[str] = []
        warned: list[str] = []
        failed: list[str] = []

        for name, value, hard, target in (
            ("recall_at_k", report.recall_at_k, self.HARD_RECALL, self.TARGET_RECALL),
            (
                "citation_accuracy",
                report.citation_accuracy,
                self.HARD_CITATION,
                self.TARGET_CITATION,
            ),
        ):
            if value < hard:
                failed.append(f"{name}: {value:.3f} < hard {hard}")
            elif value < target:
                warned.append(f"{name}: {value:.3f} < target {target}")
            else:
                passed.append(name)
            metrics[name + "_hard"] = hard
            metrics[name + "_target"] = target

        return self._finalize(metrics=metrics, passed=passed, warned=warned, failed=failed)

    def gate_classification(self, report) -> QualityGateResult:
        """执行 gate_classification 对应的逻辑，并返回处理结果。

        Args:
            report: Any，调用方传入的 report 参数。

        Returns:
            QualityGateResult，函数执行后的结果。
        """
        metrics = {
            "classification_accuracy": report.classification_accuracy,
            "priority_accuracy": report.priority_accuracy,
            "structured_output_rate": report.structured_output_rate,
            "risk_accuracy": report.risk_accuracy,
            "high_risk_miss_rate": report.high_risk_miss_rate,
        }
        passed: list[str] = []
        warned: list[str] = []
        failed: list[str] = []

        # 高风险漏报是硬性失败：出现任何一次即为 BLOCK。
        if report.high_risk_miss_rate > self.HARD_HIGH_RISK_MISS:
            failed.append(f"high_risk_miss_rate: {report.high_risk_miss_rate:.3f} > 0")
        else:
            passed.append("high_risk_miss_rate")

        # P0-5：classification / priority / structured / risk 全部「真正判级」。
        # 每一指标都按 hard→BLOCK、target→HOLD 处理，四指标都参与拦截，不再只是展示。
        indicators = (
            (
                "classification_accuracy",
                report.classification_accuracy,
                self.HARD_CLASSIFICATION,
                self.TARGET_CLASSIFICATION,
            ),
            (
                "priority_accuracy",
                report.priority_accuracy,
                self.HARD_PRIORITY,
                self.TARGET_PRIORITY,
            ),
            (
                "structured_output_rate",
                report.structured_output_rate,
                self.HARD_STRUCTURED,
                self.TARGET_STRUCTURED,
            ),
            (
                "risk_accuracy",
                report.risk_accuracy,
                self.HARD_RISK_ACCURACY,
                self.TARGET_RISK_ACCURACY,
            ),
        )
        for name, value, hard, target in indicators:
            if value < hard:
                failed.append(f"{name}: {value:.3f} < hard {hard}")
            elif value < target:
                warned.append(f"{name}: {value:.3f} < target {target}")
            else:
                passed.append(name)
            metrics[name + "_hard"] = hard
            metrics[name + "_target"] = target

        return self._finalize(metrics=metrics, passed=passed, warned=warned, failed=failed)

    def gate(
        self,
        candidate: ReleaseCandidate,
        retrieval: RetrievalReport | None = None,
        classification=None,
    ) -> QualityGateResult:
        """执行 gate 对应的逻辑，并返回处理结果。

        Args:
            candidate: ReleaseCandidate，调用方传入的 candidate 参数。
            retrieval: RetrievalReport | None，调用方传入的 retrieval 参数。
            classification: Any，调用方传入的 classification 参数。

        Returns:
            QualityGateResult，函数执行后的结果。
        """
        gates: list[QualityGateResult] = []
        if retrieval is not None:
            gates.append(self.gate_retrieval(retrieval))
        if classification is not None:
            gates.append(self.gate_classification(classification))

        if not gates:
            return QualityGateResult(verdict=QualityGateVerdict.PASS)

        passed: list[str] = []
        warned: list[str] = []
        failed: list[str] = []
        metrics: dict[str, float] = {}
        for gate in gates:
            passed.extend(gate.passed)
            warned.extend(gate.warned)
            failed.extend(gate.failed)
            metrics.update(gate.metrics)
        return self._finalize(metrics=metrics, passed=passed, warned=warned, failed=failed)

    @staticmethod
    def _finalize(
        metrics: dict[str, float],
        passed: list[str],
        warned: list[str],
        failed: list[str],
    ) -> QualityGateResult:
        """执行 _finalize 对应的逻辑，并返回处理结果。

        Args:
            metrics: dict[str, float]，调用方传入的 metrics 参数。
            passed: list[str]，调用方传入的 passed 参数。
            warned: list[str]，调用方传入的 warned 参数。
            failed: list[str]，调用方传入的 failed 参数。

        Returns:
            QualityGateResult，函数执行后的结果。
        """
        if failed:
            verdict = QualityGateVerdict.BLOCK
        elif warned:
            verdict = QualityGateVerdict.HOLD
        else:
            verdict = QualityGateVerdict.PASS
        return QualityGateResult(
            verdict=verdict,
            passed=passed,
            warned=warned,
            failed=failed,
            metrics=metrics,
        )
