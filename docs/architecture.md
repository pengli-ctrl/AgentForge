# AgentForge 架构设计

## 1. 系统定位

AgentForge 是面向企业 AI 业务流的共享平台：底层提供 Agent 编排、模型访问、RAG、可靠工作流和企业治理能力，上层通过可装配业务模块承载客服、报销等具体场景。

系统同时支持两种交付形态：

- **多租户 SaaS**：租户生命周期、套餐、用量计量、账单和运营控制面集中管理。
- **私有化部署**：客户独立部署 API、Worker、Outbox Worker、PostgreSQL、Temporal、对象存储和 Valkey，Helm 引用客户管理的 Secret。

当前完整业务线是 **Support 智能客服** 和 **Expense 智能报销**。`Demo Asset` 是第三方模块契约的参考实现，用于验证模块装配，不作为第三条完整业务线。

## 2. 分层架构

```text
┌──────────────────────────────────────────────────────────────────────┐
│ 接入层：客户端 / 飞书 / Webhook / SDK                                 │
│ Envoy Gateway / Gateway API（TLS、路由、入口限流、SSE 超时）          │
├──────────────────────────────────────────────────────────────────────┤
│ API/BFF：FastAPI / Pydantic / OpenAPI                                 │
│ 鉴权、租户上下文、请求校验、模块路由、限流中间件                     │
├──────────────────────────────────────────────────────────────────────┤
│ 业务模块：Support / Expense / Demo Asset 参考模块 / 第三方模块        │
│ 领域状态机、业务规则、模块用例、Connector、模块 Workflow              │
├──────────────────────────────────────────────────────────────────────┤
│ 企业平台：ModuleRegistry、RBAC、Policy/OPA、审批、Audit、Quota、Usage │
├──────────────────────────────────────────────────────────────────────┤
│ AI 执行：Planner / DAG / Agent Runtime / Memory / ContextStore / Tool  │
│ AI Gateway / Semantic Cache / Cost / RAG / Citation                    │
├──────────────────────────────────────────────────────────────────────┤
│ 可靠执行：Temporal / Outbox / Kafka / DLQ / Connector / 对账补偿      │
├──────────────────────────────────────────────────────────────────────┤
│ 数据与观测：PostgreSQL+pgvector / Valkey / MinIO / OTel / Langfuse     │
└──────────────────────────────────────────────────────────────────────┘
```

### 2.1 接入与 API 层

- Envoy Gateway / Gateway API 负责南北向入口、HTTPRoute、TLS、入口限流和 SSE 超时边界。
- Helm 保留 Ingress 兼容模板，默认不启用；目标环境按实际控制器能力选择 Gateway API 或 Ingress。
- FastAPI 负责协议适配、鉴权中间件、租户上下文、模块路由和 OpenAPI。
- 平台请求限流中间件支持 Memory / Valkey 后端，通过 `AGENTFORGE_RATE_LIMIT_*` 配置启用。

### 2.2 编排层

`agentforge/orchestration` 负责：

- 基于 Kahn 拓扑排序的 DAG 校验与执行；
- Planner 全局任务拆解与运行时有限重编排；
- `LoopBlock` 子图和循环上限；
- 三层超时、四级降级和请求放大保护；
- `ContextStore` 节点间数据流转；
- 通用 `TemporalDagWorkflow` 定义，用于后续把扁平 DAG 交给 Temporal 持久执行。

DAG 解决单次 AI 任务的执行图；Temporal 解决跨服务、可恢复、可重试的持久业务工作流，两者不是替代关系。

### 2.3 运行时与 AI Gateway

`agentforge/core` 和 `agentforge/agents` 负责：

- 统一 Agent 基类和注册表；
- 工作、短期、长期三级 Memory；
- Function Calling 工具框架；
- Context 隔离和工具执行边界；
- 五类内置 Agent 实现。

`agentforge/gateway`、`agentforge/llm` 和 `platform/infrastructure/llm` 负责：

- 按能力、成本、延迟进行模型路由；
- 语义缓存；
- Token 级成本记录和预算告警；
- 租户配额感知的模型调用；
- 静态模型网关与 LiteLLM Proxy adapter；
- Trace、指标和结构化日志；
- 通过统一 LLM 接口隔离模型供应商。

