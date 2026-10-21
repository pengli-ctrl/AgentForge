# AgentForge 架构设计

## 1. 系统定位

AgentForge 是面向企业 AI 业务流的共享平台：底层提供 Agent 编排、模型访问和企业治理能力，上层通过可装配业务模块承载客服、报销等具体场景。

系统同时支持两种交付形态：

- **多租户 SaaS**：租户生命周期、套餐、用量计量、账单和运营控制面集中管理。
- **私有化部署**：客户独立部署 API、Worker、Outbox Worker、PostgreSQL、Temporal、对象存储和 Valkey，Helm 引用客户管理的 Secret。

## 2. 分层架构

```text
┌───────────────────────────────────────────────────────────────┐
│ 业务模块：Support / Expense / Demo Asset / 第三方模块          │
├───────────────────────────────────────────────────────────────┤
│ 企业平台层：租户、RBAC、策略、审计、配额、SaaS、知识、Connector │
├───────────────────────────────────────────────────────────────┤
│ 网关层：模型路由、语义缓存、Token 成本、Trace                  │
├───────────────────────────────────────────────────────────────┤
│ 运行时层：Agent、Memory、Tool、Context、Registry               │
├───────────────────────────────────────────────────────────────┤
│ 编排层：DAG、Planner、LoopBlock、超时、降级、请求放大保护       │
└───────────────────────────────────────────────────────────────┘
```

### 2.1 编排层

`agentforge/orchestration` 负责：

- 基于 Kahn 拓扑排序的 DAG 调度与无依赖节点并行执行；
- Planner Agent 动态任务拆解与运行时重编排；
- `LoopBlock` 子图和循环上限；
- 三层超时、四级降级和请求放大保护；
- `ContextStore` 节点间数据流转。

DAG 解决单次 AI 任务的执行图；Temporal 解决跨服务、可恢复、可重试的持久业务工作流，两者不是替代关系。

### 2.2 运行时层

`agentforge/core` 和 `agentforge/agents` 负责：

- 统一 Agent 基类和注册表；
- 工作、短期、长期三级 Memory；
- Function Calling 工具框架；
- Context 隔离和工具执行边界；
- 五类内置 Agent 实现。

### 2.3 网关层

`agentforge/gateway` 和 `agentforge/llm` 负责：

- 按能力、成本、延迟进行模型路由；
- 语义缓存；
- Token 级成本记录和预算告警；
- 租户配额感知的模型调用；
- Trace、指标和结构化日志；
- 通过统一 LLM 接口隔离模型供应商。

### 2.4 企业平台层

`agentforge/platform` 提供共享治理能力：

| 能力 | 主要实现 |
|---|---|
| 租户与模块开关 | `tenant_modules`、`TenantModuleService`、租户账号生命周期 |
| 身份与权限 | API Key、RBAC、声明式策略、OIDC Provider Port |
| 审计与合规 | Audit、递归脱敏、导出、保留期清理、PII 删除编排 |
| 成本与配额 | 租户配额、模型成本、SaaS 用量计量、告警和账单 |
| 知识检索 | PostgreSQL FTS + pgvector，Memory 与 SQLAlchemy 双实现 |
| 可靠工作流 | Temporal Workflow/Activity/Schedule、独立 Task Queue |
| 事件交付 | 事务 Outbox、publisher retry、handler receipt、DLQ replay/discard |
| Connector | Webhook HMAC、OpenAPI 适配、Feishu 和连接器注册表 |
| 安全 | `secret_refs`、`SecretValue`、Vault/KMS/Env Provider |
| 商业控制面 | 套餐、租户状态、计量、账单和运营总览 |

