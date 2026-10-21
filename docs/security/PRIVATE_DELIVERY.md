# 私有化交付基线

## 1. 定位

AgentForge 提供一套可安装的 Helm 交付示例，用于验证同一套平台代码如何适配私有化环境。

本文不是生产运行手册，不承诺已经完成 HA、备份恢复、升级回滚、灾备或客户现场验收。

## 2. 交付拓扑

```text
                Ingress / Service
                       |
                 API Deployment
                       |
        +--------------+--------------+
        |                             |
Temporal Worker                Outbox Worker
        |                             |
        +---------- shared -----------+
                       |
  PostgreSQL / Temporal / MinIO / Valkey / Kafka
                 （外部基础设施）
```

Helm Chart 包含：

- API Deployment；
- Temporal Worker Deployment；
- Outbox Worker Deployment；
- Migration Job；
- Service、Ingress、ServiceAccount 和 ConfigMap。

Chart 不内置 PostgreSQL、Temporal、MinIO 或 Valkey。

## 3. Secret 注入

Chart 引用已有的 Kubernetes Secret，不在 `values.yaml` 中保存密钥：

```bash
kubectl create namespace agentforge

kubectl -n agentforge create secret generic agentforge-secrets \
  --from-literal=AGENTFORGE_ADMIN_API_KEY='<generated>' \
  --from-literal=AGENTFORGE_API_KEYS='<generated>' \
  --from-literal=AGENTFORGE_DATABASE_URL='<database-url>' \
  --from-literal=AGENTFORGE_TEMPORAL_ADDRESS='<temporal-address>' \
  --from-literal=AGENTFORGE_VALKEY_URL='<valkey-url>' \
  --from-literal=AGENTFORGE_OBJECT_STORE_ENDPOINT='<object-store-endpoint>' \
  --from-literal=AGENTFORGE_OBJECT_STORE_ACCESS_KEY='<access-key>' \
  --from-literal=AGENTFORGE_OBJECT_STORE_SECRET_KEY='<secret-key>'
```

需要补充的配置包括：

- `AGENTFORGE_EVENTS_IM_WEBHOOK_SECRET`；
- `AGENTFORGE_FEISHU_APP_SECRET`；
- `AGENTFORGE_SAAS_PLANS_JSON`；
- Connector 或外部系统凭据。

模块配置中的敏感值应使用 `vault://`、`kms://`、`secret://` 或 `env://` 引用，不写明文。

## 4. 安装示例

```bash
helm upgrade --install agentforge deploy/helm/agentforge \
  -n agentforge \
  --create-namespace \
  --set image.repository=registry.example.com/agentforge \
  --set image.tag=3.1.0 \
  --set existingSecret=agentforge-secrets
```

主要配置：

| 配置 | 默认值 | 说明 |
|---|---|---|
| `image.repository` | `agentforge` | 镜像仓库地址 |
| `image.tag` | `3.1.0` | 必须与应用版本一致 |
| `existingSecret` | `agentforge-secrets` | 已有 Kubernetes Secret |
| `api.replicas` | `2` | API 副本数 |
| `worker.replicas` | `1` | Temporal Worker 副本数 |
| `outboxWorker.replicas` | `1` | Outbox Worker 副本数 |
| `migration.enabled` | `true` | 部署前执行 Migration Job |
| `ingress.enabled` | `false` | 默认不创建 Ingress |

## 5. 基础验证

```bash
kubectl -n agentforge get pods
kubectl -n agentforge rollout status deploy/agentforge-agentforge-api
kubectl -n agentforge rollout status deploy/agentforge-agentforge-worker
kubectl -n agentforge rollout status deploy/agentforge-agentforge-outbox-worker
kubectl -n agentforge get jobs
```

健康检查：

```bash
kubectl -n agentforge port-forward svc/agentforge-agentforge 8000:80
curl -fsS http://localhost:8000/health/live
curl -fsS http://localhost:8000/health/ready
```

建议验证：

1. 无 API Key 请求返回 401，错误租户 Key 返回 403；
2. 租户模块开关、RBAC 和策略检查正常；
3. Audit 导出默认脱敏；
4. Outbox 无持续 failed，DLQ replay/discard 可用；
5. Secret 引用可解析，日志和响应中无 Secret 明文。

## 6. 边界

- 这是私有化交付基线，不是生产运维手册。
- 不包含客户环境的 HA、容量规划、备份恢复、灾备和升级回滚验收。
- 不包含真实 IdP、Vault/KMS、WAF/DLP 或供应链扫描的现场接入。
- 生产使用前必须结合客户基础设施完成独立设计和验收。