### 2.4 企业平台层

`agentforge/platform` 提供共享治理能力：

| 能力 | 主要实现 |
|---|---|
| 租户与模块开关 | `tenant_modules`、`TenantModuleService`、租户账号生命周期 |
| 身份认证 | API Key；OIDC/JWKS 校验器和认证器；Keycloak 本地 Compose 资产 |
| 授权策略 | RBAC、声明式 PolicyEngine、OpenFGA 适配边界、OPA adapter 与 Rego 资产 |
| 审计与合规 | Audit、递归脱敏、导出、保留期清理、PII 删除编排 |
| 成本与配额 | 租户配额、模型成本、SaaS 用量计量、告警和账单 |
| 知识检索 | PostgreSQL FTS + pgvector，Memory 与 SQLAlchemy 双实现 |
| 可靠工作流 | Temporal Workflow/Activity/Schedule、独立 Task Queue |
| 事件交付 | 事务 Outbox、publisher retry、handler receipt、DLQ replay/discard |
| Connector | Webhook HMAC、OpenAPI 适配、Feishu 和连接器注册表 |
| 安全 | `secret_refs`、`SecretValue`、Vault/KMS/Env Provider |
| 商业控制面 | 套餐、租户状态、计量、账单和运营总览 |

平台核心只依赖 SDK Port。具体业务能力由 composition root 通过 `ModuleRegistry` 装配，平台 core 不导入 Support、Expense 或第三方模块。

### 2.5 集成组件与接线状态

| 组件 | 仓库内实现 | 当前默认接线与边界 |
|---|---|---|
| Envoy Gateway / Gateway API | `Gateway`、`HTTPRoute`、`RateLimitPolicy` Helm 模板；kind 集成测试 | 默认关闭，需目标集群安装 controller、CRD 后显式开启 |
| FastAPI | 平台 API、模块 Router、认证与限流中间件 | 默认平台 API 入口 |
| LiteLLM | `LiteLLMGateway` 和 `build_inner_model_gateway` | SQLAlchemy 容器可按配置构建；外部 Proxy 和真实凭证由环境提供 |
| OIDC / JWKS | `JWKSTokenValidator`、`OIDCAuthenticator`、claim 校验和测试 | 校验能力已实现；`oidc` 模式需要 composition root 显式注入 validator，默认仍为 API Key |
| OPA | `OPAPolicyAdapter`、`policies/agentforge.rego`、本地 Compose | adapter 与资产已实现；默认运行时仍使用本地 `PolicyEngine`，切换需显式装配 |
| OpenFGA | 关系权限客户端适配边界 | 非默认授权引擎 |
| Valkey 限流 | Token Bucket Lua 原子计数、平台中间件、Memory/Valkey 后端 | 默认关闭，启用后由 `AGENTFORGE_RATE_LIMIT_BACKEND` 选择后端 |
| Redis ContextStore | 租户/会话/DAG 命名空间、TTL、访问日志和工厂 | 已实现和测试；默认仍为 Memory，Worker/DAG 需显式使用工厂接线 |
| Temporal DAG | `TemporalDagWorkflow`、Activity 和拓扑校验 | Workflow 定义已实现；默认 DAG executor 仍需通过配置或装配显式选择 |
| RAG 解析 | Docling 可注入 adapter；PaddleOCR/Unstructured/Tika adapter 边界 | 仓库不托管真实解析服务，需注入外部解析能力 |
| Prompt / Trace | Langfuse Prompt adapter、OTel GenAI 属性、OTel Collector 资产 | adapter 和约定已落地；Langfuse 项目与 Prompt 读取需显式接线 |
| 评测 | Golden Set、promptfoo 配置、评估与回归服务 | 仓库资产已落地；业务样本和真实门禁阈值需补充 |

## 3. 业务模块架构

每个模块遵守以下目录边界：

```text
agentforge/platform/modules/<module>/
├── api/                  # FastAPI Router，只调用本模块 application service
├── application/          # 用例、业务规则、审计/Outbox 编排
├── domain/               # 领域模型、状态机、值对象
├── infrastructure/       # Memory/SQLAlchemy/S3/Connector 等实现
├── workflows/            # Temporal Workflow 与 Activity
├── config.py             # Pydantic 配置 schema
├── module.py             # ModuleManifest 与 ModuleRuntime 装配
└── ports.py              # 本模块持久化与外部能力 Port
```