平台核心只依赖 SDK Port。具体业务能力由 composition root 通过 `ModuleRegistry` 装配，平台 core 不导入 Support、Expense 或第三方模块。

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
├── support/
│   ├── api/ application/ connectors/ domain/ infrastructure/ workflows/
│   ├── config.py
│   ├── module.py
│   ├── ports.py
│   ├── runtime.py
│   └── README.md
├── expense/
│   ├── api/ application/ domain/ infrastructure/ workflows/
│   ├── config.py
│   ├── module.py
│   ├── ports.py
│   ├── runtime.py
│   └── README.md
└── demo_asset/
    ├── api/ application/ domain/ infrastructure/ workflows/
    ├── config.py
    ├── module.py
    ├── ports.py
    └── README.md
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
Webhook/Feishu
  -> 签名与幂等校验
  -> 租户模块开关与权限检查
  -> 工单状态机与分类
  -> 知识检索与回复草稿
  -> 人工审核/审批
  -> Policy + RBAC 高风险授权
  -> Connector 写回
  -> Audit + Outbox + 成本/用量记录
```

### 4.2 报销与发票门禁

```text
报销录入/附件/OCR
  -> 字段归一化与人工确认
  -> 费用政策和月度预算校验
  -> 提交审批
  -> 发票登记、重复检查和 Connector 验真
  -> 门禁预检与审批决定
  -> 已批准台账
  -> 写回 Connector
  -> Audit + Outbox + 用量记录
```

Expense 门禁告警可通过 Temporal 周期扫描；告警恢复可自动关闭关联的 Support 财务队列工单。

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
| Valkey/Redis | 限流、JSON 缓存和分布式锁 |
| MinIO/S3 | 附件、发票和对象存储；presigned URL 有有效期 |
| OpenTelemetry | Trace、Metrics 和日志关联 |

Outbox 的核心约束是：业务写入与事件 enqueue 在同一业务边界内完成；发布失败可重试；handler 以 `(event_id, handler_name)` 保证幂等；超过重试上限进入 DLQ。

## 6. 部署形态

### 本地与集成测试

- `deploy/platform/docker-compose.lite.yml`：PostgreSQL、Valkey、Temporal、Temporal UI、MinIO。
- `deploy/platform/docker-compose.platform.yml`：lite 依赖加 Kafka、OTel、Migration、API、Temporal Worker、Outbox Worker。
- `docker-compose.yml`：早期编排层单 Agent 服务，保留兼容，不是当前平台主形态。

### 私有化

`deploy/helm/agentforge` 部署：

- API Deployment；
- Temporal Worker Deployment；
- Outbox Worker Deployment；
- pre-install/pre-upgrade Migration Job；
- Service、Ingress、ServiceAccount、ConfigMap。

Chart 默认使用外部 PostgreSQL、Temporal、MinIO 和 Valkey，不在 Chart 内托管有状态服务。容器默认非 root、只读根文件系统、禁止权限提升并丢弃全部 Linux capabilities。

## 7. 当前代码地图

| 路径 | 职责 |
|---|---|
| `agentforge/core` | Agent、Memory、Tool、Context、Registry |
| `agentforge/orchestration` | DAG、Planner、LoopBlock、可靠性控制 |
| `agentforge/gateway` | 路由、缓存、成本、模型注册表 |
| `agentforge/llm` | LLM 访问适配 |
| `agentforge/rag` | 分块、混合检索、精排、幻觉防护 |
| `agentforge/safety` | 信任边界、脉冲整形、AIMD、冲突仲裁 |
| `agentforge/storage` | Redis 状态、任务和 Trace 存储 |
| `agentforge/workflow` | 编排工作流运行时 |
| `agentforge/platform` | 企业平台共享内核 |
| `agentforge/platform/modules` | Support、Expense、Demo Asset |
| `bench` | 多进程负载生成和平台性能测试脚本 |
| `examples` | 编排、事件总线和端到端装配示例 |
| `templates/module-template` | 可运行第三方模块模板 |
| `tests/unit` | 单元测试 |
| `tests/integration` | 编排层和服务集成测试 |
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

## 9. 已知边界

- OIDC 真实 IdP 适配需要客户现场集成。
- Vault/KMS 的密钥策略、轮换和灾备需要现场验收。
- Compose 不是高可用生产部署。
- Helm Chart 不托管有状态中间件。
- 部门/项目级预算和门禁指标增量物化尚未实现。
