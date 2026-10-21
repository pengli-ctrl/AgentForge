"""路由模块。"""

from __future__ import annotations

import base64
import binascii
import csv
import io
from datetime import datetime, timezone
from typing import Any, Protocol

from fastapi import APIRouter, HTTPException, Query, Request, Response

from agentforge.platform.domain.upload import UploadSession
from agentforge.platform.modules.expense.application.answer_service import ExpenseRagAnswerService
from agentforge.platform.modules.expense.application.attachment_service import (
    ExpenseAttachmentService,
)
from agentforge.platform.modules.expense.application.import_service import ExpenseImportService
from agentforge.platform.modules.expense.application.invoice_service import ExpenseInvoiceService
from agentforge.platform.modules.expense.application.ledger_service import ExpenseLedgerService
from agentforge.platform.modules.expense.application.ocr_extraction_service import ExpenseOcrService
from agentforge.platform.modules.expense.application.ocr_job_service import ExpenseOcrJobService
from agentforge.platform.modules.expense.application.service import ExpenseClaimService
from agentforge.platform.modules.expense.application.writeback_job_service import (
    ExpenseWritebackJobService,
)
from agentforge.platform.modules.expense.domain.claim import ExpenseClaim, ExpenseClaimStatus
from agentforge.platform.modules.expense.domain.invoice import InvoiceGateSummary
from agentforge.platform.modules.expense.ports import ExpenseClaimRepository
from agentforge.platform.sdk.ports import AuthenticatorPort, ChunkedUploadPort, ModuleAccessPort


class ExpenseRouterContext(Protocol):
    """报销上下文能力端口协议。"""

    @property
    def authenticator(self) -> AuthenticatorPort:
        """返回认证器。

        Returns:
            认证器结果。
        """
        ...

    @property
    def module_access(self) -> ModuleAccessPort:
        """返回模块访问。

        Returns:
            模块访问结果。
        """
        ...

    @property
    def service(self) -> ExpenseClaimService:
        """执行服务。

        Returns:
            报销报销单服务结果。
        """
        ...

    @property
    def repository(self) -> ExpenseClaimRepository:
        """执行仓储。

        Returns:
            报销报销单仓储结果。
        """
        ...

    @property
    def ocr_service(self) -> ExpenseOcrService | None:
        """返回当前模块的 OCR 服务实例。

        Returns:
            报销OCR服务无结果。
        """
        ...

    @property
    def attachment_service(self) -> ExpenseAttachmentService:
        """执行附件服务。

        Returns:
            报销附件服务结果。
        """
        ...

    @property
    def ocr_job_service(self) -> ExpenseOcrJobService | None:
        """返回当前模块的 OCR 任务服务实例。

        Returns:
            报销OCR任务服务无结果。
        """
        ...

    @property
    def import_service(self) -> ExpenseImportService:
        """执行导入服务。

        Returns:
            报销导入服务结果。
        """
        ...

    @property
    def invoice_service(self) -> ExpenseInvoiceService:
        """执行发票服务。

        Returns:
            报销发票服务结果。
        """
        ...

    @property
    def answer_service(self) -> ExpenseRagAnswerService:
        """回答服务。

        Returns:
            报销RAG回答服务结果。
        """
        ...

    @property
    def ledger_service(self) -> ExpenseLedgerService:
        """执行台账服务。

        Returns:
            报销台账服务结果。
        """
        ...

    @property
    def writeback_job_service(self) -> ExpenseWritebackJobService:
        """执行写回任务服务。

        Returns:
            报销写回任务服务结果。
        """
        ...

    @property
    def uploads(self) -> ChunkedUploadPort:
        """返回上传。

        Returns:
            上传结果。
        """
        ...


