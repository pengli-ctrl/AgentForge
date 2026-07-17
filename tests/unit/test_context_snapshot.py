"""Context Snapshot 测试 — 创建/提取/合并/清理。

测试内容：
- 创建快照（冻结上下文）
- 快照不可变性（修改原数据不影响快照）
- 从快照提取指定键
- 合并多个快照
- 清理指定工作流的快照
"""

from __future__ import annotations

from agentforge.core.context_snapshot import ContextSnapshotManager


def test_create_snapshot() -> None:
    """创建快照 — 冻结当前上下文。"""
    manager = ContextSnapshotManager()
    context = {"code": "print('hello')", "config": {"strict": True}}

    snapshot = manager.create_snapshot("task-001", context)

    assert snapshot.correlation_id == "task-001"
    assert snapshot.version == 0
    assert snapshot.get("code") == "print('hello')"


def test_snapshot_immutability() -> None:
    """快照不可变性 — 修改原数据不影响快照。"""
    manager = ContextSnapshotManager()
    context = {"code": "original", "items": [1, 2, 3]}

    snapshot = manager.create_snapshot("task-002", context)

    # 修改原数据
    context["code"] = "modified"
    context["items"].append(4)

    # 快照不应受影响
    assert snapshot.get("code") == "original"
    assert snapshot.get("items") == [1, 2, 3]


def test_extract_keys() -> None:
    """从快照提取指定键。"""
    manager = ContextSnapshotManager()
    context = {
        "code_content": "def add(a, b): return a + b",
        "review_config": {"types": ["security"]},
        "test_config": {"framework": "pytest"},
        "extra_data": "not needed",
    }

    snapshot = manager.create_snapshot("task-003", context)

    # 只提取需要的键
    extracted = snapshot.extract(["code_content", "review_config"])

    assert "code_content" in extracted
    assert "review_config" in extracted
    assert "test_config" not in extracted
    assert "extra_data" not in extracted


def test_merge_snapshots() -> None:
    """合并多个快照 — last-write-wins 策略。"""
    manager = ContextSnapshotManager()

    snapshot_1 = manager.create_snapshot("task-004", {"a": 1, "b": 2})
    snapshot_2 = manager.create_snapshot("task-004", {"b": 3, "c": 4})

    merged = manager.merge_snapshots("task-004", [snapshot_1, snapshot_2])

    # 后写入的覆盖先写入的
    assert merged["a"] == 1
    assert merged["b"] == 3  # snapshot_2 覆盖了 snapshot_1
    assert merged["c"] == 4


def test_cleanup_snapshots() -> None:
    """清理指定工作流的所有快照。"""
    manager = ContextSnapshotManager()

    manager.create_snapshot("task-005", {"data": "first"})
    manager.create_snapshot("task-005", {"data": "second"})
    manager.create_snapshot("task-006", {"data": "other"})

    # 清理 task-005
    manager.cleanup("task-005")

    # task-005 的快照应被清理
    assert manager.get_latest_snapshot("task-005") is None

    # task-006 的快照应保留
    latest = manager.get_latest_snapshot("task-006")
    assert latest is not None
    assert latest.get("data") == "other"


def test_get_latest_snapshot() -> None:
    """获取最新版本的快照。"""
    manager = ContextSnapshotManager()

    manager.create_snapshot("task-007", {"version": 0})
    manager.create_snapshot("task-007", {"version": 1})
    manager.create_snapshot("task-007", {"version": 2})

    latest = manager.get_latest_snapshot("task-007")

    assert latest is not None
    assert latest.version == 2
    assert latest.get("version") == 2


def test_get_latest_snapshot_not_found() -> None:
    """获取不存在的工作流快照返回 None。"""
    manager = ContextSnapshotManager()
    assert manager.get_latest_snapshot("nonexistent") is None


def test_snapshot_to_dict() -> None:
    """快照转字典 — 返回深拷贝。"""
    manager = ContextSnapshotManager()
    context = {"key": "value", "nested": {"inner": "data"}}

    snapshot = manager.create_snapshot("task-008", context)
    snapshot_dict = snapshot.to_dict()

    # 修改返回的字典不影响原始快照
    snapshot_dict["key"] = "modified"
    assert snapshot.get("key") == "value"


def test_snapshot_get_with_default() -> None:
    """快照 get 方法支持默认值。"""
    manager = ContextSnapshotManager()
    snapshot = manager.create_snapshot("task-009", {"existing": "yes"})

    assert snapshot.get("existing") == "yes"
    assert snapshot.get("nonexistent") is None
    assert snapshot.get("nonexistent", "default") == "default"
