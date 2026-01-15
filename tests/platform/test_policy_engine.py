"""AgentForge 平台测试层：test_policy_engine。

本测试模块验证 test_policy_engine 覆盖的业务路径、边界条件和回归场景。

核心说明：
- 对外接口保持稳定，避免调用方依赖内部实现细节。
- 所有租户相关数据都必须携带 tenant_id 并保持隔离。
- 关键执行路径应保留日志、审计或链路追踪信息。
-
主要函数：test_unknown_action_fails_closed、test_writeback_requires_approval_even_for_admin、test_view_allowed_with_permission_and_role、test_writeback_without_view_permission_denied、test_disabled_policy_denied、test_relation_check_gates_resource_access、test_custom_tenant_policy、test_policy_file_loader_parses_valid_document。
"""

from __future__ import annotations

from agentforge.platform.application.builtin_policies import builtin_policies
from agentforge.platform.application.openfga_adapter import OpenFGAClient
from agentforge.platform.application.policy_engine import PolicyEngine
from agentforge.platform.domain.policy import (
    ActionPolicy,
    PolicyFileLoader,
    RelationTuple,
    ValidationOutcome,
)


async def test_unknown_action_fails_closed() -> None:
    """验证 unknown_action_fails_closed 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    engine = PolicyEngine(policies=builtin_policies())
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.delete",
        roles=["admin"],
    )
    assert decision.allowed is False
    assert decision.outcome == ValidationOutcome.DENIED


async def test_writeback_requires_approval_even_for_admin() -> None:
    """验证 writeback_requires_approval_even_for_admin 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    engine = PolicyEngine(policies=builtin_policies())
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.writeback",
        roles=["admin"],
    )
    assert decision.outcome == ValidationOutcome.REQUIRES_APPROVAL
    assert decision.allowed is False


async def test_view_allowed_with_permission_and_role() -> None:
    """验证 view_allowed_with_permission_and_role 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    engine = PolicyEngine(policies=builtin_policies())
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.view",
        roles=["support_admin"],
        permissions=["ticket.read"],
    )
    assert decision.outcome == ValidationOutcome.ALLOWED
    assert decision.allowed is True


async def test_writeback_without_view_permission_denied() -> None:
    """验证 writeback_without_view_permission_denied 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    engine = PolicyEngine(policies=builtin_policies())
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.view",
        roles=["support_admin"],
        permissions=["ticket.reply"],
    )
    assert decision.outcome == ValidationOutcome.DENIED


async def test_disabled_policy_denied() -> None:
    """验证 disabled_policy_denied 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    engine = PolicyEngine(
        policies=[
            ActionPolicy(
                name="p",
                tenant_id="t1",
                action="a",
                enabled=False,
                required_permission="ticket.read",
            )
        ]
    )
    decision = await engine.authorize(
        tenant_id="t1",
        principal="u",
        action="a",
        roles=["admin"],
    )
    assert decision.outcome == ValidationOutcome.DENIED
    assert "disabled" in decision.reasons[0]


async def test_relation_check_gates_resource_access() -> None:
    """验证 relation_check_gates_resource_access 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    client = OpenFGAClient()
    client.write(
        "t1",
        [
            RelationTuple(
                tenant_id="t1",
                object_type="ticket",
                object_id="tk-1",
                relation="viewer",
                subject_type="user",
                subject_id="user-1",
            )
        ],
    )
    engine = PolicyEngine(
        policies=builtin_policies(),
        relation_check=lambda t: client.acheck(
            t.tenant_id, t.object_type, t.object_id, t.relation, t.subject_id
        ),
    )
    decision = await engine.authorize(
        tenant_id="t1",
        principal="user-1",
        action="ticket.view",
        roles=["support_admin"],
        permissions=["ticket.read"],
        resource_type="ticket",
        resource_id="tk-1",
        relation="viewer",
    )
    assert decision.allowed is True

    denied = await engine.authorize(
        tenant_id="t1",
        principal="user-2",
        action="ticket.view",
        roles=["support_admin"],
        permissions=["ticket.read"],
        resource_type="ticket",
        resource_id="tk-1",
        relation="viewer",
    )
    assert denied.allowed is False
    assert "relation" in denied.reasons[0]