def create_expense_router(runtime: ExpenseRouterContext) -> APIRouter:
    """创建报销路由。

    Args:
        runtime: 运行时容器。

    Returns:
        处理结果对象。
    """
    router = APIRouter(tags=["expense"])

    @router.post("/attachments")
    async def upload_attachment(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /attachments 请求，上传附件。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        filename = body.get("filename")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(filename, str) or not filename:
            raise HTTPException(status_code=422, detail="filename is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            data = _decode_base64(body.get("content_base64"))
            attachment = await runtime.attachment_service.upload(
                tenant_id=tenant_id,
                filename=filename,
                content_type=str(body.get("content_type") or ""),
                data=data,
            )
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return attachment.model_dump(mode="json")

    @router.post("/upload-sessions")
    async def begin_resumable_upload(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /upload-sessions 请求，开始可续传上传。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        filename = body.get("filename")
        size_bytes = body.get("size_bytes")
        chunk_size = body.get("chunk_size")
        sha256 = body.get("sha256")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(filename, str) or not filename:
            raise HTTPException(status_code=422, detail="filename is required")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes < 1:
            raise HTTPException(status_code=422, detail="size_bytes must be a positive integer")
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) or chunk_size < 1:
            raise HTTPException(status_code=422, detail="chunk_size must be a positive integer")
        if sha256 is not None and not isinstance(sha256, str):
            raise HTTPException(status_code=422, detail="sha256 must be a string")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            session = await runtime.uploads.begin(
                tenant_id=tenant_id,
                owner_module="expense",
                filename=filename,
                content_type=str(body.get("content_type") or ""),
                size_bytes=size_bytes,
                chunk_size=chunk_size,
                sha256=sha256,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _upload_session_view(session)

    @router.get("/upload-sessions/{upload_id}")
    async def get_resumable_upload(
        request: Request,
        upload_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """处理 GET /upload-sessions/{upload_id} 请求，获取可续传上传。

        Args:
            request: 当前 HTTP 请求。
            upload_id: 上传会话 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        try:
            session = await runtime.uploads.get(tenant_id, upload_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return _upload_session_view(session)

    @router.put("/upload-sessions/{upload_id}/parts/{part_number}")
    async def put_resumable_upload_part(
        request: Request,
        upload_id: str,
        part_number: int,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 PUT /upload-sessions/{upload_id}/parts/{part_number} 请求，写入可续传上传分片。

        Args:
            request: 当前 HTTP 请求。
            upload_id: 上传会话 ID。
            part_number: 分片。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        sha256 = body.get("sha256")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if sha256 is not None and not isinstance(sha256, str):
            raise HTTPException(status_code=422, detail="sha256 must be a string")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            data = _decode_base64(body.get("content_base64"))
            session = await runtime.uploads.put_part(
                tenant_id,
                upload_id,
                part_number,
                data,
                sha256=sha256,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return _upload_session_view(session)

    @router.post("/upload-sessions/{upload_id}/complete")
    async def complete_resumable_upload(
        request: Request,
        upload_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /upload-sessions/{upload_id}/complete 请求，完成可续传上传。

        Args:
            request: 当前 HTTP 请求。
            upload_id: 上传会话 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            completion = await runtime.uploads.complete(tenant_id, upload_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

        attachment = await runtime.attachment_service.get_metadata(
            tenant_id,
            completion.upload_id,
        )
        if attachment is None:
            try:
                attachment = await runtime.attachment_service.register_stored_object(
                    tenant_id=tenant_id,
                    filename=completion.filename,
                    content_type=completion.content_type,
                    size_bytes=completion.size_bytes,
                    sha256=completion.sha256,
                    object_key=completion.object_key,
                    attachment_id=completion.upload_id,
                )
            except ValueError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
        session = await runtime.uploads.get(tenant_id, upload_id)
        return {
            "upload": _upload_session_view(session),
            "attachment": attachment.model_dump(mode="json"),
        }

    @router.get("/attachments/{attachment_id}")
    async def get_attachment(
        request: Request,
        attachment_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """处理 GET /attachments/{attachment_id} 请求，获取附件。

        Args:
            request: 当前 HTTP 请求。
            attachment_id: 附件 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        result = await runtime.attachment_service.get(tenant_id, attachment_id)
        if result is None:
            raise HTTPException(status_code=404, detail="Attachment not found")
        attachment, url = result
        return {**attachment.model_dump(mode="json"), "download_url": url}

    @router.post("/extractions/{extraction_id}/confirm")
    async def confirm_extraction(
        request: Request,
        extraction_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /extractions/{extraction_id}/confirm 请求，确认提取。

        Args:
            request: 当前 HTTP 请求。
            extraction_id: 提取 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        if runtime.ocr_service is None:
            raise HTTPException(status_code=503, detail="OCR provider is not configured")
        try:
            claim = await runtime.ocr_service.confirm(
                tenant_id=tenant_id,
                extraction_id=extraction_id,
                body=body,
                claim_service=runtime.service,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return claim.model_dump(mode="json")

    @router.post("/ocr-jobs")
    async def enqueue_ocr_job(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /ocr-jobs 请求，加入队列OCR任务。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        attachment_id = body.get("attachment_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(attachment_id, str) or not attachment_id:
            raise HTTPException(status_code=422, detail="attachment_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        if runtime.ocr_job_service is None:
            raise HTTPException(status_code=503, detail="OCR provider is not configured")
        try:
            job = await runtime.ocr_job_service.enqueue(tenant_id, attachment_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @router.post("/ocr-jobs/batch")
    async def enqueue_ocr_jobs(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /ocr-jobs/batch 请求，加入队列OCR任务。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        attachment_ids = body.get("attachment_ids")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(attachment_ids, list) or any(
            not isinstance(item, str) for item in attachment_ids
        ):
            raise HTTPException(status_code=422, detail="attachment_ids must be a list of strings")
        await _authorize_expense(runtime, request, tenant_id)
        if runtime.ocr_job_service is None:
            raise HTTPException(status_code=503, detail="OCR provider is not configured")
        jobs = await runtime.ocr_job_service.enqueue_batch(tenant_id, attachment_ids)
        return {"jobs": [job.model_dump(mode="json") for job in jobs]}

    @router.get("/ocr-jobs")
    async def list_ocr_jobs(
        request: Request,
        tenant_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """处理 GET /ocr-jobs 请求，查询OCR任务。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        if runtime.ocr_job_service is None:
            raise HTTPException(status_code=503, detail="OCR provider is not configured")
        jobs = await runtime.ocr_job_service.list(tenant_id, limit=min(max(limit, 1), 200))
        return {"jobs": [job.model_dump(mode="json") for job in jobs]}

    @router.get("/ocr-jobs/summary")
    async def ocr_job_summary(request: Request, tenant_id: str) -> dict[str, Any]:
        """处理 GET /ocr-jobs/summary 请求，查询OCR任务摘要。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        if runtime.ocr_job_service is None:
            raise HTTPException(status_code=503, detail="OCR provider is not configured")
        return await runtime.ocr_job_service.summary(tenant_id)

    @router.get("/ocr-jobs/{job_id}")
    async def get_ocr_job(request: Request, job_id: str, tenant_id: str) -> dict[str, Any]:
        """处理 GET /ocr-jobs/{job_id} 请求，获取OCR任务。

        Args:
            request: 当前 HTTP 请求。
            job_id: 任务 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        if runtime.ocr_job_service is None:
            raise HTTPException(status_code=503, detail="OCR provider is not configured")
        try:
            job = await runtime.ocr_job_service.get(tenant_id, job_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @router.post("/ocr-jobs/{job_id}/retry")
    async def retry_ocr_job(request: Request, job_id: str, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /ocr-jobs/{job_id}/retry 请求，重试OCR任务。

        Args:
            request: 当前 HTTP 请求。
            job_id: 任务 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        if runtime.ocr_job_service is None:
            raise HTTPException(status_code=503, detail="OCR provider is not configured")
        try:
            job = await runtime.ocr_job_service.retry(tenant_id, job_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @router.post("/imports")
    async def import_expense_documents(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /imports 请求，导入报销文档。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        files = body.get("files")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(files, list) or not files or len(files) > 50:
            raise HTTPException(status_code=422, detail="files must contain 1 to 50 items")
        if any(not isinstance(item, dict) for item in files):
            raise HTTPException(status_code=422, detail="each file must be an object")
        await _authorize_expense(runtime, request, tenant_id)
        batch = await runtime.import_service.create_batch(tenant_id, files)
        return batch.model_dump(mode="json")

    @router.get("/imports")
    async def list_import_batches(
        request: Request,
        tenant_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """处理 GET /imports 请求，查询导入批次。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。
        """
        await _authorize_expense(runtime, request, tenant_id)
        batches = await runtime.import_service.list(
            tenant_id,
            limit=min(max(limit, 1), 200),
        )
        return {"batches": [batch.model_dump(mode="json") for batch in batches]}

    @router.get("/imports/{batch_id}")
    async def get_import_batch(
        request: Request,
        batch_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """处理 GET /imports/{batch_id} 请求，获取导入批次。

        Args:
            request: 当前 HTTP 请求。
            batch_id: 批次 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        try:
            batch = await runtime.import_service.get(tenant_id, batch_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return batch.model_dump(mode="json")

    @router.post("/imports/{batch_id}/retry-failed")
    async def retry_failed_import_items(
        request: Request,
        batch_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /imports/{batch_id}/retry-failed 请求，重试失败导入条目。

        Args:
            request: 当前 HTTP 请求。
            batch_id: 批次 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            batch = await runtime.import_service.retry_failed(tenant_id, batch_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return batch.model_dump(mode="json")

    @router.post("/claims")
    async def create_claim(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /claims 请求，创建报销单。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            claim = await runtime.service.create_claim(body)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return claim.model_dump(mode="json")

    @router.post("/invoices/check-duplicate")
    async def check_invoice_duplicates(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /invoices/check-duplicate 请求，检查发票。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        invoices = _invoice_items(body)
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            result = await runtime.invoice_service.check_duplicates(tenant_id, invoices)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    @router.post("/claims/{claim_id}/invoices")
    async def register_claim_invoices(
        request: Request,
        claim_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /claims/{claim_id}/invoices 请求，注册报销单发票。

        Args:
            request: 当前 HTTP 请求。
            claim_id: 报销单 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        actor_id = body.get("actor_id")
        invoices = _invoice_items(body)
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(actor_id, str) or not actor_id:
            raise HTTPException(status_code=422, detail="actor_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            registered = await runtime.invoice_service.register_for_claim(
                tenant_id,
                claim_id,
                invoices,
                actor_id=actor_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"invoices": [invoice.model_dump(mode="json") for invoice in registered]}

    @router.get("/claims/{claim_id}/invoices")
    async def list_claim_invoices(
        request: Request,
        claim_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """处理 GET /claims/{claim_id}/invoices 请求，查询报销单发票。

        Args:
            request: 当前 HTTP 请求。
            claim_id: 报销单 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        await _authorize_expense(runtime, request, tenant_id)
        invoices = await runtime.invoice_service.list_for_claim(tenant_id, claim_id)
        return {"invoices": [invoice.model_dump(mode="json") for invoice in invoices]}

    @router.get("/claims/{claim_id}/invoice-readiness")
    async def get_claim_invoice_readiness(
        request: Request,
        claim_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """处理 GET /claims/{claim_id}/invoice-readiness 请求，获取报销单发票就绪状态。

        Args:
            request: 当前 HTTP 请求。
            claim_id: 报销单 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        claim = await runtime.service.get_claim(tenant_id, claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail="Expense claim not found")
        readiness = await runtime.invoice_service.evaluate_claim(tenant_id, claim)
        return readiness.model_dump(mode="json")

    @router.get("/invoices/gate-summary")
    async def get_invoice_gate_summary(
        request: Request,
        tenant_id: str,
    ) -> dict[str, Any]:
        """处理 GET /invoices/gate-summary 请求，获取发票门禁摘要。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        await _authorize_expense(runtime, request, tenant_id)
        summary = await runtime.invoice_service.gate_summary(tenant_id)
        return summary.model_dump(mode="json")

    @router.get("/invoices/gate-metrics")
    async def get_invoice_gate_metrics(
        request: Request,
        tenant_id: str,
    ) -> Response:
        """获取发票门禁指标。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            响应结果。
        """
        await _authorize_expense(runtime, request, tenant_id)
        summary = await runtime.invoice_service.gate_summary(tenant_id)
        return Response(
            content=_invoice_gate_metrics_text(summary),
            media_type="text/plain; version=0.0.4",
        )

    @router.post("/invoices/gate-alerts/scan")
    async def scan_invoice_gate_alerts(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /invoices/gate-alerts/scan 请求，扫描发票门禁告警。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        return await runtime.invoice_service.emit_gate_alerts(tenant_id)

    @router.post("/invoices/{invoice_id}/verify")
    async def verify_expense_invoice(
        request: Request,
        invoice_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /invoices/{invoice_id}/verify 请求，校验报销发票。

        Args:
            request: 当前 HTTP 请求。
            invoice_id: 发票 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        connector_id = body.get("connector_id")
        action = body.get("action", "invoice.verify")
        actor_id = body.get("actor_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(connector_id, str) or not connector_id:
            raise HTTPException(status_code=422, detail="connector_id is required")
        if not isinstance(action, str) or not action:
            raise HTTPException(status_code=422, detail="action is required")
        if not isinstance(actor_id, str) or not actor_id:
            raise HTTPException(status_code=422, detail="actor_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            result = await runtime.invoice_service.verify_invoice(
                tenant_id,
                invoice_id,
                connector_id=connector_id,
                action=action,
                actor_id=actor_id,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return result.model_dump(mode="json")

    @router.post("/invoices/{invoice_id}/release")
    async def release_expense_invoice(
        request: Request,
        invoice_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /invoices/{invoice_id}/release 请求，提交释放报销发票。

        Args:
            request: 当前 HTTP 请求。
            invoice_id: 发票 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        actor_id = body.get("actor_id")
        reason = body.get("reason")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(actor_id, str) or not actor_id:
            raise HTTPException(status_code=422, detail="actor_id is required")
        if not isinstance(reason, str) or not reason.strip():
            raise HTTPException(status_code=422, detail="reason is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            invoice = await runtime.invoice_service.release_invoice(
                tenant_id,
                invoice_id,
                actor_id=actor_id,
                reason=reason,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return invoice.model_dump(mode="json")

    @router.post("/extractions")
    async def extract_claim_fields(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /extractions 请求，提取报销单字段。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        if runtime.ocr_service is None:
            raise HTTPException(status_code=503, detail="OCR provider is not configured")
        attachment_id = body.get("attachment_id")
        try:
            if isinstance(attachment_id, str) and attachment_id:
                attachment = await runtime.attachment_service.get(tenant_id, attachment_id)
                if attachment is None:
                    raise HTTPException(status_code=404, detail="Attachment not found")
                metadata, _ = attachment
                content = await runtime.attachment_service.get_content(tenant_id, attachment_id)
                if content is None:
                    raise HTTPException(status_code=404, detail="Attachment content not found")
                content_type = metadata.content_type
            else:
                content = _decode_base64(body.get("content_base64"))
                content_type = str(body.get("content_type") or "")
            extraction = await runtime.ocr_service.extract(
                tenant_id,
                content,
                content_type,
                attachment_id if isinstance(attachment_id, str) else None,
            )
        except (ValueError, binascii.Error) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return extraction.model_dump(mode="json")

    @router.get("/claims")
    async def list_claims(
        request: Request,
        tenant_id: str,
        status: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """处理 GET /claims 请求，查询报销单。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            status: 目标状态。
            limit: 返回记录的最大数量。
            cursor: 分页游标。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        try:
            parsed_status = ExpenseClaimStatus(status) if status else None
            claims, next_cursor = await runtime.service.list_claims(
                tenant_id,
                status=parsed_status,
                limit=limit,
                cursor=cursor,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "claims": [claim.model_dump(mode="json") for claim in claims],
            "next_cursor": next_cursor,
        }

    @router.get("/policies")
    async def expense_policies(request: Request, tenant_id: str) -> dict[str, Any]:
        """处理 GET /policies 请求，查询报销策略。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        await _authorize_expense(runtime, request, tenant_id)
        return {"tenant_id": tenant_id, **runtime.service.describe_policy()}

    @router.get("/search")
    async def search_approved_expenses(
        request: Request,
        tenant_id: str,
        query: str,
        limit: int = 10,
    ) -> dict[str, Any]:
        """处理 GET /search 请求，搜索已批准报销单。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            query: 检索或筛选查询。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。
        """
        await _authorize_expense(runtime, request, tenant_id)
        results = await runtime.service.search_indexed(
            tenant_id,
            query,
            limit=min(max(limit, 1), 50),
        )
        return {
            "tenant_id": tenant_id,
            "query": query,
            "results": [result.model_dump(mode="json") for result in results],
        }

    @router.post("/answer")
    async def answer_expense_question(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """处理 POST /answer 请求，回答报销问题。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        question = body.get("question")
        limit = body.get("limit", 5)
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(question, str) or not question.strip():
            raise HTTPException(status_code=422, detail="question is required")
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 1 or limit > 20:
            raise HTTPException(status_code=422, detail="limit must be between 1 and 20")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            answer = await runtime.answer_service.answer(
                tenant_id,
                question,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "tenant_id": tenant_id,
            "question": question,
            **answer.model_dump(mode="json"),
        }

    @router.post("/claims/{claim_id}/index")
    async def index_approved_claim(
        request: Request,
        claim_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /claims/{claim_id}/index 请求，建立索引已批准报销单。

        Args:
            request: 当前 HTTP 请求。
            claim_id: 报销单 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            claim = await runtime.service.index_claim(tenant_id, claim_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return claim.model_dump(mode="json")

    @router.get("/ledger")
    async def expense_ledger(request: Request, tenant_id: str) -> dict[str, Any]:
        """处理 GET /ledger 请求，查询报销台账。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        await _authorize_expense(runtime, request, tenant_id)
        claims, total_amount_cents = await runtime.service.get_ledger(tenant_id)
        return {
            "tenant_id": tenant_id,
            "total_amount_cents": total_amount_cents,
            "claims": [claim.model_dump(mode="json") for claim in claims],
        }

    @router.get("/ledger/export")
    async def export_expense_ledger(
        request: Request,
        tenant_id: str,
        file_format: str = Query("csv", alias="format"),
    ) -> Any:
        """处理 GET /ledger/export 请求，导出报销台账。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            file_format: 文件格式化。

        Returns:
            处理结果对象。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        if file_format not in {"csv", "json"}:
            raise HTTPException(status_code=422, detail="format must be csv or json")
        try:
            claims = await runtime.ledger_service.list_approved(tenant_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        rows = [_ledger_export_row(claim) for claim in claims]
        if file_format == "json":
            return {
                "tenant_id": tenant_id,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "claims": rows,
            }

        output = io.StringIO(newline="")
        fieldnames = list(rows[0]) if rows else _LEDGER_EXPORT_FIELDS
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(
            {key: _csv_safe_value(value) for key, value in row.items()} for row in rows
        )
        response = Response(
            content=output.getvalue().encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8",
        )
        filename = f"expense-ledger-{_safe_filename_part(tenant_id)}.csv"
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response

    @router.post("/ledger/writeback")
    async def writeback_expense_ledger(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /ledger/writeback 请求，提交写回报销台账。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        connector_id = body.get("connector_id")
        action = body.get("action", "ledger.post")
        actor_id = body.get("actor_id")
        claim_ids = body.get("claim_ids")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(connector_id, str) or not connector_id:
            raise HTTPException(status_code=422, detail="connector_id is required")
        if not isinstance(action, str) or not action:
            raise HTTPException(status_code=422, detail="action is required")
        if not isinstance(actor_id, str) or not actor_id:
            raise HTTPException(status_code=422, detail="actor_id is required")
        if claim_ids is not None and (
            not isinstance(claim_ids, list)
            or any(not isinstance(claim_id, str) or not claim_id for claim_id in claim_ids)
        ):
            raise HTTPException(status_code=422, detail="claim_ids must be a list of strings")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            batch = await runtime.ledger_service.writeback(
                tenant_id,
                connector_id=connector_id,
                action=action,
                actor_id=actor_id,
                claim_ids=claim_ids,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return batch.model_dump(mode="json")

    @router.post("/ledger/writebacks/verify")
    async def verify_expense_writebacks(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /ledger/writebacks/verify 请求，校验报销写回。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id, connector_id, action, actor_id, claim_ids = _writeback_request(body)
        lookup_action = body.get("lookup_action", "ledger.lookup")
        if not isinstance(lookup_action, str) or not lookup_action:
            raise HTTPException(status_code=422, detail="lookup_action is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            batch = await runtime.ledger_service.verify_writebacks(
                tenant_id,
                connector_id=connector_id,
                action=action,
                lookup_action=lookup_action,
                actor_id=actor_id,
                claim_ids=claim_ids,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return batch.model_dump(mode="json")

    @router.post("/ledger/writebacks/compensate")
    async def compensate_expense_writebacks(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /ledger/writebacks/compensate 请求，补偿报销写回。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id, connector_id, action, actor_id, claim_ids = _writeback_request(body)
        compensation_action = body.get("compensation_action", "ledger.compensate")
        reason = body.get("reason")
        if not isinstance(compensation_action, str) or not compensation_action:
            raise HTTPException(status_code=422, detail="compensation_action is required")
        if not isinstance(reason, str) or not reason.strip():
            raise HTTPException(status_code=422, detail="reason is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            batch = await runtime.ledger_service.compensate_writebacks(
                tenant_id,
                connector_id=connector_id,
                action=action,
                compensation_action=compensation_action,
                actor_id=actor_id,
                reason=reason,
                claim_ids=claim_ids,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return batch.model_dump(mode="json")

    @router.get("/ledger/reconciliation")
    async def reconcile_expense_ledger(
        request: Request,
        tenant_id: str,
        connector_id: str | None = None,
    ) -> dict[str, Any]:
        """处理 GET /ledger/reconciliation 请求，核对报销台账。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            connector_id: 连接器 ID。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        try:
            reconciliation = await runtime.ledger_service.reconcile(tenant_id, connector_id)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return reconciliation.model_dump(mode="json")

    @router.post("/ledger/writeback-jobs")
    async def enqueue_writeback_job(
        request: Request,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /ledger/writeback-jobs 请求，加入队列写回任务。

        Args:
            request: 当前 HTTP 请求。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id, connector_id, action, actor_id, claim_ids = _writeback_request(body)
        await _authorize_expense(runtime, request, tenant_id)
        try:
            job = await runtime.writeback_job_service.enqueue(
                tenant_id,
                connector_id=connector_id,
                action=action,
                actor_id=actor_id,
                claim_ids=claim_ids,
            )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @router.get("/ledger/writeback-jobs")
    async def list_writeback_jobs(
        request: Request,
        tenant_id: str,
        limit: int = 100,
    ) -> dict[str, Any]:
        """处理 GET /ledger/writeback-jobs 请求，查询写回任务。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。
            limit: 返回记录的最大数量。

        Returns:
            结构化结果字典。
        """
        await _authorize_expense(runtime, request, tenant_id)
        jobs = await runtime.writeback_job_service.list(
            tenant_id,
            limit=min(max(limit, 1), 200),
        )
        return {
            "jobs": [
                {
                    **job.model_dump(mode="json", exclude={"items", "claim_ids"}),
                    "claim_count": len(job.claim_ids),
                }
                for job in jobs
            ]
        }

    @router.get("/ledger/writeback-jobs/summary")
    async def writeback_job_summary(request: Request, tenant_id: str) -> dict[str, Any]:
        """处理 GET /ledger/writeback-jobs/summary 请求，查询写回任务摘要。

        Args:
            request: 当前 HTTP 请求。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。
        """
        await _authorize_expense(runtime, request, tenant_id)
        return await runtime.writeback_job_service.summary(tenant_id)

    @router.get("/ledger/writeback-jobs/{job_id}")
    async def get_writeback_job(
        request: Request,
        job_id: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        """处理 GET /ledger/writeback-jobs/{job_id} 请求，获取写回任务。

        Args:
            request: 当前 HTTP 请求。
            job_id: 任务 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        try:
            job = await runtime.writeback_job_service.get(tenant_id, job_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @router.post("/ledger/writeback-jobs/{job_id}/retry-failed")
    async def retry_failed_writeback_job(
        request: Request,
        job_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /ledger/writeback-jobs/{job_id}/retry-failed 请求，重试失败写回任务。

        Args:
            request: 当前 HTTP 请求。
            job_id: 任务 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            job = await runtime.writeback_job_service.retry_failed(tenant_id, job_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return job.model_dump(mode="json")

    @router.post("/claims/{claim_id}/decision")
    async def decide_claim(
        request: Request,
        claim_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /claims/{claim_id}/decision 请求，处理报销单。

        Args:
            request: 当前 HTTP 请求。
            claim_id: 报销单 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        decided_by = body.get("decided_by")
        decision = body.get("decision")
        reason = body.get("reason", "")
        override_reason = body.get("override_reason", "")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        if not isinstance(decided_by, str) or not decided_by:
            raise HTTPException(status_code=422, detail="decided_by is required")
        if decision not in {"approve", "reject"}:
            raise HTTPException(status_code=422, detail="decision must be approve or reject")
        if not isinstance(reason, str):
            raise HTTPException(status_code=422, detail="reason must be a string")
        if not isinstance(override_reason, str):
            raise HTTPException(status_code=422, detail="override_reason must be a string")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            claim = await runtime.service.decide_claim(
                tenant_id,
                claim_id,
                decision=decision,
                approver_id=decided_by,
                reason=reason,
                override_reason=override_reason,
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return claim.model_dump(mode="json")

    @router.get("/claims/{claim_id}")
    async def get_claim(request: Request, claim_id: str, tenant_id: str) -> dict[str, Any]:
        """处理 GET /claims/{claim_id} 请求，获取报销单。

        Args:
            request: 当前 HTTP 请求。
            claim_id: 报销单 ID。
            tenant_id: 租户 ID，用于数据隔离。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        await _authorize_expense(runtime, request, tenant_id)
        claim = await runtime.service.get_claim(tenant_id, claim_id)
        if claim is None:
            raise HTTPException(status_code=404, detail="Expense claim not found")
        return claim.model_dump(mode="json")

    @router.post("/claims/{claim_id}/submit")
    async def submit_claim(
        request: Request,
        claim_id: str,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """处理 POST /claims/{claim_id}/submit 请求，提交报销单。

        Args:
            request: 当前 HTTP 请求。
            claim_id: 报销单 ID。
            body: 请求体数据。

        Returns:
            结构化结果字典。

        Raises:
            HTTPException: 请求参数、状态或依赖不满足要求时抛出。
        """
        tenant_id = body.get("tenant_id")
        if not isinstance(tenant_id, str) or not tenant_id:
            raise HTTPException(status_code=422, detail="tenant_id is required")
        await _authorize_expense(runtime, request, tenant_id)
        try:
            claim = await runtime.service.submit_claim(tenant_id, claim_id)
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return claim.model_dump(mode="json")

    return router


def _decode_base64(value: Any) -> bytes:
    """解码 Base64 数据。

    Args:
        value: 待处理值。

    Returns:
        处理结果对象。

    Raises:
        ValueError: 输入值或业务状态不合法时抛出。
    """
    if not isinstance(value, str) or not value:
        raise ValueError("content_base64 is required")
    return base64.b64decode(value, validate=True)


def _upload_session_view(session: UploadSession) -> dict[str, Any]:
    """上传会话视图。

    Args:
        session: 当前会话。

    Returns:
        结构化结果字典。
    """
    received_bytes = sum(part.size_bytes for part in session.parts)
    return {
        "upload_id": session.upload_id,
        "tenant_id": session.tenant_id,
        "owner_module": session.owner_module,
        "filename": session.filename,
        "content_type": session.content_type,
        "size_bytes": session.size_bytes,
        "chunk_size": session.chunk_size,
        "total_chunks": session.total_chunks,
        "received_chunks": len(session.parts),
        "received_bytes": received_bytes,
        "progress": round(received_bytes / session.size_bytes, 4),
        "received_parts": [
            {
                "part_number": part.part_number,
                "size_bytes": part.size_bytes,
                "sha256": part.sha256,
            }
            for part in session.parts
        ],
        "status": session.status.value,
        "expected_sha256": session.expected_sha256,
        "completed_sha256": session.completed_sha256,
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
        "expires_at": session.expires_at.isoformat(),
    }


_LEDGER_EXPORT_FIELDS = [
    "claim_id",
    "tenant_id",
    "applicant_id",
    "amount_cents",
    "currency",
    "expense_date",
    "category",
    "description",
    "invoice_count",
    "approved_by",
    "approved_at",
    "writeback_status",
    "writeback_connector",
    "writeback_action",
    "writeback_external_id",
    "writeback_error",
    "writeback_at",
    "verification_status",
    "verification_external_id",
    "verification_message",
    "verified_at",
    "compensation_id",
    "compensated_at",
    "compensation_reason",
]


def _ledger_export_row(claim: ExpenseClaim) -> dict[str, str | int]:
    """将报销单转换为台账导出行。

    Args:
        claim: 报销单对象。

    Returns:
        结构化结果字典。
    """
    approval = claim.metadata.get("approval")
    approval = approval if isinstance(approval, dict) else {}
    writeback = claim.metadata.get("last_writeback")
    writeback = writeback if isinstance(writeback, dict) else {}
    verification = claim.metadata.get("last_writeback_verification")
    verification = verification if isinstance(verification, dict) else {}
    return {
        "claim_id": claim.claim_id,
        "tenant_id": claim.tenant_id,
        "applicant_id": claim.applicant_id,
        "amount_cents": claim.amount_cents,
        "currency": claim.currency,
        "expense_date": claim.expense_date.isoformat(),
        "category": claim.category,
        "description": claim.description,
        "invoice_count": claim.invoice_count,
        "approved_by": str(approval.get("decided_by") or ""),
        "approved_at": str(approval.get("decided_at") or ""),
        "writeback_status": str(writeback.get("status") or "pending"),
        "writeback_connector": str(writeback.get("connector_id") or ""),
        "writeback_action": str(writeback.get("action") or ""),
        "writeback_external_id": str(writeback.get("external_id") or ""),
        "writeback_error": str(writeback.get("error") or ""),
        "writeback_at": str(writeback.get("attempted_at") or ""),
        "verification_status": str(verification.get("status") or ""),
        "verification_external_id": str(verification.get("external_id") or ""),
        "verification_message": str(verification.get("message") or ""),
        "verified_at": str(verification.get("checked_at") or ""),
        "compensation_id": str(writeback.get("compensation_id") or ""),
        "compensated_at": str(writeback.get("compensated_at") or ""),
        "compensation_reason": str(writeback.get("compensation_reason") or ""),
    }


def _safe_filename_part(value: str) -> str:
    """生成可安全用于文件名的片段。

    Args:
        value: 待处理值。

    Returns:
        字符串结果。
    """
    return (
        "".join(
            char if char.isascii() and (char.isalnum() or char in "._-") else "_" for char in value
        )
        or "tenant"
    )


def _csv_safe_value(value: str | int) -> str | int:
    """转义可能触发表格公式的 CSV 单元格。

    Args:
        value: 待处理值。

    Returns:
        整数结果。
    """
    if isinstance(value, str) and value.startswith(("=", "+", "-", "@", "\t", "\r")):
        return f"'{value}"
    return value


def _writeback_request(
    body: dict[str, Any],
) -> tuple[str, str, str, str, list[str] | None]:
    """执行写回请求。

    Args:
        body: 请求体数据。

    Returns:
        结果元组。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    tenant_id = body.get("tenant_id")
    connector_id = body.get("connector_id")
    action = body.get("action", "ledger.post")
    actor_id = body.get("actor_id")
    claim_ids = body.get("claim_ids")
    if not isinstance(tenant_id, str) or not tenant_id:
        raise HTTPException(status_code=422, detail="tenant_id is required")
    if not isinstance(connector_id, str) or not connector_id:
        raise HTTPException(status_code=422, detail="connector_id is required")
    if not isinstance(action, str) or not action:
        raise HTTPException(status_code=422, detail="action is required")
    if not isinstance(actor_id, str) or not actor_id:
        raise HTTPException(status_code=422, detail="actor_id is required")
    if claim_ids is not None and (
        not isinstance(claim_ids, list)
        or any(not isinstance(claim_id, str) or not claim_id for claim_id in claim_ids)
    ):
        raise HTTPException(status_code=422, detail="claim_ids must be a list of strings")
    return tenant_id, connector_id, action, actor_id, claim_ids


def _invoice_items(body: dict[str, Any]) -> list[dict[str, Any]]:
    """处理发票条目。

    Args:
        body: 请求体数据。

    Returns:
        结果列表。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    invoices = body.get("invoices")
    if not isinstance(invoices, list) or not invoices or len(invoices) > 200:
        raise HTTPException(status_code=422, detail="invoices must contain 1 to 200 items")
    if any(not isinstance(invoice, dict) for invoice in invoices):
        raise HTTPException(status_code=422, detail="each invoice must be an object")
    return invoices


def _invoice_gate_metrics_text(summary: InvoiceGateSummary) -> str:
    """生成发票门禁指标文本。

    Args:
        summary: 摘要。

    Returns:
        字符串结果。
    """
    tenant = _prometheus_label(summary.tenant_id)
    lines = [
        "# HELP agentforge_expense_invoice_gate_claims Current claims by invoice readiness state.",
        "# TYPE agentforge_expense_invoice_gate_claims gauge",
        f'agentforge_expense_invoice_gate_claims{{tenant_id="{tenant}",state="ready"}} '
        f"{summary.ready_claims}",
        f'agentforge_expense_invoice_gate_claims{{tenant_id="{tenant}",state="not_ready"}} '
        f"{summary.not_ready_claims}",
        "# HELP agentforge_expense_invoice_gate_blocked_attempts Total blocked approval attempts.",
        "# TYPE agentforge_expense_invoice_gate_blocked_attempts gauge",
        f'agentforge_expense_invoice_gate_blocked_attempts{{tenant_id="{tenant}"}} '
        f"{summary.blocked_attempts}",
        "# HELP agentforge_expense_invoice_gate_overrides "
        "Claims approved through invoice override.",
        "# TYPE agentforge_expense_invoice_gate_overrides gauge",
        f'agentforge_expense_invoice_gate_overrides{{tenant_id="{tenant}"}} '
        f"{summary.override_claims}",
        "# HELP agentforge_expense_invoice_gate_oldest_block_age_seconds "
        "Age of oldest blocked claim.",
        "# TYPE agentforge_expense_invoice_gate_oldest_block_age_seconds gauge",
        f'agentforge_expense_invoice_gate_oldest_block_age_seconds{{tenant_id="{tenant}"}} '
        f"{summary.oldest_blocked_age_seconds:.3f}",
        "# HELP agentforge_expense_invoice_gate_reason_claims Claims currently blocked by reason.",
        "# TYPE agentforge_expense_invoice_gate_reason_claims gauge",
    ]
    for reason, count in sorted(summary.reason_counts.items()):
        lines.append(
            f'agentforge_expense_invoice_gate_reason_claims{{tenant_id="{tenant}",'
            f'reason="{_prometheus_label(reason)}"}} {count}'
        )
    lines.extend(
        [
            "# HELP agentforge_expense_invoice_gate_alert Active invoice gate operational alerts.",
            "# TYPE agentforge_expense_invoice_gate_alert gauge",
        ]
    )
    for alert in summary.alerts:
        lines.append(
            f'agentforge_expense_invoice_gate_alert{{tenant_id="{tenant}",'
            f'type="{_prometheus_label(alert.type)}",'
            f'severity="{_prometheus_label(alert.severity)}"}} 1'
        )
    return "\n".join(lines) + "\n"


def _prometheus_label(value: str) -> str:
    """将标签值转换为 Prometheus 安全格式。

    Args:
        value: 待处理值。

    Returns:
        字符串结果。
    """
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


async def _authorize_expense(
    runtime: ExpenseRouterContext,
    request: Request,
    tenant_id: str,
) -> None:
    """授权报销。

    Args:
        runtime: 运行时容器。
        request: 当前 HTTP 请求。
        tenant_id: 租户 ID，用于数据隔离。

    Raises:
        HTTPException: 请求参数、状态或依赖不满足要求时抛出。
    """
    runtime.authenticator.authorize_tenant(request, tenant_id)
    if not await runtime.module_access.is_enabled(tenant_id, "expense"):
        raise HTTPException(status_code=403, detail="Expense module is not enabled for tenant")
