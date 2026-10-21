# AgentForge Module Template

该目录是一个可运行的第三方业务模块模板，演示如何通过稳定 SDK 接入 AgentForge，而不修改平台 core、API app 或 ServiceContainer。

模板包名为 `agentforge_module_template`，示例业务名为 Demo Asset。

## 目录

```text
templates/module-template/
├── pyproject.toml
├── README.md
└── agentforge_module_template/
    ├── __init__.py
    ├── module.py                    # ModuleManifest 与 ModuleRuntime
    ├── config.py                    # Pydantic 配置 schema
    ├── ports.py                     # 模块仓储 Port
    ├── api/router.py                # 模块 API
    ├── application/service.py       # 用例、Audit、Outbox
    ├── domain/asset.py              # 领域模型和状态
    ├── infrastructure/
    │   ├── memory_repository.py
    │   └── sqlalchemy_repository.py
    └── workflows/asset_workflow.py  # Temporal Workflow/Activity
```

## 1. 复制并重命名

复制 `agentforge_module_template` 目录，替换：

- Python 包名；
- `ModuleManifest.name`；
- `api_prefix`；
- `task_queue`；
- `migration_namespace`；
- 权限、事件、表名和业务模型。

`ModuleManifest` 的约束：

| 字段 | 要求 |
|---|---|
| `name` | 小写 snake_case |
| `version` | 语义版本 |
| `api_prefix` | `/v1/{name}` 或 `/v1/{name}s` |
| `task_queue` | 以模块名开头 |
| `migration_namespace` | 等于模块名 |
| `permissions` | `{module}.{resource}.{action}` |
| `published_events` / `consumed_events` | 以 `.vN` 结尾 |
| `minimum_platform_version` | 不高于目标平台版本 |
| `contract_version` | 当前支持 `1` |

## 2. 装配入口

`DemoAssetModule` 实现：

- `manifest`；
- `build(ctx) -> ModuleRuntime`。

`build` 中通过 `ModuleContext` 获取共享 Port，并组装模块自身的 service、repository、router、workflow、activity、connector、事件处理器和 startup hook。

本地测试可显式装配：

```python
from agentforge.platform.api.app import create_platform_app
from agentforge_module_template.module import DemoAssetModule

app = create_platform_app(
    extra_modules=(DemoAssetModule(),),
    load_plugins=False,
)
```

## 3. 插件发布

在模块包 `pyproject.toml` 声明 entry point：

```toml
[project.entry-points."agentforge.modules"]
asset = "agentforge_module_template.module:DemoAssetModule"
```

平台启动时通过 entry point 自动发现已安装模块。entry point 可以提供模块实例、模块类或零参数 factory。

无需修改 `create_platform_app`。

## 4. ModuleRuntime 能力

模板展示了以下可注册能力：

- `router`：模块 HTTP API；
- `temporal_workflows`：模块 Temporal Workflow；
- `temporal_activities`：模块 Activity；
- `agent_tools`：模块提供的 Agent Tool；
- `connector_registrations`：Connector 元数据和 allow-list；
- `event_handlers`：按事件类型处理 Outbox 事件；
- `startup_hooks`：启动时初始化，例如确保 Schedule；
- `metric_providers`：向平台指标端点提供模块指标。

## 5. Domain / Application / Infrastructure

- Domain 不依赖 FastAPI、SQLAlchemy 或平台具体实现。
- Application 只依赖本模块 Port 和 `agentforge.platform.sdk` 中的 Audit、Outbox、Authorization 等 Port。
- API 负责鉴权、租户/模块访问检查和请求转换，不包含业务规则。
- Infrastructure 提供 Memory 和 SQLAlchemy 双仓储，二者必须保持相同行为。
- 所有查询必须显式使用 `tenant_id`。

模板中的 `AssetRepository` 是模块 Port。共享能力只通过 `ModuleContext` 注入：

```text
ctx.audit
ctx.authorization
ctx.outbox
ctx.connectors
ctx.knowledge
ctx.models
ctx.policy
ctx.cost
ctx.identity
ctx.module_access
ctx.workflow
ctx.persistence
ctx.object_store
ctx.uploads
ctx.usage
```

## 6. 配置与 Secret

`config.py` 定义 `AssetModuleConfig`，并拒绝未知字段：

```python
class AssetModuleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    retention_days: int = Field(default=365, ge=1)
    allow_manual_archive: bool = True
```

配置合并顺序：

```text
manifest.config_defaults
  -> 部署级配置
  -> 租户级 tenant_modules override
```

敏感字段不得出现在配置明文中。模块配置应校验 `secret_refs`，只允许 `env://`、`vault://`、`kms://`、`secret://`。

## 7. 事件

模板发布并消费：

```text
asset.asset.created.v1
```

业务写入完成后：

1. 写 Audit；
2. 在同一业务边界内 enqueue Outbox；
3. Outbox Worker 投递给 publisher 和 handler；
4. handler 以 `(event_id, handler_name)` 幂等；
5. 重复事件不得产生重复业务副作用。

消费其他模块事件时，只能依赖已发布事件契约，不直接读取其他模块数据库。

## 8. Temporal

模板包含 `AssetPreparationWorkflow` 和 `prepare_asset_activity`。生产要求：

- 使用 manifest 声明自己的 Task Queue；
- Workflow 保持确定性；
- 外部副作用放在 Activity；
- Activity 配置 timeout 和 retry；
- 多次启动 Schedule/Worker 必须幂等；
- Workflow 名称全局唯一。

## 9. 迁移

模块必须有独立 `migration_namespace` 和可执行 downgrade。验收至少执行：

```text
upgrade head
downgrade base
upgrade head
```

迁移只能修改本模块表；破坏性字段变更采用 expand / migrate / contract。

## 10. 契约测试

```python
from agentforge.platform.sdk.contract_testing import run_module_contract_suite

report = await run_module_contract_suite(
    module,
    context,
    tenant_isolation_probe=probe,
)
```

契约套件检查：

- manifest 名称、API 前缀、Task Queue、migration namespace；
- contract version；
- permission 和 event 格式；
- `depends_on` 只引用可用 `core.*` 能力；
- config schema/defaults；
- `build()` 返回 `ModuleRuntime`；
- Router prefix；
- 冲突检测；
- 可选租户隔离探针。

## 11. 发布验收

- [ ] contract suite 通过。
- [ ] tenant isolation probe 通过。
- [ ] Memory/SQLAlchemy 行为一致。
- [ ] 事件重复消费幂等。
- [ ] Temporal retry/timeout/task queue 已验证。
- [ ] Secret 不进入日志或数据库明文。
- [ ] migration upgrade/downgrade/upgrade 通过。
- [ ] 全量静态门禁和测试通过。

完整规则见：

- [模块接入指南](../../docs/modules/MODULE_INTEGRATION_GUIDE.md)
- [模块版本兼容与弃用](../../docs/modules/VERSIONING_AND_DEPRECATION.md)
- [Demo Asset 模块](../../agentforge/platform/modules/demo_asset/README.md)
