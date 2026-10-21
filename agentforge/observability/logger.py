"""日志器模块。"""

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
    """结构化格式化器相关组件。"""

    def format(self, record: logging.LogRecord) -> str:
        """格式化结构化格式化器。

        Args:
            record: 待处理的领域记录。

        Returns:
            字符串结果。
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
    """结构化日志器相关组件。"""

    def __init__(
        self,
        name: str = "agentforge",
        level: int = logging.INFO,
        use_json: bool = True,
    ) -> None:
        """初始化 StructuredLogger。

        Args:
            name: 资源或对象名称。
            level: 级别。
            use_json: JSON。
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
            level: 级别。
            message: 输入参数。
            correlation_id: 用于关联同一业务链路的关联 ID。
            agent_name: 智能体名称。
            event_type: 事件类型。
            extra: 输入参数。
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
        """输出调试级别日志。

        Args:
            message: 输入参数。
            correlation_id: 用于关联同一业务链路的关联 ID。
            agent_name: 智能体名称。
            event_type: 事件类型。
            extra: 输入参数。
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
        """执行信息。

        Args:
            message: 输入参数。
            correlation_id: 用于关联同一业务链路的关联 ID。
            agent_name: 智能体名称。
            event_type: 事件类型。
            extra: 输入参数。
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
        """输出警告级别日志。

        Args:
            message: 输入参数。
            correlation_id: 用于关联同一业务链路的关联 ID。
            agent_name: 智能体名称。
            event_type: 事件类型。
            extra: 输入参数。
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
        """执行错误。

        Args:
            message: 输入参数。
            correlation_id: 用于关联同一业务链路的关联 ID。
            agent_name: 智能体名称。
            event_type: 事件类型。
            extra: 输入参数。
            exc_info: 输入参数。
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
    """获取日志器。

    Args:
        name: 资源或对象名称。

    Returns:
        结构化日志器结果。
    """
    global _logger
    if _logger is None:
        _logger = StructuredLogger(name)
    return _logger
