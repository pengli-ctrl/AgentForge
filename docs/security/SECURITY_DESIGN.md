# 安全设计

## 1. 定位

AgentForge 的安全能力用于验证企业 AI 平台的默认边界和实现方式，不代表已经完成客户现场的安全认证、合规验收或生产加固。

核心原则：

- 默认拒绝，而不是默认放行；
- 权限、租户和模块边界在 API 与应用层双重校验；
- Secret 不进入明文配置、日志、审计或响应；
- 外部副作用必须可审计、幂等、可重试；
- 高风险动作不能只依赖模型判断。

## 2. 身份与权限

- API Key 默认 fail-closed；未配置管理密钥或租户密钥时拒绝启动。
- API Key 使用常量时间比较，并绑定 `tenant_id`。
- Admin Key 与租户 Key 权限分离。
- RBAC、声明式策略、租户状态和模块启用状态共同参与授权。
- 高风险写回同时经过 Policy/RBAC 和人工审批边界。
- OIDC 提供 Provider Port、Principal、Bearer Token 和租户/权限校验；真实 IdP discovery、JWKS 与 group claim 映射按客户环境接入。

## 3. 租户隔离

- 模块 API 检查租户生命周期和模块启用状态。
- 仓储查询、缓存键、Audit、Outbox、Quota、Cost 和事件载荷显式包含 `tenant_id`。
- 跨租户 list/get 返回空、404 或 403，不能泄露资源是否存在。
- suspended/cancelled 租户在模块 API 边界 fail-closed。
- 模块契约套件提供 tenant isolation probe。

## 4. Secret 与密钥

- 模块配置中的敏感值只能使用 `secret_refs`。
- 支持 `env://`、`vault://`、`kms://`、`secret://`。
- `SecretValue.reveal()` 是显式访问入口；字符串表示只输出引用和 fingerprint。
- 支持 Secret 原地替换和版本标记。
- Helm Chart 引用已有 Kubernetes Secret，不在 values 中保存明文。
- 密钥托管、轮换、权限策略和灾备需要按客户环境落地。

## 5. 审计、脱敏与数据生命周期

- Audit 支持 JSON/CSV 查询、导出和租户过滤。
- 导出默认递归脱敏 Bearer Token、邮箱、电话、身份证号和敏感 key。
- Audit 支持按租户保留期清理，并要求确认值匹配 `tenant_id`。
- PII 删除编排支持模块注册 eraser，并写入脱敏 Audit/Outbox。
- 删除过程区分成功和部分失败，避免把部分删除误报为全部完成。
- 附件下载 URL 有效期为 1-3600 秒，默认 300 秒。

## 6. Webhook 与 Connector

- 通用 IM Webhook 支持 HMAC-SHA256 验签。
- Feishu 回调支持签名、加密和 verification token 配置。
- 回调支持时间窗口防重放。
- Connector 支持注册、allow-list、幂等和审计。
- OpenAPI Connector 提供有界重试和限流。
- WAF、IP allow-list、DLP 和外部 API 网络策略属于部署环境边界。

## 7. 限流、缓存与事件可靠性

- Valkey 支持限流、`retry_after`、TTL 缓存和分布式锁。
- Circuit Breaker 与请求放大保护限制故障扩散。
- 配额感知模型网关提供租户级硬门禁。
- Outbox 支持 handler receipt、retry、DLQ、replay 和 discard。
- 缓存必须包含租户、权限和数据版本边界；高风险或强一致场景禁止使用语义缓存。

## 8. 容器与交付默认值

Helm Chart 包含：

- API Deployment；
- Temporal Worker Deployment；
- Outbox Worker Deployment；
- Migration Job；
- Service、Ingress、ServiceAccount 和 ConfigMap。

安全默认值：

- `runAsNonRoot=true`；
- `readOnlyRootFilesystem=true`；
- `allowPrivilegeEscalation=false`；
- 丢弃全部 Linux capabilities；
- API 提供 `/health/live` 和 `/health/ready`；
- Secret 通过 `envFrom` 注入，不写入镜像或 ConfigMap。

## 9. 明确边界

以下内容不作为仓库已经完成的承诺：

- 客户真实 IdP discovery、JWKS、签名校验和 group claim 映射；
- 客户 Vault/KMS 的托管、轮换、灾备和权限验收；
- WAF、DLP、网络策略与出站访问控制；
- PostgreSQL、Temporal、MinIO、Valkey 的高可用和容量验证；
- 镜像 CVE/SBOM、签名、来源证明和制品仓库准入；
- Kubernetes 安装、升级、回滚和灾备演练。

漏洞报告流程见仓库根目录的 `SECURITY.md`。