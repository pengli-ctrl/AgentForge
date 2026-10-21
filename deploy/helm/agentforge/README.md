# AgentForge Helm Chart

该 Chart 用于 AgentForge 3.1.0 私有化部署。它部署无状态应用组件，并连接客户已有的 PostgreSQL、Temporal、MinIO/S3 和 Valkey/Redis。

## 包含组件

- API Deployment；
- Temporal Worker Deployment；
- Outbox Worker Deployment；
- pre-install/pre-upgrade Migration Job；
- Service、Ingress、ServiceAccount、ConfigMap。

Migration Job 执行：

```text
alembic upgrade head
```

## 前置条件

- Kubernetes 1.27+；
- Helm 3；
- 可访问的 PostgreSQL 15+、Temporal 1.32+、MinIO/S3 和 Valkey/Redis 7+；
- 已推送的 AgentForge 镜像；
- 已创建的 Kubernetes Secret。

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

Ingress 默认关闭，生产需配置 TLS、域名、WAF 和网络策略。

## 外部依赖

Chart 默认不托管：

- PostgreSQL；
- Temporal；
- MinIO/S3；
- Valkey/Redis；
- Kafka（生产由 Outbox Worker 配置接入）。

可通过 `config` 覆盖连接配置，通过 `existingSecret` 注入敏感值。

## 验证

```bash
helm lint deploy/helm/agentforge
helm template agentforge deploy/helm/agentforge -n agentforge \
  --set existingSecret=agentforge-secrets

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

## 运维手册

安装、备份、恢复、迁移演练、升级和回滚的完整步骤见：

[`docs/security/PRIVATE_DEPLOYMENT_RUNBOOK.md`](../../../docs/security/PRIVATE_DEPLOYMENT_RUNBOOK.md)
