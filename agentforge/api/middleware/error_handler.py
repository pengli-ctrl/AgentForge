"""统一错误处理中间件 — 全局异常捕获和标准化错误响应。

所有未处理的异常被捕获后转换为标准化的 JSON 错误响应，
避免暴露内部实现细节。

错误响应格式：
    {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal error occurred",
            "detail": "..."  // 仅在 DEBUG 模式下包含
        }
    }
"""

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
        code: 错误码（如 NOT_FOUND、VALIDATION_ERROR）。
        message: 用户可见的错误消息。
        status_code: HTTP 状态码。
        detail: 详细信息（仅 DEBUG 模式返回给客户端）。
    """

    code: str
    message: str
    status_code: int = 500
    detail: str = ""

    def to_dict(self, include_detail: bool = False) -> dict[str, Any]:
        """转换为字典格式。

        Args:
            include_detail: 是否包含详细错误信息。

        Returns:
            标准化的错误字典。
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

    捕获所有未处理的异常，转换为标准化错误响应。
    在 DEBUG 模式下包含详细的错误堆栈信息。

    Args:
        debug: 是否启用 DEBUG 模式（包含详细错误信息）。
    """

    # 已知异常到 APIError 的映射
    EXCEPTION_MAP: dict[type[Exception], APIError] = {
        FileNotFoundError: NOT_FOUND,
        ValueError: VALIDATION_ERROR,
        PermissionError: UNAUTHORIZED,
    }

    def __init__(self, debug: bool = False) -> None:
        self.debug = debug

    def handle_exception(self, exc: Exception) -> APIError:
        """处理异常，返回标准化的 APIError。

        Args:
            exc: 捕获的异常。

        Returns:
            标准化的 APIError。
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
        """处理已知的 APIError。

        Args:
            error: APIError 实例。

        Returns:
            处理后的 APIError（可能附加 detail）。
        """
        if self.debug and not error.detail:
            error.detail = traceback.format_exc()
        return error
