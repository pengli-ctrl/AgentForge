# AgentForge 业务模块接入指南

> 验证基线：`templates/module-template` 与 `agentforge/platform/modules/demo_asset`。

## 1. 接入流程

1. 复制 `templates/module-template/agentforge_module_template`。
2. 修改包名、`ModuleManifest.name`、`api_prefix`、`task_queue`、`migration_namespace`。
3. 按 Domain / Application / Infrastructure / API 分层实现，Application 只依赖本模块 Port 和 `agentforge.platform.sdk`。
4. 在模块 `pyproject.toml` 声明 `agentforge.modules` entry point。
5. 执行 `run_module_contract_suite`，并补充模块业务 E2E、租户隔离和迁移测试。
6. 为 SQLAlchemy 仓储提供独立 migration namespace 和可执行 downgrade。

```toml
[project.entry-points."agentforge.modules"]
asset = "agentforge_module_template.module:DemoAssetModule"
```

本地嵌入式装配可使用 `create_platform_app(extra_modules=(DemoAssetModule(),), load_plugins=False)`。生产环境通过安装包 entry point 自动发现，不需要修改平台 core 或 API app。

## 2. 模块契约

| 检查项 | 要求 |
|---|---|
| API 前缀 | `/v1/{module}` 或 `/v1/{module}s`，Router 自身 prefix 为空 |
| 权限 | `{module}.{resource}.{action}` |
| Published Event | `{module}.{resource}.{event}.vN` |
| Consumed Event | 使用 `.vN` 后缀，声明后不得静默改变语义 |
| 依赖能力 | 只能引用 `core.*` 能力，不直接依赖其他业务模块 |
| Config | Pydantic schema，声明默认值，并支持租户覆盖 |
| 事件处理器 | 使用事件中的 tenant_id，重复消费必须幂等 |
| Startup hook | 可重复执行，不依赖单次进程状态 |
| Temporal | 声明 Workflow、Activity 和独立 Task Queue |
| 租户隔离 | API、仓储查询、缓存键和事件处理均显式包含 tenant_id |
| Migration | `migration_namespace == manifest.name`，可 upgrade/downgrade |
| 版本策略 | 声明 `version`、`contract_version`、`minimum_platform_version` |

统一检查入口：

```python
from agentforge.platform.sdk.contract_testing import run_module_contract_suite
```

`tenant_isolation_probe` 必须证明租户 A 写入的数据在租户 B 中不可见，跨租户查询返回空或 404。

## 3. 当前模块参考

### Support

详见 [`agentforge/platform/modules/support/README.md`](../../agentforge/platform/modules/support/README.md)。

| 维度 | 当前实现 |
|---|---|
| Manifest / API 前缀 | `support` / `/v1/support` |
| Temporal | Task Queue `support-copilot`；工单工作流和 SLA 周期扫描 |
| Migration | `migration_namespace=support`，主要数据位于 `module_support` schema |
| 数据模型 | Ticket、状态机、优先级、SLA 事件、负责人、回复和写回记录 |
| Port | TicketRepository、ReplyConnectorPort、NotificationPort |
| 权限 | `support.ticket.read`、`support.ticket.review`、`support.ticket.approve` |
| 事件 | 发布 `support.ticket.sla_due_soon.v1`、`support.ticket.sla_breached.v1`；消费 Expense 门禁告警事件 |
| 共享能力 | Audit、Outbox、Connector、Cost、Identity、Knowledge、Model、Workflow |
| 重点 | Webhook HMAC、SLA 升级、通知幂等、高风险写回审批 |

### Expense

详见 [`agentforge/platform/modules/expense/README.md`](../../agentforge/platform/modules/expense/README.md)。

| 维度 | 当前实现 |
|---|---|
| Manifest / API 前缀 | `expense` / `/v1/expense` |
| Temporal | Task Queue `expense-copilot`；OCR、台账写回和门禁周期扫描 |
| Migration | `migration_namespace=expense`，主要数据位于 `module_expense` schema |
| 数据模型 | Claim、Attachment、OCR Job、Invoice、Approval、Ledger、Writeback Job |
| 权限 | `expense.claim.*`、`expense.ledger.*`、`expense.invoice.*` |
| 事件 | 报销提交/审批、台账写回与核验、发票登记/验真/门禁告警 |
| 共享能力 | Audit、Outbox、Authorization、Knowledge、Model、Object Store、Uploads、Workflow |
| 重点 | 金额整数分、票据去重、发票门禁、幂等写回和补偿 |

### Demo Asset

详见 [`agentforge/platform/modules/demo_asset/README.md`](../../agentforge/platform/modules/demo_asset/README.md)。

| 维度 | 当前实现 |
|---|---|
| Manifest / API 前缀 | `asset` / `/v1/assets`；当前 Router 路径为 `/assets`，有效路径为 `/v1/assets/assets` |
| Temporal | Task Queue `asset-copilot` |
| Migration | `migration_namespace=asset`，表 `module_asset_assets` |
| 数据模型 | Asset 与 archive 状态 |
| 权限 | `asset.asset.read`、`asset.asset.write` |
| 事件 | 发布并消费 `asset.asset.created.v1` |
| 作用 | 可运行的模块模板，验证 Manifest、Router、Memory/SQLAlchemy、Connector、事件和 Temporal 装配 |

## 4. 配置与密钥

- 业务配置放在 `config_schema` / `config_defaults`，通过租户 override 合并。
- 密钥、Webhook secret、Connector token 放在 `secret_refs`，只允许 `vault://`、`kms://`、`secret://`、`env://`。
- Application 层不得读取其他模块配置。
- 配置变更必须写 Audit 和 Outbox。

## 5. 数据与迁移

1. 每个模块拥有独立 migration namespace；生产模块可使用独立 schema。
2. 迁移只能修改本模块表。
3. upgrade/downgrade 必须在空库和上一版本快照执行。
4. 破坏性变更采用 expand / migrate / contract。
5. 表名建议 `module_{module}_{entity}`，租户过滤字段建立索引。

## 6. 发布验收

- [ ] Manifest、Router、Task Queue、Permission、Event、Migration 命名一致。
- [ ] tenant_isolation_probe 通过。
- [ ] Memory 和 SQLAlchemy 仓储行为一致。
- [ ] 事件重复消费幂等。
- [ ] Temporal retry、timeout、task_queue 已验证。
- [ ] Secret 不进入日志和数据库明文。
- [ ] Contract suite、静态门禁和全量测试通过。
