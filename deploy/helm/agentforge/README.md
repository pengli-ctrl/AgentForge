# AgentForge Helm Chart

该 Chart 用于 AgentForge 3.1.0 私有化部署。它部署无状态应用组件，并连接客户已有的 PostgreSQL、Temporal、MinIO/S3、Valkey/Redis 和 Kafka。

## 包含组件

- API Deployment；
- Temporal Worker Deployment；
- Outbox Worker Deployment；
- pre-install/pre-upgrade Migration Job；
- Service、Gateway、HTTPRoute、RateLimitPolicy；
- Ingress 兼容模板；
- ServiceAccount 和 ConfigMap。

Migration Job 执行：

```text
alembic upgrade head
```

## 前置条件

- Kubernetes 1.27+；
- Helm 3；
- 可访问的 PostgreSQL 15+、Temporal 1.32+、MinIO/S3、Valkey/Redis 7+ 和 Kafka；
- 已推送的 AgentForge 镜像；
- 已创建的 Kubernetes Secret；
- 使用 Gateway API 时，集群已安装 Gateway API CRD、Envoy Gateway controller 和对应 GatewayClass。

## Secret

Chart 通过 `existingSecret` 引用 Secret，不在 values 或模板中保存明文 Secret。可先创建：

```bash
kubectl create namespace agentforge

kubectl -n agentforge create secret generic agentforge-secrets \
  --from-literal=AGENTFORGE_ADMIN_API_KEY='<generated>' \
  --from-literal=AGENTFORGE_API_KEYS='{"<tenant-key>":"tenant-a"}' \
  --from-literal=AGENTFORGE_DATABASE_URL='postgresql+asyncpg://...' \
  --from-literal=AGENTFORGE_OBJECT_STORE_ACCESS_KEY='<access-key>' \
  --from-literal=AGENTFORGE_OBJECT_STORE_SECRET_KEY='<secret-key>'
```

推荐使用 Vault/External Secrets Operator 创建 Secret。模块中的外部凭据应通过 `secret_refs` 引用 Secret Provider。

可选集成配置包括：

- OIDC：`AGENTFORGE_OIDC_ISSUER_URL`、`AGENTFORGE_OIDC_AUDIENCE`、`AGENTFORGE_OIDC_JWKS_URL`；
- OPA：`AGENTFORGE_OPA_URL`、`AGENTFORGE_OPA_POLICY_PATH`；
- LiteLLM：`AGENTFORGE_LITELLM_PROXY_URL`、`AGENTFORGE_LITELLM_API_KEY`；
- Valkey 限流：`AGENTFORGE_RATE_LIMIT_ENABLED`、`AGENTFORGE_RATE_LIMIT_BACKEND=valkey`；
- Prompt：`AGENTFORGE_PROMPT_REGISTRY_BACKEND=langfuse`。

OIDC、OPA、Langfuse 和 Redis ContextStore 可能需要 composition root 显式完成适配器接线；仅设置环境变量不等价于生产链路已启用。

## 安装

```bash
helm upgrade --install agentforge deploy/helm/agentforge \
  -n agentforge \
  --create-namespace \
  --set image.repository=registry.example.com/agentforge \
  --set image.tag=3.1.0 \
  --set existingSecret=agentforge-secrets
```

默认启用：

- 2 个 API 副本；
- 1 个 Temporal Worker；
- 1 个 Outbox Worker；
- Migration Job；
- ClusterIP Service；
- 非 root、只读根文件系统、drop 全部 capabilities。

默认入口：

- `ingress.enabled=false`；
- `edgeGateway.enabled=false`；
- 私有化环境必须按控制器能力选择 Gateway API 或 Ingress，并配置 TLS、域名、WAF 和网络策略。

## Envoy Gateway / Gateway API

启用 Helm 资源：

```bash
helm upgrade --install agentforge deploy/helm/agentforge \
  -n agentforge \
  --set existingSecret=agentforge-secrets \
  --set edgeGateway.enabled=true \
  --set edgeGateway.gatewayClassName=eg
```

Chart 会渲染：

- `Gateway`；
- `HTTPRoute`；
- `edgeGateway.rateLimit.enabled=true` 时的 `RateLimitPolicy`。

Chart 不安装 Envoy Gateway controller，不创建 GatewayClass，也不管理 TLS 证书和 DNS。默认 SSE 配置：

```text
edgeGateway.sse.idleTimeout=300s
edgeGateway.sse.maxDuration=1800s
```

Ingress 仅作为兼容回退，不是默认入口。不要把 `ingress.enabled=true` 与 Gateway API 同时当作两套生产入口长期并行运行。

## 外部依赖

Chart 默认不托管：

- PostgreSQL；
- Temporal；
- MinIO/S3；
- Valkey/Redis；
- Kafka；
- OTel Collector、Langfuse 或企业 IdP。

可通过 `config` 覆盖连接配置，通过 `existingSecret` 注入敏感值。

## 验证

```bash
helm lint deploy/helm/agentforge
helm template agentforge deploy/helm/agentforge -n agentforge \
  --set existingSecret=agentforge-secrets

helm template agentforge deploy/helm/agentforge -n agentforge \
  --set edgeGateway.enabled=true > /tmp/agentforge-gateway.yaml
kubectl apply --dry-run=server -f /tmp/agentforge-gateway.yaml

kubectl -n agentforge rollout status deploy/agentforge-agentforge-api
kubectl -n agentforge rollout status deploy/agentforge-agentforge-worker
kubectl -n agentforge rollout status deploy/agentforge-agentforge-outbox-worker
```

健康检查：

```text
GET /health/live
GET /health/ready
```

`/health/live` 表示进程存活，`/health/ready` 表示应用已初始化；两者都不是数据库、Temporal、Valkey 或对象存储的深度健康检查。

## 版本

- Chart version：`3.1.0`
- App version：`3.1.0`
- Migration target：`20261021_0032`

镜像 tag、Chart version 和应用 version 必须保持一致。

## 私有化交付说明

交付拓扑、Secret 注入和基础安装步骤见：

[`docs/security/PRIVATE_DELIVERY.md`](../../../docs/security/PRIVATE_DELIVERY.md)

本文不承诺生产 HA、备份恢复、灾备或客户现场验收。