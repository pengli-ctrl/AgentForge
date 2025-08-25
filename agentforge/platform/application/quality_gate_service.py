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

    def gate_retrieval(self, report: RetrievalReport) -> QualityGateResult:
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
        """report: ClassificationReport。"""
        metrics = {
            "classification_accuracy": report.classification_accuracy,
            "priority_accuracy": report.priority_accuracy,
            "structured_output_rate": report.structured_output_rate,
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

        acc_name, acc_value = (
            "classification_accuracy",
            report.classification_accuracy,
        )
        if acc_value < self.HARD_CLASSIFICATION:
            failed.append(f"{acc_name}: {acc_value:.3f} < hard {self.HARD_CLASSIFICATION}")
        elif acc_value < self.TARGET_CLASSIFICATION:
            warned.append(f"{acc_name}: {acc_value:.3f} < target {self.TARGET_CLASSIFICATION}")
        else:
            passed.append(acc_name)
        metrics[acc_name + "_hard"] = self.HARD_CLASSIFICATION
        metrics[acc_name + "_target"] = self.TARGET_CLASSIFICATION

        return self._finalize(metrics=metrics, passed=passed, warned=warned, failed=failed)

    def gate(
        self,
        candidate: ReleaseCandidate,
        retrieval: RetrievalReport | None = None,
        classification=None,
    ) -> QualityGateResult:
        """聚合门禁：可选包含召回评估与分类评估。"""
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
