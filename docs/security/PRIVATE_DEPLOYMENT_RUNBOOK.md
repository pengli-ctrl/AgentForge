# AgentForge 私有化部署运行手册

## 1. 前置条件

- Kubernetes 1.27+ 和 Helm 3。
- PostgreSQL 15+（推荐 17）、Temporal 1.32+、MinIO/S3 和 Valkey/Redis 7+。
- 可用的 Ingress Controller 和 TLS 证书。
- 已构建并推送到私有镜像仓库的 `agentforge:3.1.0` 镜像。
- 已准备备份目录、对象存储镜像工具 `mc` 和 `pg_dump`/`pg_restore`。
- 已确认许可证、网络策略、数据驻留和备份保留要求。

Helm Chart 只部署 AgentForge 应用组件，不托管 PostgreSQL、Temporal、MinIO 或 Valkey。

## 2. 创建 Secret

不要在命令行、Git 或 Helm values 中保存生产明文 Secret。推荐使用 Secret Manager、External Secrets Operator 或 Vault Agent 创建 Kubernetes Secret。

最小 Secret 示例：

```bash
kubectl create namespace agentforge

kubectl -n agentforge create secret generic agentforge-secrets \
  --from-literal=AGENTFORGE_ADMIN_API_KEY='<generated>' \
  --from-literal=AGENTFORGE_API_KEYS='{"<generated-tenant-key>":"tenant-a"}' \
  --from-literal=AGENTFORGE_DATABASE_URL='postgresql+asyncpg://<user>:<password>@<host>:5432/agentforge' \
  --from-literal=AGENTFORGE_OBJECT_STORE_ACCESS_KEY='<access-key>' \
  --from-literal=AGENTFORGE_OBJECT_STORE_SECRET_KEY='<secret-key>' \
  --from-literal=AGENTFORGE_EVENTS_IM_WEBHOOK_SECRET='<webhook-secret>' \
  --from-literal=AGENTFORGE_FEISHU_APP_SECRET='<feishu-secret>'
```

按需补充：

- `AGENTFORGE_FEISHU_ENCRYPT_KEY`
- `AGENTFORGE_FEISHU_VERIFICATION_TOKEN`
- `AGENTFORGE_FEISHU_APP_ID`
- `AGENTFORGE_SAAS_PLANS_JSON`
- Connector 或外部系统凭据

模块配置中的敏感值应使用 `secret_refs` 引用 `vault://`、`kms://`、`secret://` 或 `env://`，不要写明文。

## 3. Helm 安装

```bash
helm upgrade --install agentforge deploy/helm/agentforge \
  -n agentforge \
  --create-namespace \
  --set image.repository=registry.example.com/agentforge \
  --set image.tag=3.1.0 \
  --set existingSecret=agentforge-secrets
```

主要 values：

| 配置 | 默认值 | 说明 |
|---|---|---|
| `image.repository` | `agentforge` | 私有镜像仓库地址 |
| `image.tag` | `3.1.0` | 必须与应用版本一致 |
| `existingSecret` | `agentforge-secrets` | 已存在的 Kubernetes Secret |
| `api.replicas` | `2` | API 副本数 |
| `worker.replicas` | `1` | Temporal Worker 副本数 |
| `outboxWorker.replicas` | `1` | Outbox Worker 副本数 |
| `migration.enabled` | `true` | pre-install/pre-upgrade Migration Job |
| `ingress.enabled` | `false` | 默认不创建 Ingress |

生产部署必须通过环境专用 values 或外部 Secret 覆盖示例配置，不要把密码提交到 Git。

## 4. 部署组件

Chart 包含：

- API Deployment；
- Temporal Worker Deployment；
- Outbox Worker Deployment；
- Migration Job，执行 `alembic upgrade head`；
- Service、Ingress、ServiceAccount、ConfigMap。

安全默认：

- 非 root 用户运行；
- `readOnlyRootFilesystem=true`；
- `allowPrivilegeEscalation=false`；
- drop 全部 Linux capabilities；
- API 提供 `/health/live` 和 `/health/ready`；
- Secret 通过 `envFrom` 注入，不写入镜像或 ConfigMap。

## 5. 部署验证

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

验收项：

1. 无 API Key 请求返回 401，错误租户 Key 返回 403。
2. `/v1/admin/plans` 使用 Admin Key 可访问。
3. 租户模块开关、RBAC 和策略检查正常。
4. Audit 导出默认脱敏，附件下载 URL 不超过 3600 秒。
5. Outbox 无持续 failed，DLQ replay/discard 可用。
6. Temporal Schedule 和 Worker Task Queue 正常。
7. Secret 引用可解析，日志和响应中无 Secret 明文。

## 6. 数据库迁移演练

必须在测试数据库执行：

```bash
export AGENTFORGE_MIGRATION_DRILL_DATABASE_URL='postgresql+asyncpg://.../agentforge_test'
export AGENTFORGE_MIGRATION_DRILL_CONFIRM=agentforge
python scripts/migration_drill.py
```

脚本执行：

```text
upgrade 20261020_0028
upgrade head
downgrade 20261020_0028
upgrade head
```

