"""本地真实容器集成测试。"""
import os
import httpx
import pytest


def _require_stack() -> None:
    """要求本地集成栈已启动。"""
    if os.getenv("AGENTFORGE_LOCAL_STACK") != "1":
        pytest.skip("local integration stack is not enabled")


def test_mock_openai_health() -> None:
    """验证 Mock OpenAI 服务。"""
    _require_stack()
    response = httpx.get("http://localhost:8010/health", timeout=5)
    response.raise_for_status()


def test_opa_health() -> None:
    """验证 OPA 服务。"""
    _require_stack()
    response = httpx.get("http://localhost:8181/health", timeout=5)
    response.raise_for_status()
