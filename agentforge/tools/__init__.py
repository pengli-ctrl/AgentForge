"""AgentForge 工具模块 — 工具统一接口和实现。"""

from agentforge.core.base_tool import BaseTool, ToolRegistry, ToolResult
from agentforge.tools.code_review_tool import CodeReviewTool
from agentforge.tools.doc_generation_tool import DocGenerationTool
from agentforge.tools.file_io_tool import FileIOTool
from agentforge.tools.git_tool import GitTool
from agentforge.tools.security_scan_tool import SecurityScanTool
from agentforge.tools.test_execution_tool import TestExecutionTool

__all__ = [
    "BaseTool",
    "ToolResult",
    "ToolRegistry",
    "CodeReviewTool",
    "TestExecutionTool",
    "DocGenerationTool",
    "SecurityScanTool",
    "GitTool",
    "FileIOTool",
]
