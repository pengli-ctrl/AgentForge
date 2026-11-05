from agentforge.platform.settings import Settings
from agentforge.platform.sdk.upgrade_ports import AuthPort, ContextStorePort, DagExecutorPort, PolicyPort, PromptRegistryPort, RagParserPort, RateLimitPort


def test_upgrade_settings_defaults_are_backward_compatible() -> None:
    settings = Settings(_env_file=None)
    assert settings.edge_gateway_provider == "ingress"
    assert settings.auth_mode == "api_key"
    assert settings.authz_engine == "local"
    assert settings.rate_limit_backend == "memory"
    assert settings.ai_gateway_backend == "local"
    assert settings.context_store_backend == "memory"
    assert settings.dag_executor == "local"
    assert settings.rag_parser_backend == "legacy"


def test_upgrade_ports_are_protocols() -> None:
    ports = (AuthPort, PolicyPort, RateLimitPort, ContextStorePort, PromptRegistryPort, RagParserPort, DagExecutorPort)
    assert all(getattr(port, "_is_protocol", False) for port in ports)
