from agentforge.platform.infrastructure.llm.gateway_factory import build_inner_model_gateway
from agentforge.platform.infrastructure.llm.litellm_gateway import LiteLLMModelGateway
from agentforge.platform.infrastructure.llm.static_gateway import StaticModelGateway
from agentforge.platform.settings import Settings


def test_factory_builds_static_gateway() -> None:
    gateway = build_inner_model_gateway(Settings(_env_file=None, ai_gateway_backend="static"))
    assert isinstance(gateway, StaticModelGateway)


def test_factory_builds_litellm_gateway() -> None:
    gateway = build_inner_model_gateway(
        Settings(_env_file=None, ai_gateway_backend="litellm", litellm_proxy_url="http://litellm:4000")
    )
    assert isinstance(gateway, LiteLLMModelGateway)


def test_factory_rejects_unknown_backend() -> None:
    try:
        build_inner_model_gateway(Settings(_env_file=None, ai_gateway_backend="nope"))
    except ValueError as exc:
        assert "unsupported" in str(exc)
    else:
        raise AssertionError("expected ValueError")
