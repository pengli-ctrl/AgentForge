# 模块版本兼容与弃用策略

## 1. 版本字段

| 字段 | 含义 |
|---|---|
| `ModuleManifest.version` | 模块包语义版本，例如 `1.4.0` |
| `ModuleManifest.contract_version` | 平台模块契约版本；当前支持 `1` |
| `ModuleManifest.minimum_platform_version` | 模块要求的最低平台版本 |
| `ModuleManifest.deprecated` | 是否进入弃用窗口 |
| `ModuleManifest.deprecation_message` | 用户可读的迁移说明 |
| `ModuleManifest.replacement_module` | 推荐替代模块名 |

## 2. 兼容规则

1. Patch：只修复 bug，不改变 manifest、事件、权限、配置字段或数据库语义。
2. Minor：可以新增可选字段、事件和权限；旧租户配置必须继续有效。
3. Major：允许删除字段或改变语义，但必须先经过弃用窗口并提供数据迁移。
4. `contract_version` 升级由平台显式加入支持列表，模块不能自行假定双向兼容。
5. `minimum_platform_version` 高于当前平台时，ModuleRegistry 拒绝启动模块。
6. 已发布事件的 `.vN` 后缀不可修改；只能新增 `vN+1` 并保留转换窗口。
7. 配置 schema 只允许向后兼容的新增；删除字段必须提供默认值和迁移说明。

## 3. 弃用窗口

- 至少提前一个 Minor 版本公告。
- 常规模块保留至少 2 个 Minor 版本或 180 天，以较长者为准。
- 安全问题可以立即禁用或移除，但必须保留审计、通知和回滚说明。
- 弃用模块必须填写 `deprecation_message`，建议填写 `replacement_module`。
- `ModuleRegistry.deprecated_modules()` 供运维和 CI 生成迁移提醒。
- SaaS 停止新租户开通弃用模块；私有化客户按合同保留升级窗口。

## 4. 发布流程

```text
提案 -> 兼容性评审 -> Minor 发布并标记 deprecated -> 迁移演练
     -> 观察窗口 -> Major 发布 -> 删除旧实现 -> 更新 CHANGELOG
```

## 5. 发布门禁

当前由代码和测试自动保证：

- `ModuleRegistry` 校验 manifest 版本、最低平台版本、contract version、权限、事件和命名冲突。
- `run_module_contract_suite` 校验模块运行时、Router、配置 schema、核心能力依赖和租户隔离探针。
- `tests/infra` 和 `scripts/migration_drill.py` 覆盖 migration upgrade/downgrade/upgrade。

发布评审必须补充：

- 对已发布权限和事件做版本快照比对，禁止无迁移地删除或改名。
- 使用上一版本配置 fixture 回放租户配置兼容性。
- 对弃用模块确认替代方案、迁移通知和回滚路径。
