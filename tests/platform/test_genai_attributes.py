from agentforge.platform.observability.genai import set_genai_attributes


class FakeSpan:
    def __init__(self): self.attrs = {}
    def set_attribute(self, key, value): self.attrs[key] = value


def test_genai_attributes_include_tenant_and_prompt_version() -> None:
    span = FakeSpan()
    set_genai_attributes(span, provider="openai", model="gpt-test", tenant_id="t1", prompt_version="p7")
    assert span.attrs["gen_ai.system"] == "openai"
    assert span.attrs["agentforge.tenant_id"] == "t1"
    assert span.attrs["agentforge.prompt.version"] == "p7"
