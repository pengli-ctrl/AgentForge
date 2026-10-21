# 基础设施集成

## 1. 定位

AgentForge 是可运行、可测试、可扩展的商业基线，不是已经完成生产验收的运维产品。本文说明平台如何与真实基础设施集成，以及当前测试覆盖范围。

基础设施用于验证架构边界和关键可靠性语义，不代表仓库已经提供高可用、容灾、容量规划或客户现场运维体系。

## 2. 组件边界

| 组件 | 职责 | 当前集成方式 |
|---|---|---|
| PostgreSQL 15+ | 平台主数据、模块数据、pgvector、Outbox、用量记录 | SQLAlchemy 异步仓储与 Alembic |
| Temporal 1.32+ | 持久 Workflow、Activity、Schedule、模块 Task Queue | 独立 Worker 与模块装配 |
| MinIO / S3 | 附件、发票和分片上传对象 | 对象存储 Port 与集成测试 |
| Valkey / Redis 7+ | 限流、JSON 缓存和分布式锁 | 协调组件与故障语义测试 |
| Kafka | Outbox 事件外发 | publisher、重试与 DLQ |
| OpenTelemetry / Prometheus / Grafana | Trace、指标与运行观测 | 可选观测配置 |

## 3. 真实基础设施测试

Linux/macOS/CI：

```bash
make test-infra
```

Windows PowerShell：

```powershell
./scripts/run_infra_tests.ps1
```

脚本会：

1. 启动 `deploy/platform/docker-compose.lite.yml`；
2. 等待 PostgreSQL、Valkey、MinIO 和 Temporal 可用；
3. 创建测试数据库；
4. 设置 `AGENTFORGE_RUN_INFRA_TESTS=1`；
5. 执行 `tests/infra`；
6. 执行 `upgrade -> downgrade -> upgrade` 迁移演练；
7. 停止 Compose 服务。

普通 `pytest` 会跳过真实基础设施测试，只有显式开启后才执行。

关键环境变量：

| 变量 | 用途 |
|---|---|
| `AGENTFORGE_RUN_INFRA_TESTS` | 设为 `1` 后启用真实基础设施测试 |
| `AGENTFORGE_INFRA_DATABASE_URL` | 集成测试 PostgreSQL URL |
| `AGENTFORGE_TEMPORAL_ADDRESS` | Temporal 地址 |
| `AGENTFORGE_TEMPORAL_NAMESPACE` | Temporal namespace |
| `AGENTFORGE_VALKEY_URL` | Valkey/Redis URL |
| `AGENTFORGE_OBJECT_STORE_*` | S3/MinIO 端点、凭据、bucket 和 region |
| `AGENTFORGE_MIGRATION_DRILL_DATABASE_URL` | 迁移演练专用数据库 |
| `AGENTFORGE_MIGRATION_DRILL_CONFIRM` | 迁移演练确认值 |

## 4. 数据与迁移

模块使用独立 migration namespace。当前主要数据域：

```text
platform
module_support
module_expense
module_asset_assets
```

集成测试覆盖：

- Alembic `upgrade head`；
- Support、Expense、Demo Asset schema；
- `tenant_id` 隔离；
- Outbox 持久化、publisher 和 handler；
- migration `upgrade -> downgrade -> upgrade`。

正式迁移以 `alembic/versions` 为准。

## 5. Temporal

主要 Task Queue：

```text
support-copilot
expense-copilot
asset-copilot
```

Temporal Worker 和 Outbox Worker 使用独立进程，可独立扩缩容。Schedule 初始化由模块 startup hook 完成，并保持幂等。

## 6. 对象存储

集成测试覆盖：

- 小于和大于分片阈值的上传；
- SHA-256 校验；
- 分片上传、完成和中断；
- presigned URL；
- metadata 与 content type；
- 对象存储不可用时的失败语义。

下载 URL 有效期限制为 1-3600 秒，默认 300 秒。

## 7. Valkey 与限流

集成测试覆盖：

- 固定窗口和滑动窗口限流；
- `retry_after`；
- JSON 缓存与 TTL；
- 分布式锁 `SET NX`；
- compare-and-delete 释放；
- 原子操作和过期行为。

## 8. Outbox、DLQ 与幂等

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

- `(event_id, handler_name)` 唯一，避免重复执行已完成的业务处理器；
- publisher 与 handler 分离，业务事务和事件投递不共享同一个失败边界；
- failed 事件支持 replay 和 discard，并保留审计线索；
- 事件处理器必须幂等，不能依赖“只会投递一次”。

## 9. 边界

- Compose 用于本地开发、演示和集成测试，不是高可用生产方案。
- 仓库不承诺已经完成客户环境的容量压测、灾备、HA 选型和运维验收。
- 私有化 Helm 仅提供交付形态示例，外部中间件由客户环境负责。
- 真实 IdP、Vault/KMS、WAF/DLP 和供应链扫描需要按目标环境接入。