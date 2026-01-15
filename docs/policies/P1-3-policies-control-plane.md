# P1-3 策略热加载控制面：/v1/policies

## 目标

把底层 `PolicyEngine`（C-05 已落地：原子换载 + 版本化审计 + 坏配置保旧）的**控制面能力**暴露为 REST 端点，让运营/脚本无需重启服务即可安全更新策略。补齐 README 宣称的 `/v1/policies`，消除"文档与实现不符"。

## 已实现的端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/v1/policies?tenant_id=` | 列出某租户当前生效策略 + `source_revision` |
| GET | `/v1/policies/revision` | 返回当前版本号（并发 / 对账用） |
| POST | `/v1/policies/reload` | body `{"policies": [<ActionPolicy...>]}`，原子热加载全量替换 |

## 设计要点（保持 fail-closed）

1. **原子热加载**：`POST /v1/policies/reload` 把 body 经 `PolicyFileLoader.from_string`（JSON 严格解析，`ActionPolicy` 用 `extra="forbid"` 拒绝未知字段）解析后交给 `PolicyEngine.reload` 一次性换载。
2. **坏配置保旧**：解析失败、含未知字段、重复 key 时返回 `422`，引擎**保留上一份策略**且 `source_revision` 不递增——绝无半更新状态。
3. **版本追溯**：`source_revision` 单调递增，每次成功 reload 递增；审计事件（`PolicyReloadEvent`）已由 C-05 的 `reload_listener` 旁路发出，本端点不重复实现。

## 示例

```bash
# 查看 tenant-a 当前策略
curl "http://localhost:8000/v1/policies?tenant_id=tenant-a"

# 热加载（原子替换）
curl -X POST http://localhost:8000/v1/policies/reload \
  -H "Content-Type: application/json" \
  -d '{
    "policies": [{
      "name": "write-ticket",
      "tenant_id": "tenant-a",
      "action": "ticket:write",
      "risk_level": "high",
      "allowed_roles": ["support_admin"],
      "require_approval": true,
      "enabled": true
    }]
  }'

# 坏配置 -> 422，旧策略保留，revision 不变
curl -X POST http://localhost:8000/v1/policies/reload \
  -H "Content-Type: application/json" \
  -d '{"policies": [{"name":"x","tenant_id":"t","action":"a","enabled":true,"unknown_field":1}]}'
# -> HTTP 422
```

## 与 RBAC 的关系

`/v1/policies` 与 `/v1/rbac` 同属授权域，共享同一个 `PolicyEngine` 实例。RBAC 管理**角色/分配**，policies 管理**动作级策略**（风险等级、审批要求、角色 allow-list）。两者叠加后由 `POST /v1/rbac/authorize` 统一裁决。

## 验证

```bash
# 4 项控制面测试（含 fail-closed：坏配置 422 且保留旧策略）
python -m pytest tests/platform/test_policies_router.py -q
# 全平台回归
python -m pytest tests/platform -q
```

## 验收清单

- [x] `GET /v1/policies` / `GET /v1/policies/revision` 只读可用
- [x] `POST /v1/policies/reload` 原子热加载，revision 单调递增
- [x] 坏配置 / 坏 body → 422，旧策略保留（fail-closed）
- [x] 4 项控制面测试通过，全平台 262 passed
- [x] flake8 / black / isort 全绿