当前实际装配的模块：

```text
agentforge/platform/modules/
├── support/              # 完整业务线：工单、分类、RAG、审核、SLA、写回
├── expense/              # 完整业务线：OCR、预算、审批、发票门禁、台账、对账
└── demo_asset/           # 第三方模块参考实现，不是第三条完整业务线
```

模块契约：

- `api_prefix` 与模块名一致；
- 权限使用 `{module}.{resource}.{action}`；
- 事件使用 `{module}.{resource}.{event}.vN`；
- Temporal Task Queue 以模块名开头；
- migration namespace 等于模块名；
- API、仓储、缓存键和事件处理显式携带 `tenant_id`；
- 事件消费必须幂等；
- 配置中的敏感项只能引用 Secret，不存明文。

模块可通过 `agentforge.modules` entry point 自动发现，也可在测试或嵌入式场景通过 `extra_modules` 显式装配。契约检查入口为 `run_module_contract_suite`。

## 4. 关键数据路径

### 4.1 客服处理

```text
Envoy Gateway / Ingress
  -> FastAPI /v1/support/events/im 或 /v1/support/workflows/support
  -> 鉴权、租户、模块开关和限流
  -> message_id 幂等与工单状态机
  -> 分类器输出 intent / priority / team / risk
  -> KnowledgePort 检索当前租户 Top-K
  -> ReplyDraftService 生成草稿并校验 citation
  -> 人工审核 / 高风险审批
  -> Policy + RBAC 授权
  -> Feishu Connector 幂等发布
  -> Audit + Outbox + 成本/用量 + Trace
  -> SLA Sweep 提醒、升级和通知
```

### 4.2 报销、发票门禁与写回

```text
上传附件 / 分片上传
  -> MinIO / S3 + 短时下载 URL
  -> OCR Job / Extraction
  -> 字段归一化 + 人工确认
  -> Expense Claim 草稿与政策/月度预算校验
  -> 提交审批并评估发票 readiness
  -> 发票登记、租户指纹去重、Connector 验真
  -> off / duplicate_only / verified / strict 门禁
  -> RBAC + Policy + 审批决定
  -> 已批准台账
  -> 幂等写回、验真、对账和补偿
  -> Audit + Outbox + 用量 + Trace
```

Expense 门禁告警通过 Temporal 周期扫描；告警恢复可自动关闭关联的 Support 财务队列工单，形成跨模块业务闭环。

### 4.3 用量计量

```text
OCR 页数 / 模型 Token / Workflow 启动 /
对象存储字节 / 通知次数
  -> UsageMeteringAdapter（best-effort）
  -> UsageMeteringService
  -> Plan limit / overage policy
  -> Audit + Outbox
  -> 告警、账单和运营总览
```

用量采集失败不会中断主业务路径；超过硬门禁时由租户状态和配额检查在 API 边界执行 fail-closed。

## 5. 数据与可靠性

| 组件 | 用途 |
|---|---|
| PostgreSQL | 平台及模块主数据、租户配置、审计、用量、Outbox、pgvector |
| Alembic | 数据库升级与回滚 |
| Temporal | 持久工作流、重试、Schedule 和模块 Task Queue |
| Outbox | 业务事务与事件发布解耦，支持 handler receipt、retry、DLQ |
| Kafka | Outbox 事件外发 |
| Valkey/Redis | 分布式令牌桶限流、JSON 缓存、分布式锁和可选 ContextStore |
| MinIO/S3 | 附件、发票和对象存储；presigned URL 有有效期 |
| OpenTelemetry | Trace、Metrics 和日志关联 |
| Langfuse | Prompt 版本读取和评测观测的适配边界 |

Outbox 的核心约束是：业务写入与事件 enqueue 在同一业务边界内完成；发布失败可重试；handler 以 `(event_id, handler_name)` 保证幂等；超过重试上限进入 DLQ。

## 6. 部署形态

### 本地与集成测试

