# 生产基础设施集成

## 1. 支持的基础设施

AgentForge 的生产路径使用：

- PostgreSQL 15+（推荐 17），承载平台及模块主数据、pgvector、Outbox 和用量记录；
- Temporal 1.32+，承载持久 Workflow、Activity、Schedule 和模块 Task Queue；
- MinIO 或 S3 兼容对象存储，承载附件、发票和上传对象；
- Valkey/Redis 7+，承载限流、JSON 缓存和分布式锁；
- Kafka，用于 Outbox 事件外发；
- OpenTelemetry Collector、Prometheus 和 Grafana，用于观测。

## 2. 真实基础设施测试

Linux/macOS/CI：

```bash
make test-infra
```

Windows PowerShell：

```powershell
./scripts/run_infra_tests.ps1
```

底层等价入口：

```bash
bash scripts/run_infra_tests.sh
```

脚本执行顺序：

1. 启动 `deploy/platform/docker-compose.lite.yml`；
2. 等待 PostgreSQL、Valkey、MinIO、Temporal 可用；
3. 创建 `agentforge_test`；
4. 设置 `AGENTFORGE_RUN_INFRA_TESTS=1`；
5. 执行 `tests/infra`；
6. 创建 `agentforge_drill` 并执行 migration drill；
7. 停止 Compose 服务。

普通 `pytest` 运行时，`tests/infra` 默认跳过。只有显式设置 opt-in 环境变量后才执行真实服务测试。

## 3. 环境变量

| 变量 | 默认值/用途 |
|---|---|
| `AGENTFORGE_RUN_INFRA_TESTS` | 设为 `1` 后启用真实基础设施测试 |
| `AGENTFORGE_INFRA_DATABASE_URL` | `postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge_test` |
| `AGENTFORGE_TEMPORAL_ADDRESS` | `localhost:7233` |
| `AGENTFORGE_TEMPORAL_NAMESPACE` | `default` |
| `AGENTFORGE_VALKEY_URL` | `redis://localhost:6379/0` |
| `AGENTFORGE_OBJECT_STORE_ENDPOINT` | `http://localhost:9000` |
| `AGENTFORGE_OBJECT_STORE_ACCESS_KEY` | S3 访问密钥 |
| `AGENTFORGE_OBJECT_STORE_SECRET_KEY` | S3 Secret Key |
| `AGENTFORGE_OBJECT_STORE_BUCKET` | `agentforge-infra-test` |
| `AGENTFORGE_OBJECT_STORE_REGION` | `us-east-1` |
| `AGENTFORGE_MIGRATION_DRILL_DATABASE_URL` | migration drill 专用测试数据库 |
| `AGENTFORGE_MIGRATION_DRILL_CONFIRM` | 必须为 `agentforge` |

生产环境不应使用 Compose 中的默认密码或示例密钥。

## 4. PostgreSQL

集成测试覆盖：

- Alembic `upgrade head`；
- Support/Expense/Demo Asset 模块 schema；
- `tenant_id` 隔离；
- JSON SLA 字段读写；
- Outbox 持久化、publisher 和 handler 处理；
- migration `upgrade -> downgrade -> upgrade` 演练。

主要数据命名空间：

```text
platform
module_support
module_expense
public（Demo Asset 使用 module_asset_assets 表）
```

迁移入口：

```bash
AGENTFORGE_DATABASE_URL='postgresql+asyncpg://...' alembic upgrade head
alembic current
```

生产升级前必须备份，并在测试数据库执行：

```bash
export AGENTFORGE_MIGRATION_DRILL_DATABASE_URL='postgresql+asyncpg://.../agentforge_test'
export AGENTFORGE_MIGRATION_DRILL_CONFIRM=agentforge
python scripts/migration_drill.py
```

脚本拒绝 URL 中不含 `test` 的数据库，除非显式设置 `AGENTFORGE_ALLOW_NON_TEST_DRILL=true`。

## 5. Temporal

集成测试覆盖：

- 创建 Schedule；
- 启动 Worker；
- 按模块 Task Queue 路由；
- Activity 超时、重试和失败恢复；
- 多 Task Queue 隔离。