报告写入 `dist/migration-drill.json`。URL 不含 `test` 时脚本默认拒绝执行。

## 7. 备份

数据库使用 PostgreSQL custom format，对象存储可选使用 `mc mirror`。

```bash
export AGENTFORGE_BACKUP_DATABASE_URL='postgresql://<user>:<password>@<host>:5432/agentforge'
export AGENTFORGE_BACKUP_DIR='/backup/agentforge'
export AGENTFORGE_OBJECT_STORE_ALIAS='agentforge'
export AGENTFORGE_BACKUP_BUCKET='agentforge'
bash scripts/backup_private.sh
```

生成：

- `agentforge-<timestamp>.dump`
- `agentforge-<timestamp>.dump.sha256`
- 配置对象存储时的 `objects-<timestamp>/`

注意：

- 数据库备份应使用与恢复环境兼容的 PostgreSQL 客户端版本。
- 对象存储 mirror 可能不是时点一致快照；生产应在存储层或快照系统配合下完成一致性备份。
- 备份文件应加密、异地保存，并设置保留期和访问控制。
- 定期执行恢复演练，不能只验证备份任务成功。

## 8. 恢复

恢复是破坏性操作，先停止 API、Worker 和 Outbox Worker，并确认目标数据库正确。

```bash
export AGENTFORGE_BACKUP_DATABASE_URL='postgresql://<user>:<password>@<host>:5432/agentforge'
export AGENTFORGE_RESTORE_CONFIRM=agentforge
bash scripts/restore_private.sh /backup/agentforge/agentforge-<timestamp>.dump
```

脚本行为：

1. 若 checksum 文件存在，先执行 SHA-256 校验；
2. 使用 `pg_restore --clean --if-exists` 恢复数据库；
3. 执行 `alembic upgrade head`。

数据库恢复后还需：

1. 从对象存储备份恢复 `objects-<timestamp>/`；
2. 校验附件和 presigned URL；
3. 检查 Outbox failed 和 Temporal 工作流状态；
4. 执行 smoke test；
5. 重新启动 API、Worker 和 Outbox Worker。

## 9. 升级

```bash
helm upgrade agentforge deploy/helm/agentforge \
  -n agentforge \
  --set image.repository=registry.example.com/agentforge \
  --set image.tag=3.2.0 \
  --set existingSecret=agentforge-secrets
```

升级流程：

1. 阅读目标版本 Release Notes 和 Migration Guide。
2. 备份数据库和对象存储。
3. 在 staging 执行 migration drill。
4. 停止或缩容 Outbox Worker，避免迁移期间写旧 schema。
5. 执行 Helm upgrade，确认 Migration Job 成功。
6. 依次确认 API、Worker、Outbox Worker readiness。
7. 验证租户、模块、Audit、Outbox 和关键业务路径。
8. 观察错误率、延迟、DLQ 和 Temporal 重试。

## 10. 回滚

应用回滚：

```bash
helm rollback agentforge <REVISION> -n agentforge
```

数据库回滚：

```bash
alembic downgrade 20261020_0028
```

注意：

- 降级 0032 会删除租户账号和用量数据。
- 降级 0031 会删除 Outbox handler receipts。
- 降级 0029 会删除租户模块覆盖配置字段。
- 如果新商业数据必须保留，优先恢复升级前备份，而不是只执行 downgrade。
- 回滚前停止 Worker 和 Outbox Worker，确认 schema 与旧应用兼容。
- 回滚后检查 Temporal Schedule、未完成工作流和 Outbox pending/failed 事件。

## 11. 故障排查

| 现象 | 处理 |
|---|---|
| API 无法启动或 readiness 失败 | 检查容器日志、Migration Job、认证配置和启动异常 |
| readiness 正常但业务请求返回 503 | 检查数据库、Temporal、Valkey、对象存储和对应服务日志 |
| 服务启动提示无认证配置 | 配置 `AGENTFORGE_ADMIN_API_KEY` 或 `AGENTFORGE_API_KEYS` |
| Secret 无法解析 | 检查引用 scheme、Vault/KMS 权限和 Secret 版本 |
| Outbox 持续 failed | 查询 `last_error`，修复下游后 replay；确认不可恢复时 discard |
| Temporal Worker 无任务 | 检查 namespace、Task Queue、Schedule 和 Worker 日志 |
| 附件下载 403 | 检查 presigned TTL、bucket policy、时钟和对象是否存在 |
| 租户 403 | 检查租户状态、模块开关、API Key 绑定和 RBAC |
| migration 无法 downgrade | 检查活动连接、schema 依赖和备份可用性 |
| PII 删除部分失败 | 查看 `tenant.data.erase_partial`，修复对应模块 eraser 后重试 |

## 12. 上线检查

- [ ] 已执行 Helm lint/template/dry-run。
- [ ] 已执行数据库 migration drill。
- [ ] 已完成数据库和对象存储恢复演练。
- [ ] 已对接真实 IdP、Vault/KMS、TLS、WAF 和监控。
- [ ] 已完成镜像 CVE/SBOM 扫描和制品签名。
- [ ] 已配置告警、日志保留、DLQ 巡检和维护窗口。
- [ ] 已验证回滚和灾难恢复流程。
