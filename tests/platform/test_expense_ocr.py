"""测试报销OCR测试模块。"""

from __future__ import annotations

import base64

from fastapi.testclient import TestClient

from agentforge.platform.api.app import create_platform_app
from agentforge.platform.domain.ocr import OcrField, OcrResult
from agentforge.platform.runtime import build_memory_container


class FakeOcrProvider:
    """供测试使用的模拟 OCR 提供方。"""

    def __init__(self, result: OcrResult) -> None:
        """初始化模拟OCR提供方。

        Args:
            result: 处理结果。
        """
        self.result = result
        self.calls: list[tuple[bytes, str]] = []

    async def extract(self, content: bytes, content_type: str = "") -> OcrResult:
        """提取模拟OCR提供方。

        Args:
            content: 写入内容。
            content_type: 内容 MIME 类型。

        Returns:
            OCR结果结果。
        """
        self.calls.append((content, content_type))
        return self.result


def _body(content: bytes = b"invoice-image") -> dict[str, str]:
    """处理请求体。

    Args:
        content: 写入内容。

    Returns:
        结构化结果字典。
    """
    return {
        "tenant_id": "tenant-ocr",
        "content_type": "image/png",
        "content_base64": base64.b64encode(content).decode("ascii"),
    }


def test_ocr_extraction_requires_review_and_normalizes_fields() -> None:
    """验证OCR提取要求审核及字段对应的测试场景。"""
    provider = FakeOcrProvider(
        OcrResult(
            text="Invoice total 1,280.50 CNY dated 2026-10-18",
            provider="fake-ocr",
            fields=[
                OcrField(name="amount", value="¥1,280.50", confidence=0.98),
                OcrField(name="invoice_date", value="2026/10/18", confidence=0.91),
                OcrField(name="申请人", value="employee-9", confidence=0.87),
                OcrField(name="费用类型", value="travel", confidence=0.95),
            ],
        )
    )
    app = create_platform_app(build_memory_container(ocr=provider))
    response = TestClient(app).post(
        "/v1/expense/extractions",
        json=_body(),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["amount_cents"] == 128050
    assert result["currency"] == "CNY"
    assert result["expense_date"] == "2026-10-18"
    assert result["applicant_id"] == "employee-9"
    assert result["category"] == "travel"
    assert result["provider"] == "fake-ocr"
    assert result["requires_review"] is True
    assert provider.calls == [(b"invoice-image", "image/png")]


def test_ocr_endpoint_returns_503_without_provider() -> None:
    """验证OCR端点返回不包含提供方对应的测试场景。"""
    response = TestClient(create_platform_app()).post(
        "/v1/expense/extractions",
        json=_body(),
    )
    assert response.status_code == 503


def test_ocr_extraction_rejects_invalid_amount() -> None:
    """验证OCR提取拒绝无效金额对应的测试场景。"""
    provider = FakeOcrProvider(
        OcrResult(
            text="broken",
            fields=[OcrField(name="amount", value="not-a-number", confidence=0.4)],
            provider="fake-ocr",
        )
    )
    app = create_platform_app(build_memory_container(ocr=provider))
    response = TestClient(app).post("/v1/expense/extractions", json=_body())
    assert response.status_code == 422


def test_ocr_confirmation_creates_claim_with_server_side_audit_context() -> None:
    """验证OCR确认创建报销单使用侧审计上下文对应的测试场景。"""
    provider = FakeOcrProvider(
        OcrResult(
            text="Invoice total 1,280.50 CNY dated 2026-10-18",
            provider="fake-ocr",
            fields=[
                OcrField(name="amount", value="1280.50", confidence=0.98),
                OcrField(name="invoice_date", value="2026-10-18", confidence=0.91),
                OcrField(name="applicant", value="employee-9", confidence=0.87),
                OcrField(name="category", value="travel", confidence=0.95),
            ],
        )
    )
    client = TestClient(create_platform_app(build_memory_container(ocr=provider)))
    extraction = client.post("/v1/expense/extractions", json=_body()).json()
    assert extraction["extraction_id"]

    response = client.post(
        f"/v1/expense/extractions/{extraction['extraction_id']}/confirm",
        json={
            "tenant_id": "tenant-ocr",
            "idempotency_key": "confirmed-ocr-1",
            "confirmed_fields": {"category": "meals", "amount_cents": 128000},
        },
    )
    assert response.status_code == 200, response.text
    claim = response.json()
    assert claim["status"] == "draft"
    assert claim["amount_cents"] == 128000
    assert claim["metadata"]["ocr"]["extraction_id"] == extraction["extraction_id"]
    assert claim["metadata"]["ocr"]["raw_text"] == provider.result.text
    assert claim["metadata"]["ocr"]["confirmed_fields"]["category"] == "meals"

    repeated = client.post(
        f"/v1/expense/extractions/{extraction['extraction_id']}/confirm",
        json={"tenant_id": "tenant-ocr"},
    )
    assert repeated.status_code == 409


def test_ocr_confirmation_registers_invoice_candidate_and_flags_duplicate() -> None:
    """验证OCR确认注册发票候选结果及标记重复对应的测试场景。"""
    provider = FakeOcrProvider(
        OcrResult(
            text="Invoice INV-OCR-1 amount 1280.50",
            provider="fake-ocr",
            fields=[
                OcrField(name="amount", value="1280.50", confidence=0.98),
                OcrField(name="invoice_date", value="2026-10-18", confidence=0.91),
                OcrField(name="invoice_code", value="044001", confidence=0.9),
                OcrField(name="invoice_number", value="INV-OCR-1", confidence=0.95),
                OcrField(name="seller_tax_id", value="91310000TEST", confidence=0.9),
                OcrField(name="applicant", value="employee-9", confidence=0.87),
                OcrField(name="category", value="travel", confidence=0.95),
            ],
        )
    )
    client = TestClient(create_platform_app(build_memory_container(ocr=provider)))

    first_extraction = client.post("/v1/expense/extractions", json=_body()).json()
    first = client.post(
        f"/v1/expense/extractions/{first_extraction['extraction_id']}/confirm",
        json={"tenant_id": "tenant-ocr", "idempotency_key": "ocr-invoice-1"},
    )
    assert first.status_code == 200, first.text
    first_claim = first.json()
    assert first_claim["metadata"]["invoice_registration"]["status"] == "registered"
    invoices = client.get(
        f"/v1/expense/claims/{first_claim['claim_id']}/invoices",
        params={"tenant_id": "tenant-ocr"},
    ).json()["invoices"]
    assert len(invoices) == 1
    assert invoices[0]["invoice_number"] == "INV-OCR-1"
    assert invoices[0]["metadata"]["source"] == "ocr"

    second_extraction = client.post("/v1/expense/extractions", json=_body(b"other")).json()
    second = client.post(
        f"/v1/expense/extractions/{second_extraction['extraction_id']}/confirm",
        json={"tenant_id": "tenant-ocr", "idempotency_key": "ocr-invoice-2"},
    )
    assert second.status_code == 200, second.text
    second_claim = second.json()
    assert second_claim["metadata"]["invoice_registration"]["status"] == "failed"
    assert "duplicate invoice" in second_claim["metadata"]["invoice_registration"]["reason"]
