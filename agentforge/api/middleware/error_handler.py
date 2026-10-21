"""错误处理器模块。"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class APIError(Exception):
    """API 错误 — 标准化的错误响应。

    Attributes:
        code: 业务代码。
        message: 消息内容。
        status_code: 状态代码。
        detail: 详情。
    """

    code: str
    message: str
    status_code: int = 500
    detail: str = ""

    def to_dict(self, include_detail: bool = False) -> dict[str, Any]:
        """转换为字典格式。

        Args:
            include_detail: 详情。

        Returns:
            结构化结果字典。
        """
        error_dict: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }
        if include_detail and self.detail:
            error_dict["detail"] = self.detail
        return {"error": error_dict}


# 预定义错误
NOT_FOUND = APIError(
    code="NOT_FOUND",
    message="Resource not found",
    status_code=404,
)

VALIDATION_ERROR = APIError(
    code="VALIDATION_ERROR",
    message="Request validation failed",
    status_code=422,
)

UNAUTHORIZED = APIError(
    code="UNAUTHORIZED",
    message="Authentication required",
    status_code=401,
)

FORBIDDEN = APIError(
    code="FORBIDDEN",
    message="Permission denied",
    status_code=403,
)

RATE_LIMITED = APIError(
    code="RATE_LIMITED",
    message="Rate limit exceeded. Please retry later.",
    status_code=429,
)

INVALID_STATE_TRANSITION = APIError(
    code="INVALID_STATE_TRANSITION",
    message="Invalid task state transition",
    status_code=409,
)

INTERNAL_ERROR = APIError(
    code="INTERNAL_ERROR",
    message="An internal error occurred",
    status_code=500,
)


class ErrorHandlerMiddleware:
    """统一错误处理中间件。

    Attributes:
        EXCEPTION_MAP: 异常。
    """

    # 已知异常到 APIError 的映射。
    # 注意：不要将 ValueError 盲目映射为客户端 422 —— 内部业务异常
    # （如 TaskStore.update_status 抛出的 "Invalid status transition"）
    # 属于服务端逻辑错误，应保留为 500 而非伪装成客户端校验失败，
    # 否则会掩盖服务端 bug。异常的显式校验错误应通过 APIError 抛出。
    EXCEPTION_MAP: dict[type[Exception], APIError] = {
        FileNotFoundError: NOT_FOUND,
        PermissionError: FORBIDDEN,
    }

    def __init__(self, debug: bool = False) -> None:
        """初始化 ErrorHandlerMiddleware。

        Args:
            debug: 调试。
        """
        self.debug = debug

    def handle_exception(self, exc: Exception) -> APIError:
        """处理异常。

        Args:
            exc: 输入参数。

        Returns:
            处理结果对象。
        """
        # 查找已知异常类型
        for exc_type, api_error in self.EXCEPTION_MAP.items():
            if isinstance(exc, exc_type):
                error = APIError(
                    code=api_error.code,
                    message=str(exc) or api_error.message,
                    status_code=api_error.status_code,
                )
                if self.debug:
                    error.detail = traceback.format_exc()
                logger.error(
                    "API error (code=%s, message=%s)",
                    error.code,
                    error.message,
                    exc_info=True,
                )
                return error

        # 未知异常 → 内部错误
        error = APIError(
            code=INTERNAL_ERROR.code,
            message=INTERNAL_ERROR.message,
            status_code=INTERNAL_ERROR.status_code,
        )
        if self.debug:
            error.detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"

        logger.error(
            "Unhandled exception (type=%s, message=%s)",
            type(exc).__name__,
            str(exc),
            exc_info=True,
        )

        return error

    def handle_api_error(self, error: APIError) -> APIError:
        """处理API错误。

        Args:
            error: 错误。

        Returns:
            处理结果对象。
        """
        if self.debug and not error.detail:
            error.detail = traceback.format_exc()
        return error
