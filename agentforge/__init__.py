"""
AgentForge — 事件驱动的多 Agent 编排框架。

从单 Agent PoC 到事件驱动架构的完整演进实践，核心模块包括：
- 事件总线（EventBus）
- Context Snapshot 隔离
- 动态路由引擎（WorkflowEngine）
- 工具抽象层（BaseTool）
- RAG 工程化（AST 分块 + 混合检索 + 幻觉防护）
- 四层容错防线（Trust Boundary / Conflict Arbiter / AIMD / Pulse Shaper）
- API 层（FastAPI REST 接口）
- 存储层（TaskStore / TraceStore / RedisStateStore）
- 可观测性（Prometheus 指标 / 分布式追踪 / 结构化日志）
- SDK（AgentForgeClient / AgentBuilder）
- CLI（命令行工具）

Example:
    >>> from agentforge.core.event_bus import EventBus
    >>> bus = EventBus(backend="redis")
"""

__version__ = "3.0.0"
__author__ = "彭黎"
__email__ = "pl2847253@gmail.com"

__all__ = [
    "core",
    "llm",
    "tools",
    "agents",
    "rag",
    "safety",
    "api",
    "storage",
    "observability",
    "workflow",
    "prompts",
    "sdk",
    "cli",
]
