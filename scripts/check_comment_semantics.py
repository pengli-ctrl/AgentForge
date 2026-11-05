"""校验新增注释与实现语义一致。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = {
    "agentforge/orchestration/graph_validator.py": ("DAG", "校验"),
    "agentforge/orchestration/temporal_dag.py": ("DAG", "执行"),
    "agentforge/platform/api/security.py": ("OIDC", "认证"),
    "agentforge/platform/api/rate_limit_middleware.py": ("限流", "请求"),
    "agentforge/platform/infrastructure/context_store.py": ("上下文", "Redis"),
    "agentforge/platform/infrastructure/rate_limit.py": ("限流", "后端"),
    "agentforge/platform/infrastructure/authz/opa_adapter.py": ("OPA", "授权"),
    "agentforge/platform/infrastructure/llm/gateway_factory.py": ("模型网关", "配置"),
    "agentforge/platform/infrastructure/prompt/langfuse_adapter.py": ("Langfuse", "提示词"),
    "agentforge/platform/observability/genai.py": ("GenAI", "链路"),
    "agentforge/platform/application/evaluation_harness.py": ("评测", "指标"),
    "agentforge/rag/parser.py": ("解析", "文档"),
    "agentforge/rag/parser_adapters.py": ("解析", "适配器"),
}
BANNED = ["提供" + "架构升级适配", "输入" + "参数。", "处理" + "结果。", "结果" + "结果", "相关" + "组件。", "相关" + "逻辑。"]
issues = []
for name, words in EXPECTED.items():
    path = ROOT / name
    text = path.read_text(encoding="utf-8")
    for phrase in BANNED:
        if phrase in text:
            issues.append(f"{name}: banned phrase {phrase}")
    first = text.splitlines()[0] if text.splitlines() else ""
    if not all(word in first for word in words):
        issues.append(f"{name}: summary must mention {words}")
if issues:
    raise SystemExit("comments are not semantically aligned: " + "; ".join(issues))
print("comment semantic gate passed")
