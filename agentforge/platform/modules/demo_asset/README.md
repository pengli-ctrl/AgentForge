# Demo Asset Module

## 模块定位

Demo Asset 是 AgentForge 的可运行参考模块，用于验证第三方业务模块能否在不修改平台 core、API app 和 `ServiceContainer` 的前提下完成装配。

它与 `templates/module-template` 保持同一套 `ModuleManifest`、`ModuleContext`、`ModuleRuntime` 和 SDK Port 契约。

## Manifest

| 字段 | 值 |
|---|---|
| 模块名 | `asset` |
| API 前缀 | `/v1/assets`（与 Router 路径组合后的有效路径见下方） |
| Temporal Task Queue | `asset-copilot` |
| migration namespace | `asset` |
| 最低平台版本 | `3.1.0` |
| 权限 | `asset.asset.read`、`asset.asset.write` |
| 发布事件 | `asset.asset.created.v1` |
| 消费事件 | `asset.asset.created.v1` |

## 目录结构

```text
demo_asset/
├── api/router.py
├── application/service.py
├── domain/asset.py
├── infrastructure/
│   ├── memory_repository.py
│   └── sqlalchemy_repository.py
├── workflows/asset_workflow.py
├── config.py
├── module.py
└── ports.py
```

## 主要接口

```text
POST /v1/assets/assets
GET  /v1/assets/assets
GET  /v1/assets/assets/{asset_id}
POST /v1/assets/assets/{asset_id}/archive
```


`ModuleRegistry` 会把 `manifest.api_prefix` 与 Router 的 route path 组合。当前 Router 声明 `/assets`，因此有效路径为 `/v1/assets/assets`；调整 API 时应同时核对这两层。
所有查询、写入和事件都显式携带 `tenant_id`。Memory 与 SQLAlchemy 仓储实现必须保持相同行为。

## 运行时能力

模块通过 `ModuleRuntime` 注册：

- Asset API Router；
- `AssetPreparationWorkflow` 和 `prepare_asset_activity`；
- `asset-directory` Connector 元数据与 `lookup`、`sync` allow-list；
- `asset.asset.created.v1` 幂等事件处理器；
- 启动 hook；
- 模块指标扩展点。

## 配置

`AssetModuleConfig` 当前包含：

```text
retention_days
allow_manual_archive
```

租户级配置通过 `tenant_modules` 覆盖，敏感值必须使用 `secret_refs`。

## 相关文档

- [模块接入指南](../../../../docs/modules/MODULE_INTEGRATION_GUIDE.md)
- [模块版本兼容与弃用](../../../../docs/modules/VERSIONING_AND_DEPRECATION.md)
- [可运行模块模板](../../../../templates/module-template/README.md)
