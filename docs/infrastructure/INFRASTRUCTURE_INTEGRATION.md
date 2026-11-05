# 基础设施集成

## 1. 定位

AgentForge 是可运行、可测试、可扩展的商业基线，不是已经完成生产验收的运维产品。本文说明平台如何与真实基础设施、本地容器和外部适配器集成，以及当前测试覆盖范围。

基础设施用于验证架构边界和关键可靠性语义，不代表仓库已经提供高可用、容灾、容量规划或客户现场运维体系。

## 2. 组件边界

| 组件 | 职责 | 当前集成方式 |
|---|---|---|
| PostgreSQL 15+ | 平台主数据、模块数据、pgvector、Outbox、用量记录 | SQLAlchemy 异步仓储与 Alembic |
| Temporal 1.32+ | 持久 Workflow、Activity、Schedule、模块 Task Queue | 独立 Worker、模块装配和 DAG Workflow 定义 |
| MinIO / S3 | 附件、发票和分片上传对象 | 对象存储 Port、S3 adapter 与集成测试 |
| Valkey / Redis 7+ | Token Bucket 限流、JSON 缓存、分布式锁、ContextStore | Lua 原子限流、平台中间件和集成测试 |
| Kafka | Outbox 事件外发 | publisher、重试与 DLQ |
| OPA | 外部策略授权 | adapter、Rego 资产、本地 Compose 和测试 |
| LiteLLM Proxy | 统一模型网关 | `LiteLLMGateway`、Mock OpenAI 和模型工厂测试 |
| OIDC / JWKS | 企业身份认证 | JWKS validator、Bearer authenticator、测试和 Keycloak Compose 资产 |
| OpenTelemetry / Prometheus / Grafana | Trace、指标与运行观测 | OTel Collector 资产、GenAI 属性和可选观测配置 |
| Langfuse | Prompt 版本和评测观测 | Prompt adapter 与自托管接入边界 |

## 3. 本地接入集成环境

`deploy/local/docker-compose.integration.yml` 用于验证项目自己的协议和 adapter 接线：

```bash
docker compose -f deploy/local/docker-compose.integration.yml up -d --build mock-openai opa valkey
python scripts/check_local_stack.py
AGENTFORGE_LOCAL_STACK=1 python -m pytest tests/integration -q
docker compose -f deploy/local/docker-compose.integration.yml down -v
```

Local Compose 命令直接验证：

- Mock OpenAI health；
- OPA health；
- 本地服务 readiness；
- 集成测试能否识别已启动容器。

GitHub Actions 将组件验证拆成独立 Job：

- Local Compose Integration：启动 `mock-openai`、`opa`、`valkey`，执行集成测试；
- Security Integration：启动 OPA/Valkey，执行 OPA adapter、OIDC/JWKS 和分布式限流测试；
- Observability Integration：启动 OTel Collector，执行 GenAI 属性和 Prompt/Trace 测试；
- Kind Envoy Gateway：安装真实 Envoy Gateway controller，验证 Gateway API manifest。

LiteLLM Proxy 服务定义在 Compose 中，但真实 Proxy、模型供应商凭证和压测不属于默认 CI；必须单独启动并验收。

## 4. 真实基础设施测试

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

## 5. 数据与迁移

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

## 6. Temporal

主要 Task Queue：

```text
support-copilot
expense-copilot
asset-copilot
```

当前 Workflow/Activity 包括：

- Support 工单 Workflow 和 SLA Sweep；
- Expense OCR Job、发票门禁扫描和台账写回；
- Demo Asset 参考 Workflow；
- 通用 `TemporalDagWorkflow` 定义和拓扑校验。

Temporal Worker 和 Outbox Worker 使用独立进程，可独立扩缩容。Schedule 初始化由模块 startup hook 完成，并保持幂等。通用 DAG executor 是否启用仍需通过显式配置或 composition root 接线确认。

## 7. 对象存储

集成测试覆盖：

- 小于和大于分片阈值的上传；
- SHA-256 校验；
- 分片上传、完成和中断；
- presigned URL；
- metadata 与 content type；
- 对象存储不可用时的失败语义。

下载 URL 有效期限制为 1-3600 秒，默认 300 秒。

## 8. Valkey、限流与 ContextStore

集成测试覆盖：

- 原子 Token Bucket 限流；
- `retry_after`；
- JSON 缓存与 TTL；
- 分布式锁 `SET NX`；
- compare-and-delete 释放；
- 原子操作和过期行为；
- Redis ContextStore 的命名空间、TTL 和访问日志。

平台限流中间件默认关闭。启用时需要同时确认：

```text
AGENTFORGE_RATE_LIMIT_ENABLED=true
AGENTFORGE_RATE_LIMIT_BACKEND=valkey
AGENTFORGE_RATE_LIMIT_CAPACITY=<capacity>
AGENTFORGE_RATE_LIMIT_REFILL_PER_SECOND=<refill>
```

Redis ContextStore 已提供 `build_context_store` 工厂和测试，但默认平台 Worker 仍使用 Memory；生产接线必须显式完成并验证跨 Worker 读取。

## 9. 外部适配器状态

| 能力 | 已实现 | 仍需显式完成 |
|---|---|---|
| OIDC | JWKS/RS256 validator、authenticator、claim 校验和单测 | composition root 注入、真实 IdP 与 JWKS 轮换 |
| OPA | adapter、Rego、本地 OPA 和策略测试 | 默认 PolicyEngine 替换、双跑、故障 fail-closed 演练 |
| LiteLLM | gateway adapter、模型工厂、Mock OpenAI | 真实 Proxy、供应商凭证和压测 |
| RAG parser | Docling parser adapter、fallback/adapter 边界 | 真实解析服务和 OCR 依赖安装 |
| Prompt | Langfuse adapter | 项目凭证、Prompt 拉取和发布门禁接线 |
| 评测 | Golden Set、promptfoo、评估服务 | 业务样本、阈值和 CI 质量门禁 |

## 10. Outbox、DLQ 与幂等

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

## 11. 边界

- Compose 用于本地开发、演示和集成测试，不是高可用生产方案。
- 仓库不承诺已经完成客户环境的容量压测、灾备、HA 选型和运维验收。
- 私有化 Helm 仅提供交付形态示例，外部中间件由客户环境负责。
- Envoy Gateway controller、企业 IdP、OPA 策略分发、Vault/KMS、WAF/DLP 和供应链扫描需要按目标环境接入。
- 真实模型、OCR、ERP 和财务系统必须通过 Connector 配置、smoke test 和回放样本验证。