当前主要 Task Queue：

```text
support-copilot
expense-copilot
asset-copilot
```

Temporal Worker 和 Outbox Worker 使用独立 Deployment，可独立扩缩容。Schedule 的初始化由模块 startup hook 执行，并应保持幂等。

## 6. MinIO / S3

集成测试覆盖：

- 小于分片阈值和大于分片阈值的上传；
- SHA-256 校验；
- 分片上传、完成和中断；
- presigned URL；
- Metadata 和 content type；
- 对象存储不可用时的失败语义。

生产要求：

- 使用独立 bucket 和最小权限访问密钥；
- 启用服务端加密和版本/生命周期策略；
- 下载 URL 有效期限定在 1-3600 秒；
- 备份时同时备份数据库和对象存储；
- 不要把 Access Key、Secret Key 写入镜像、Git 或 Helm values。

## 7. Valkey / Redis

集成测试覆盖：

- 固定窗口/滑动窗口限流和 `retry_after`；
- JSON 缓存与 TTL；
- 分布式锁；
- `SET NX` 和 compare-and-delete 释放；
- 原子操作和过期行为。

生产建议使用 Valkey/Redis 7+ 高可用方案，启用认证、TLS、持久化和跨可用区部署。Valkey 不可用时，需要明确限流与缓存组件的降级行为。

## 8. Outbox、DLQ 与事件

```text
pending
  ├─ handler claim -> processing -> completed
  ├─ publisher success -> published
  └─ failure -> attempts + 1
                 └─ attempts >= max_attempts -> failed (DLQ)

failed
  ├─ replay -> pending
  └─ discard -> discarded
```

关键语义：

- Handler receipt 以 `(event_id, handler_name)` 唯一，避免重试重复执行已完成业务处理器。
- 已成功 handler 不会因 publisher 重试再次执行。
- Publisher 至少一次投递，消费端必须幂等。
- `failed` 记录保留 payload、`attempts` 和 `last_error`。
- DLQ replay 必须确认下游依赖已恢复；不可恢复事件执行 discard，并保留审计轨迹。
- 业务写入与 Outbox enqueue 应在同一事务边界内提交。

## 9. CI

基础设施 Integration job 在 Ubuntu 上启动 Docker Compose，执行：

```bash
bash scripts/run_infra_tests.sh
```

Docker 不可用时该 job 失败，而不是静默跳过；普通单元测试仍可在无 Docker 环境执行。

## 10. 故障排查

| 现象 | 排查 |
|---|---|
| infra tests 全部 skipped | 确认 `AGENTFORGE_RUN_INFRA_TESTS=1` |
| Temporal 连接失败 | 检查 `temporal` 容器、7233 端口和 namespace |
| MinIO 403 | 检查 access key、secret、bucket、region 和 endpoint |
| migration downgrade 失败 | 确认只对测试库执行；检查 schema 依赖和活动连接 |
| API 无法启动或 ready 失败 | 查看启动日志、Migration Job 和认证配置；ready 仅表示应用进程可服务 |
| ready 正常但业务请求失败 | 检查数据库、Temporal、Valkey、对象存储及对应服务日志 |
| Outbox failed | 查询事件 `last_error`，修复依赖后 replay；不可恢复事件 discard |
| handler 重复执行 | 检查 migration `0031_outbox_handler_receipts` 和 receipt 唯一约束 |
| 上传中断 | 检查 upload session 状态、对象存储 multipart 和过期清理 |
| 限流失效 | 检查 Valkey 连接、键命名空间和脚本原子性 |

## 11. 生产边界

- Compose 是本地/演示/测试编排，不是高可用生产平台。
- 生产使用外部 PostgreSQL、Temporal、MinIO/S3 和 Valkey，并由云厂商或客户运维团队提供备份、监控和灾备。
- Helm Chart 不自动配置 WAF、DLP、IdP、Vault/KMS 或镜像扫描。
- 真实基础设施测试通过不代表目标客户环境的容量、网络和故障恢复已经验收。
