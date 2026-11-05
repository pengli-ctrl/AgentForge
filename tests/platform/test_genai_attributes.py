"""测试 GenAI Trace 属性映射。"""

from agentforge.platform.observability.genai import set_genai_attributes


class FakeSpan:
    """提供测试用 Span。"""

    def __init__(self):
        """初始化测试 Span。"""
        self.attrs = {}

    def set_attribute(self, key, value):
        """记录 Span 属性。

        Args:
            key: 属性名。
            value: 属性值。
        """
        self.attrs[key] = value


def test_genai_attributes_include_tenant_and_prompt_version() -> None:
    """验证租户和提示词版本进入 Span。"""
    span = FakeSpan()
    set_genai_attributes(
        span, provider="openai", model="gpt-test", tenant_id="t1", prompt_version="p7"
    )
    assert span.attrs["gen_ai.system"] == "openai"
    assert span.attrs["agentforge.tenant_id"] == "t1"
    assert span.attrs["agentforge.prompt.version"] == "p7"
