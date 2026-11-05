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

- API Key 默认 fail-closed；生产环境未配置管理密钥或租户密钥时拒绝启动。
- API Key 使用常量时间比较，并绑定 `tenant_id`。
- Admin Key 与租户 Key 权限分离。
- RBAC、声明式策略、租户状态和模块启用状态共同参与授权。
- 高风险写回同时经过 Policy/RBAC 和人工审批边界。
- OIDC 提供 JWKS/RS256 校验器、Bearer 认证器、issuer、audience、exp 和 nbf 校验，以及 tenant/admin claim 检查。
- OIDC mode 需要 composition root 注入 validator；未完成注入时保持 fail-closed，不能用 API Key 默认值伪装 OIDC 已启用。
- OPA adapter 支持 allow、deny、requires_approval 和 approval_ref；默认运行时仍使用本地 PolicyEngine，切换到 OPA 需要显式装配和不可用时的 fail-closed 验证。
- OpenFGA 仅作为关系权限适配边界，不是当前默认授权引擎。

## 3. 租户隔离

- 模块 API 检查租户生命周期和模块启用状态。
- 仓储查询、缓存键、Audit、Outbox、Quota、Cost 和事件载荷显式包含 `tenant_id`。
- 跨租户 list/get 返回空、404 或 403，不能泄露资源是否存在。
- suspended/cancelled 租户在模块 API 边界 fail-closed。
- 模块契约套件提供 tenant isolation probe。
- RAG 检索必须绑定租户、权限和文档版本，不能先返回全量向量再依赖上游补过滤。

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
- Feishu、ERP、Webhook 等外部写回必须使用幂等键；超时不能直接等价为失败并盲目重试。
- WAF、IP allow-list、DLP 和外部 API 网络策略属于部署环境边界。

## 7. 限流、缓存与事件可靠性

- Valkey 支持原子 Token Bucket 限流、`retry_after`、JSON 缓存和分布式锁。
- 平台限流中间件支持 Memory / Valkey 后端；默认关闭，生产必须显式开启并验证故障策略。
- Redis ContextStore 支持租户/会话/DAG 命名空间、TTL 和访问日志；默认仍使用 Memory，生产接线需显式完成。
- Circuit Breaker 与请求放大保护限制故障扩散。
- 配额感知模型网关提供租户级硬门禁。
- Outbox 支持 handler receipt、retry、DLQ、replay 和 discard。
- 缓存必须包含租户、权限和数据版本边界；高风险或强一致场景禁止使用语义缓存。
- AI Gateway 只负责模型选择、Fallback、缓存和成本，不承担租户授权。

## 8. 接入网关与容器交付

Helm Chart 包含：

- API Deployment；
- Temporal Worker Deployment；
- Outbox Worker Deployment；
- Migration Job；
- Gateway API `Gateway`、`HTTPRoute`、可选 `RateLimitPolicy`；
- Ingress 兼容模板；
- Service、ServiceAccount 和 ConfigMap。

安全默认值：

- Gateway API 和 Ingress 都默认关闭，按环境选择；
- 启用 Gateway API 时必须由集群提供 CRD、controller 和 GatewayClass；
- `runAsNonRoot=true`；
- `readOnlyRootFilesystem=true`；
- `allowPrivilegeEscalation=false`；
- 丢弃全部 Linux capabilities；
- API 提供 `/health/live` 和 `/health/ready`；
- Secret 通过 `envFrom` 注入，不写入镜像或 ConfigMap。

## 9. 明确边界

以下内容不作为仓库已经完成的承诺：

- 客户真实 IdP discovery、group claim 映射、OIDC composition 接线和故障演练；
- OPA 在生产默认路径的完整装配、策略分发、双跑和回滚；
- 客户 Vault/KMS 的托管、轮换、灾备和权限验收；
- WAF、DLP、网络策略与出站访问控制；
- PostgreSQL、Temporal、MinIO、Valkey 的高可用和容量验证；
- 镜像 CVE/SBOM、签名、来源证明和制品仓库准入；
- Kubernetes 安装、升级、回滚和灾备演练。

漏洞报告流程见仓库根目录的 `SECURITY.md`。