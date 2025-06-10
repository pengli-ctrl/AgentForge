"""AgentForge API 层 — FastAPI REST 接口。

提供任务提交、状态查询、结果获取、Agent 管理和指标暴露的 REST API。

核心组件：
- app：FastAPI 应用入口
- routes/tasks：任务管理接口
- routes/agents：Agent 管理接口
- routes/metrics：Prometheus 指标接口
- middleware/auth：API Key 认证
- middleware/rate_limit：令牌桶限流
- middleware/error_handler：统一错误处理
"""

from agentforge.api.app import create_app

__all__ = ["create_app"]