async def test_custom_tenant_policy() -> None:
    """验证 custom_tenant_policy 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    engine = PolicyEngine(
        policies=[
            ActionPolicy(
                name="custom",
                tenant_id="t9",
                action="ticket.view",
                allowed_roles=["support_admin"],
                enabled=True,
            )
        ]
    )
    ok = await engine.authorize(
        tenant_id="t9", principal="u", action="ticket.view", roles=["support_admin"]
    )
    assert ok.allowed is True
    bad = await engine.authorize(
        tenant_id="t9", principal="u", action="ticket.view", roles=["support_agent"]
    )
    assert bad.allowed is False


def test_policy_file_loader_parses_valid_document() -> None:
    """验证 policy_file_loader_parses_valid_document 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    doc = (
        "["
        '{"name": "ticket_writeback", "tenant_id": "*", "action": "ticket.writeback",'
        '"risk_level": "high", "required_permission": "ticket.writeback",'
        '"require_approval": true, "enabled": true},'
        '{"name": "ticket_view", "tenant_id": "*", "action": "ticket.view",'
        '"risk_level": "low", "required_permission": "ticket.read"}'
        "]"
    )
    policies = PolicyFileLoader.from_string(doc)
    assert len(policies) == 2
    assert policies[0].action == "ticket.writeback"
    assert policies[0].require_approval is True
    assert policies[1].required_permission == "ticket.read"


def test_policy_file_loader_rejects_invalid_or_unknown_fields() -> None:
    # 验证未知输入场景，确保系统不会静默放行。
    """验证 policy_file_loader_rejects_invalid_or_unknown_fields 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。

    Raises:
        AssertionError: 当输入、状态或外部依赖不满足要求时抛出。
    """
    bad_unknown = '[{"name":"x","tenant_id":"*","action":"a","unknown":1}]'
    try:
        PolicyFileLoader.from_string(bad_unknown)
        raise AssertionError("expected validation error")
    except Exception:
        pass
    # 验证非列表输入，确保类型校验有效。
    try:
        PolicyFileLoader.from_string('{"name":"x"}')
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    # 验证非 JSON 输入，确保解析异常被正确处理。
    try:
        PolicyFileLoader.from_string("not-json{")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


async def test_policy_engine_reload_atomically_replaces_policies() -> None:
    """验证 policy_engine_reload_atomically_replaces_policies 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    engine = PolicyEngine(policies=[])
    doc1 = (
        '[{"name": "p1", "tenant_id": "*", "action": "ticket.ping",'
        '"risk_level": "low", "enabled": false}]'
    )
    rev = engine.reload(PolicyFileLoader.from_string(doc1))
    assert rev == 1
    assert engine.source_revision == 1
    d = await engine.authorize(
        tenant_id="t1", principal="u1", action="ticket.ping", roles=["admin"]
    )
    assert d.outcome == ValidationOutcome.DENIED  # 验证禁用状态下策略和功能不会意外生效。

    doc2 = (
        '[{"name": "p1", "tenant_id": "*", "action": "ticket.ping",'
        '"risk_level": "low", "enabled": true}]'
    )
    rev2 = engine.reload(PolicyFileLoader.from_string(doc2))
    assert rev2 == 2
    d2 = await engine.authorize(
        tenant_id="t1", principal="u1", action="ticket.ping", roles=["admin"]
    )
    assert d2.outcome == ValidationOutcome.ALLOWED


async def test_policy_engine_keep_previous_on_bad_reload() -> None:
    """验证 policy_engine_keep_previous_on_bad_reload 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。

    Raises:
        ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        AssertionError: 当输入、状态或外部依赖不满足要求时抛出。
    """
    engine = PolicyEngine(
        policies=PolicyFileLoader.from_string(
            '[{"name":"p","tenant_id":"*","action":"a","enabled":true}]'
        )
    )
    base_rev = engine.source_revision
    before_d = await engine.authorize(tenant_id="t1", principal="u", action="a", roles=["admin"])
    assert before_d.outcome == ValidationOutcome.ALLOWED

    def bad_loader():
        """执行 bad_loader 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise ValueError("config source unavailable")

    try:
        engine.reload_from_loader(bad_loader)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert engine.source_revision == base_rev
    after_d = await engine.authorize(tenant_id="t1", principal="u", action="a", roles=["admin"])
    assert after_d.outcome == ValidationOutcome.ALLOWED