- `deploy/platform/docker-compose.lite.yml`：PostgreSQL、Valkey、Temporal、Temporal UI、MinIO。
- `deploy/platform/docker-compose.platform.yml`：lite 依赖加 Kafka、OTel、Migration、API、Temporal Worker、Outbox Worker。
- `deploy/local/docker-compose.integration.yml`：Mock OpenAI、LiteLLM、OPA、Valkey、Temporal、MinIO。
- `deploy/local/keycloak-compose.yml`：OIDC/JWKS 本地联调资产。
- `deploy/local/observability/docker-compose.yml`：OTel Collector 联调资产。
- `docker-compose.yml`：早期编排层单 Agent 服务，保留兼容，不是当前平台主形态。

### 私有化

`deploy/helm/agentforge` 部署：

- API Deployment；
- Temporal Worker Deployment；
- Outbox Worker Deployment；
- pre-install/pre-upgrade Migration Job；
- Service、Gateway、HTTPRoute、RateLimitPolicy、Ingress 兼容模板、ServiceAccount、ConfigMap。

Chart 默认使用外部 PostgreSQL、Temporal、MinIO、Valkey 和 Kafka，不在 Chart 内托管有状态服务。容器默认非 root、只读根文件系统、禁止权限提升并丢弃全部 Linux capabilities。

## 7. 当前代码地图

| 路径 | 职责 |
|---|---|
| `agentforge/core` | Agent、Memory、Tool、Context、Registry |
| `agentforge/orchestration` | DAG、Planner、LoopBlock、可靠性控制、Temporal DAG |
| `agentforge/gateway` | 路由、缓存、成本、模型注册表 |
| `agentforge/llm` | LLM 访问适配 |
| `agentforge/rag` | 分块、混合检索、精排、幻觉防护、解析 adapter |
| `agentforge/safety` | 信任边界、脉冲整形、AIMD、冲突仲裁 |
| `agentforge/storage` | Redis 状态、任务和 Trace 存储 |
| `agentforge/workflow` | 编排工作流运行时 |
| `agentforge/platform` | 企业平台共享内核 |
| `agentforge/platform/modules` | Support、Expense、Demo Asset |
| `deploy/helm/agentforge` | 私有化 Chart 与 Gateway API 资源 |
| `deploy/local` | Compose、kind、Keycloak、LiteLLM、Mock OpenAI、OTel |
| `policies` | OPA Rego 策略资产 |
| `evals` | Golden Set 和 promptfoo 配置 |
| `bench` | 多进程负载生成和平台性能测试脚本 |
| `examples` | 编排、事件总线和端到端装配示例 |
| `templates/module-template` | 可运行第三方模块模板 |
| `tests/unit` | 单元测试 |
| `tests/integration` | 编排层、服务和本地容器集成测试 |
| `tests/platform` | 平台、模块和商业能力测试 |
| `tests/infra` | 真实基础设施测试 |

## 8. 架构约束

1. 平台核心不得导入具体业务模块。
2. 业务模块 Application 层只依赖本模块 Port 和 `agentforge.platform.sdk`。
3. 所有租户数据访问必须显式带 `tenant_id`。
4. 高风险写操作必须经过 Policy/RBAC 和人工审批边界。
5. 外部副作用必须可审计、幂等、可重试。
6. Secret 只能通过 Secret Reference 注入，不进入日志、Audit 或数据库明文。
7. 新增模块必须通过契约套件、迁移测试、租户隔离探针和全量测试。
8. 集成测试必须接入 GitHub Actions 的真实容器 Job，不能只保留本地脚本。

## 9. 已知边界

- OIDC/JWKS 校验器已实现，但企业 IdP discovery、真实 claim 映射和自动 composition 接线需按客户环境完成。
- OPA adapter 和 Rego 资产已实现，默认运行路径仍使用本地 PolicyEngine；切换到 OPA 需要显式装配和故障策略验证。
- Redis ContextStore、Langfuse Prompt、RAG Docling adapter 和 Temporal DAG 已有实现/测试，但默认 Worker 装配仍需按演进计划逐项接线。
- Vault/KMS 的密钥策略、轮换和灾备需要现场验收。
- Compose 不是高可用生产部署。
- Helm Chart 不托管有状态中间件。
- 部门/项目级预算和门禁指标增量物化尚未实现。
- 真实模型供应商、OCR 服务、ERP、WAF、容量、灾备和客户验收必须在目标环境完成。