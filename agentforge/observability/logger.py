"""结构化日志 — JSON 格式，含 correlation_id、agent_name、event_type。

用于全链路可观测性（Layer 4 容错防线）。
所有日志输出为 JSON 格式，包含追踪上下文信息，
便于在 ELK/Loki 等日志聚合系统中检索和分析。

日志字段：
- timestamp: 时间戳（ISO 8601 格式）
- level: 日志级别
- logger: logger 名称
- message: 日志消息
- correlation_id: 关联 ID
- agent_name: Agent 名称
- event_type: 事件类型
- extra: 额外字段
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

# 自定义日志字段类型
_TRACE_FIELDS = {
    "correlation_id",
    "agent_name",
    "event_type",
    "trace_id",
    "span_id",
    "task_id",
    "workflow_name",
}


class StructuredFormatter(logging.Formatter):
    """JSON 结构化日志格式化器。

    将日志记录格式化为 JSON 字符串，包含时间戳、级别、消息
    和追踪上下文字段。
    """

    def format(self, record: logging.LogRecord) -> str:
        """将日志记录格式化为 JSON 字符串。

        Args:
            record: 日志记录。

        Returns:
            JSON 格式的日志字符串。
        """
        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 提取追踪上下文字段
        for field_name in _TRACE_FIELDS:
            value = getattr(record, field_name, None)
            if value:
                log_entry[field_name] = value

        # 提取额外字段（通过 extra 参数传入的）
        if hasattr(record, "extra_data"):
            log_entry["extra"] = record.extra_data

        # 异常信息
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        # 文件位置（仅 DEBUG 级别）
        if record.levelno <= logging.DEBUG:
            log_entry["module"] = record.module
            log_entry["line"] = record.lineno

        return json.dumps(log_entry, ensure_ascii=False, default=str)


class StructuredLogger:
    """结构化日志记录器 — 提供 JSON 格式的日志输出。

    封装标准 logging.Logger，自动注入追踪上下文字段。

    Args:
        name: logger 名称。
        level: 日志级别。
        use_json: 是否使用 JSON 格式（False 时使用普通文本格式）。
    """

    def __init__(
        self,
        name: str = "agentforge",
        level: int = logging.INFO,
        use_json: bool = True,
    ) -> None:
        """初始化实例，并保存运行所需的依赖、配置和内部状态。

        Args:
            name: str，调用方传入的 name 参数。
            level: int，调用方传入的 level 参数。
            use_json: bool，调用方传入的 use_json 参数。

        Returns:
            None，函数执行后的结果。
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        # 避免重复添加 handler
        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            if use_json:
                handler.setFormatter(StructuredFormatter())
            else:
                handler.setFormatter(
                    logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s")
                )
            self.logger.addHandler(handler)

        self.logger.propagate = False

    def _log(
        self,
        level: int,
        message: str,
        correlation_id: str = "",
        agent_name: str = "",
        event_type: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录日志（内部方法）。

        Args:
            level: 日志级别。
            message: 日志消息。
            correlation_id: 关联 ID。
            agent_name: Agent 名称。
            event_type: 事件类型。
            extra: 额外字段。
        """
        extra_data: dict[str, Any] = {}
        if correlation_id:
            extra_data["correlation_id"] = correlation_id
        if agent_name:
            extra_data["agent_name"] = agent_name
        if event_type:
            extra_data["event_type"] = event_type
        if extra:
            extra_data["extra"] = extra

        self.logger.log(level, message, extra=extra_data or None)

    def debug(
        self,
        message: str,
        correlation_id: str = "",
        agent_name: str = "",
        event_type: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录 DEBUG 级别日志。

        Args:
            message: 日志消息。
            correlation_id: 关联 ID。
            agent_name: Agent 名称。
            event_type: 事件类型。
            extra: 额外字段。
        """
        self._log(logging.DEBUG, message, correlation_id, agent_name, event_type, extra)

    def info(
        self,
        message: str,
        correlation_id: str = "",
        agent_name: str = "",
        event_type: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录 INFO 级别日志。

        Args:
            message: 日志消息。
            correlation_id: 关联 ID。
            agent_name: Agent 名称。
            event_type: 事件类型。
            extra: 额外字段。
        """
        self._log(logging.INFO, message, correlation_id, agent_name, event_type, extra)

    def warning(
        self,
        message: str,
        correlation_id: str = "",
        agent_name: str = "",
        event_type: str = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """记录 WARNING 级别日志。

        Args:
            message: 日志消息。
            correlation_id: 关联 ID。
            agent_name: Agent 名称。
            event_type: 事件类型。
            extra: 额外字段。
        """
        self._log(logging.WARNING, message, correlation_id, agent_name, event_type, extra)

    def error(
        self,
        message: str,
        correlation_id: str = "",
        agent_name: str = "",
        event_type: str = "",
        extra: dict[str, Any] | None = None,
        exc_info: bool = False,
    ) -> None:
        """记录 ERROR 级别日志。

        Args:
            message: 日志消息。
            correlation_id: 关联 ID。
            agent_name: Agent 名称。
            event_type: 事件类型。
            extra: 额外字段。
            exc_info: 是否包含异常堆栈。
        """
        extra_data: dict[str, Any] = {}
        if correlation_id:
            extra_data["correlation_id"] = correlation_id
        if agent_name:
            extra_data["agent_name"] = agent_name
        if event_type:
            extra_data["event_type"] = event_type
        if extra:
            extra_data["extra"] = extra

        self.logger.error(message, extra=extra_data or None, exc_info=exc_info)


# 全局 logger 单例
_logger: StructuredLogger | None = None


def get_logger(name: str = "agentforge") -> StructuredLogger:
    """读取并返回指定数据，并返回调用方需要的结果。

    Args:
        name: str，调用方传入的 name 参数。

    Returns:
        StructuredLogger，函数执行后的结果。
    """
    global _logger
    if _logger is None:
        _logger = StructuredLogger(name)
    return _logger