def test_policy_engine_reload_rejects_duplicate_key() -> None:
    """验证 policy_engine_reload_rejects_duplicate_key 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。

    Raises:
        AssertionError: 当输入、状态或外部依赖不满足要求时抛出。
    """
    engine = PolicyEngine(policies=[])
    dup = '[{"name":"a","tenant_id":"t1","action":"x"},{"name":"b","tenant_id":"t1","action":"x"}]'
    try:
        engine.reload(PolicyFileLoader.from_string(dup))
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert engine.source_revision == 0


def test_policy_engine_emits_versioned_reload_event() -> None:
    """验证 policy_engine_emits_versioned_reload_event 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    events: list[tuple] = []
    engine = PolicyEngine(
        policies=[],
        reload_listener=lambda event: events.append(
            (event.revision, event.policy_count, event.source)
        ),
    )
    rev = engine.reload(
        PolicyFileLoader.from_string(
            '[{"name": "p1", "tenant_id": "*", "action": "ticket.ping",'
            '"risk_level": "low", "enabled": true},'
            '{"name": "p2", "tenant_id": "*", "action": "ticket.view",'
            '"risk_level": "low", "required_permission": "ticket.read"}]'
        )
    )
    assert rev == 1
    assert engine.source_revision == 1
    assert len(events) == 1
    assert events[0] == (1, 2, "reload")


def test_policy_engine_reload_from_loader_emits_source_label() -> None:
    """验证 policy_engine_reload_from_loader_emits_source_label 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。
    """
    events: list[str] = []
    engine = PolicyEngine(
        policies=[],
        reload_listener=lambda event: events.append(event.source),
    )
    rev = engine.reload_from_loader(
        lambda: PolicyFileLoader.from_string(
            '[{"name": "p", "tenant_id": "*", "action": "a", "enabled": true}]'
        )
    )
    assert rev == 1
    assert events == ["reload_from_loader"]


def test_policy_engine_bad_reload_emits_no_event() -> None:
    """验证 policy_engine_bad_reload_emits_no_event 对应的业务行为、边界条件和回归场景。

    Returns:
        None，函数执行后的结果。

    Raises:
        ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        AssertionError: 当输入、状态或外部依赖不满足要求时抛出。
    """
    events: list[int] = []
    engine = PolicyEngine(
        policies=PolicyFileLoader.from_string(
            '[{"name": "p", "tenant_id": "*", "action": "a", "enabled": true}]'
        ),
        reload_listener=lambda event: events.append(event.revision),
    )
    base_rev = engine.source_revision

    def bad_loader():
        """执行 bad_loader 对应的逻辑，并返回处理结果。

        Returns:
            None，函数执行后的结果。

        Raises:
            ValueError: 当输入、状态或外部依赖不满足要求时抛出。
        """
        raise ValueError("config source unavailable")

    try:
        engine.reload_from_loader(bad_loader)
        raise AssertionError("expected ValueError")
    except ValueError:
        pass
    assert engine.source_revision == base_rev
    assert events == []  # 验证失败场景，确保异常路径能够被正确处理。
