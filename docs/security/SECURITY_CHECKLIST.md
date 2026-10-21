# AgentForge 安全检查清单

> 状态说明：`[x]` 表示代码和自动化测试已覆盖；`[ ]` 表示需要目标环境、第三方系统或运维流程现场验收，不代表功能缺失。

## 1. 身份认证与授权

- [x] API Key 默认 fail-closed；生产未配置密钥时拒绝启动。
- [x] API Key 与 `tenant_id` 绑定，跨租户访问返回 403。
- [x] Admin Key 与租户 Key 分离。
- [x] RBAC 角色、权限和用户角色赋值已实现。
- [x] OIDC Provider Port、Principal、Bearer Token 和过期检查已实现。
- [x] OIDC Principal 强制校验 `tenant_id` 和 permission。
- [x] 高风险写回同时经过 Policy/RBAC 和人工审批边界。
- [ ] 对接客户真实 IdP discovery、JWKS、签名校验和 group claim 映射。

## 2. 租户隔离

- [x] 模块 API 检查租户模块启用状态和租户生命周期状态。
- [x] Support、Expense 和 Demo Asset 数据均显式携带 `tenant_id`。
- [x] 仓储查询、缓存键和事件载荷保持租户隔离。
- [x] list/get/module disable 等跨租户访问返回空、404 或 403。
- [x] Outbox、Audit、配置、Cost 和 Quota 均按 `tenant_id` 查询。
- [x] suspended/cancelled 租户在模块 API 边界 fail-closed。
- [x] 模块契约套件支持 tenant isolation probe。

## 3. Secret 与密钥

- [x] 模块配置中的敏感字段只能使用 `secret_refs`。
- [x] 支持 `env://`、`vault://`、`kms://`、`secret://`。
- [x] `SecretValue.reveal()` 是显式访问入口。
- [x] `str`/`repr` 不输出 Secret 明文，只输出引用和 fingerprint。
- [x] 支持原地替换 Secret 和版本标记。
- [x] Helm Chart 使用 `existingSecret`，Chart values 不保存 Secret。
- [ ] 在客户 Vault/KMS 中完成密钥托管、轮换、权限策略和灾备演练。
- [ ] 确认 CI、日志、备份和运维终端不会捕获 Secret。

## 4. 审计、脱敏与数据生命周期

- [x] Audit 支持 JSON/CSV 查询、导出和租户过滤。
- [x] 导出默认递归脱敏 Bearer Token、邮箱、电话、身份证号和敏感 key。
- [x] Audit 支持按租户保留期清理，并要求确认值匹配 `tenant_id`。
- [x] PII 删除编排支持模块注册 eraser，并写入脱敏 Audit/Outbox。
- [x] 删除过程支持成功和部分失败区分。
- [x] 附件下载 URL 限定为 1-3600 秒，默认 300 秒。
- [ ] 按客户数据分类完成日志、备份、对象存储和第三方系统的保留期验收。

## 5. Webhook 与 Connector

- [x] 通用 IM Webhook 支持 HMAC-SHA256 验签。
- [x] Feishu 回调支持签名、加密和 verification token 配置。
- [x] Feishu 回调支持时间窗口防重放参数。
- [x] Connector 支持注册、allow-list、幂等和审计。
- [x] OpenAPI Connector 支持有界重试和限流。
- [x] Webhook/Connector Secret 通过 Secret Reference 配置。
- [ ] 对接客户 WAF、IP allow-list、DLP 和外部 API 网络策略。

## 6. 限流、缓存与锁

- [x] Valkey 支持限流和 `retry_after`。
- [x] Valkey JSON 缓存支持 TTL。
- [x] 分布式锁使用 `SET NX` 和 compare-and-delete 释放。
- [x] CircuitBreaker 和请求放大保护已实现。
- [x] 配额感知模型网关支持硬门禁。
- [x] Outbox 支持 handler receipt、retry、DLQ、replay 和 discard。
- [ ] 在目标环境验证 Valkey/Redis Cluster、跨可用区、故障切换和容量。

## 7. 部署与容器

- [x] Helm Chart 包含 API、Temporal Worker、Outbox Worker 和 Migration Job。
- [x] `runAsNonRoot=true`，禁止权限提升，只读根文件系统，drop 全部 capabilities。
- [x] API 配置 readiness/liveness probe。
- [x] PostgreSQL、Temporal、MinIO 和 Valkey 均通过 ConfigMap/Secret 配置。
- [x] Docker Compose、Helm 和真实基础设施测试入口已提供。
- [x] 数据库迁移 Job 在 API/Worker 启动前执行。
- [ ] 在目标 Kubernetes 集群执行 Helm lint、template、dry-run、安装、升级和回滚。
- [ ] 配置 Ingress TLS、WAF、网络策略、Pod Security、资源配额和节点隔离。

## 8. 供应链与发布

- [x] Flake8、isort、black、mypy 和全量测试门禁。
- [x] `scripts/verify_release.py` 校验版本、迁移头和 CI job。
- [x] `scripts/security_scan.py` 扫描硬编码密钥和高风险调用。
- [x] 私有化包构建支持确定性归档和 checksum。
- [x] `.env` 和本地 Secret 文件不进入 Git。
- [ ] 对目标镜像执行 CVE/SBOM 扫描、签名、来源证明和制品仓库准入。
- [ ] 对 Helm Chart 和发布包执行 checksum、签名和供应链验收。

## 9. 上线前必须完成

1. 设置强随机 `AGENTFORGE_ADMIN_API_KEY` 和租户 API Keys，验证缺省密钥已移除。
2. 在测试环境执行 migration drill：`upgrade -> downgrade -> upgrade`。
3. 执行备份与恢复演练，确认数据库、对象存储和 Outbox 状态一致。
4. 验证真实 IdP、Vault/KMS、TLS、WAF、限流和高可用中间件。
5. 验证 DLQ replay/discard、Temporal Worker 重启和 Outbox 重试。
6. 记录安全扫描、镜像扫描、自动化验证结果和上线审批证据。