# AgentForge

![CI](https://img.shields.io/badge/CI-passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Tests](https://img.shields.io/badge/Tests-884%20passed-brightgreen)
![Version](https://img.shields.io/badge/version-3.1.0-blue)

> **让 AI 从 Demo 走进真实业务，而不是停在 Prompt 和演示里。**

AgentForge 是一个面向企业 AI 业务流的 **共享平台内核 + 可装配业务模块 + 多租户 SaaS/私有化交付** 框架。

它把模型接入、Agent 编排、RAG、权限策略、审批、审计、配额成本、可靠工作流和外部系统连接沉淀为统一底座。业务团队只需实现自己的领域模块，就能把客服、报销等 AI 场景做成可治理、可计量、可运营、可交付的产品。

当前版本：`3.1.0`。已落地 **Support、Expense、Demo Asset** 三个模块，支持 SaaS 和私有化两种交付形态。

### 一分钟了解 AgentForge

| 你关心的问题 | AgentForge 提供什么 |
|---|---|
| AI 能力如何落地到真实业务？ | DAG 编排、Planner、Agent Runtime、工具调用、RAG、模型路由和语义缓存 |
| 企业如何放心使用 AI？ | 多租户、RBAC、声明式策略、人工审批、全程审计、Secret Reference 和 fail-closed 安全默认 |
| 多个业务如何共用一套平台？ | `ModuleManifest` / `ModuleRuntime` / SDK Port / `ModuleRegistry` 的模块化装配 |
| 如何控制成本和资源？ | 租户配额、Token 成本追踪、套餐、用量计量、超额策略、告警和账单 |
| 长流程如何可靠执行？ | Temporal Workflow、Schedule、独立 Task Queue、事务 Outbox、DLQ、重放和幂等处理器 |
| 如何同时服务 SaaS 和私有化客户？ | 租户生命周期、套餐控制面、Helm Chart、existing Secret、Migration Job 和运维手册 |
| 出了问题如何排查？ | Trace、Prometheus 指标、结构化日志、Audit、成本看板和运营总览 |

### 适合谁

| 角色 | 典型目标 |
|---|---|
| **AI 平台 / 架构团队** | 建设企业级 AI 中台，统一模型访问、Agent 运行时、RAG、治理和成本边界，避免每个业务重复造轮子 |
| **企业 SaaS 产品团队** | 把客服、财务、运营等流程产品化，快速增加 AI 能力并保持多租户隔离 |
| **解决方案 / 私有化交付团队** | 用同一套代码完成 SaaS 或客户独立部署，覆盖租户配置、迁移、备份、恢复和回滚 |
| **后端 / Agent 工程师** | 通过 SDK 和模板开发新业务模块，复用 Tool、Memory、Temporal、Outbox、Connector 与观测能力 |
| **运维 / 安全 / 合规团队** | 通过 fail-closed 鉴权、审计脱敏、策略、配额、DLQ、只读容器和生产检查清单控制风险 |

> 如果你只需要一次性 Prompt Demo，AgentForge 可能偏重；如果你需要把 AI 做成可上线、可治理、可复制交付的业务平台，它就是为此设计的。

### 可以用它做什么

- **智能客服**：Webhook/Feishu 接入 → 分类 → 知识检索 → 回复草稿 → 人工审核 → 写回 → SLA 和通知。
- **财务报销**：票据上传/OCR → 字段确认 → 政策校验 → 审批 → 发票门禁 → 台账 → ERP/财务系统写回。
- **企业行业模块**：基于模块 SDK 开发库存、合同、采购、物流等新领域模块，不修改平台 core。
- **多租户 SaaS**：按套餐开通模块，按 OCR、Token、Workflow、存储和通知计量，生成告警与账单。
- **私有化交付**：Helm 部署 API、Worker、Outbox Worker 和 Migration Job，连接客户既有 PostgreSQL、Temporal、对象存储和 Valkey。

---

## 核心能力

| 能力域 | 关键能力 | 对使用者的价值 |
|---|---|---|
| **Agent 运行时与编排** | 统一 Agent、三级 Memory、Tool、ContextStore、DAG、Planner、LoopBlock、超时、降级和请求放大保护 | 快速构建复杂 AI 流程，同时控制并发、失败和成本 |
| **模型与知识网关** | 模型路由、语义缓存、Token 成本、Trace、混合检索、精排和幻觉防护 | 用统一接口接入模型与知识，按任务选择成本/质量平衡 |
| **企业治理** | 多租户、RBAC、声明式策略、审批、Audit、脱敏、保留期和 PII 生命周期 | 把 AI 放进企业权限和责任边界，而不是绕过现有制度 |
| **可靠工作流与集成** | Temporal、Schedule、独立 Task Queue、事务 Outbox、Kafka、Handler Receipt、DLQ、Connector 和 Webhook HMAC | 长流程可恢复，外部副作用可审计、可重试、可补偿 |
| **业务模块平台** | Module Manifest、SDK Port、Entry Point 插件、双仓储、租户模块配置、契约测试和版本策略 | 一个内核承载多个业务，模块可独立开发、测试和交付 |
| **SaaS 与私有化** | 租户生命周期、套餐、计量、告警、账单、运营总览、Helm、Secret 和 Migration | 从第一天就具备商业化交付能力，而不是上线后再补平台能力 |

## 架构一览

```text
┌─────────────────────────────────────────────────────────────────────┐
│ 接入：REST API / Webhook / Feishu / OpenAPI Connector / CLI / SDK   │
├─────────────────────────────────────────────────────────────────────┤
│ 业务模块：Support / Expense / Demo Asset / 自定义模块               │
│ 分层：api · application · domain · infrastructure · workflows        │
├─────────────────────────────────────────────────────────────────────┤
│ 企业平台治理：Tenant · RBAC · Policy · Approval · Audit · Quota     │
│               SaaS 控制面 · 模块配置 · Connector · Secret          │
├──────────────────────────────────┬──────────────────────────────────┤
│ Agent 运行时与编排               │ 模型与知识网关                   │
│ Agent / Memory / Tool / Context  │ Router / Cache / RAG / Cost      │
│ DAG / Planner / LoopBlock        │ Trace / Reranker / Guard         │
├──────────────────────────────────┴──────────────────────────────────┤
│ 可靠交付：Temporal · Outbox / Kafka · DLQ · Schedule · Reconciliation│
├─────────────────────────────────────────────────────────────────────┤
│ 数据与观测：PostgreSQL/pgvector · Object Store · Valkey · OTel      │
└─────────────────────────────────────────────────────────────────────┘
```

### 一条业务请求如何穿过系统

```text
用户 / 外部系统
  -> 鉴权、租户状态、模块开关
  -> 业务模块 API 与领域用例
  -> Agent 编排、RAG、模型网关、工具和 Connector
  -> 高风险动作进入审批与策略检查
  -> Audit、Outbox、Temporal、成本和用量记录
  -> 业务结果返回，异步任务继续可靠执行
```

### 为什么这样设计

- **治理只做一次**：租户、权限、审计、配额、成本和可观测性属于共享内核，不在每个业务里重复实现。
- **业务真正解耦**：平台 core 不导入 Support、Expense 或第三方模块；模块只依赖 SDK Port 和自身 Port。
- **可靠性内建**：业务写入与 Outbox、Temporal、幂等 Handler 和 DLQ 一起设计，而不是上线后补重试。
- **交付形态统一**：同一份平台代码支持 SaaS 控制面和私有化 Helm，不靠两套分叉代码维护。
- **安全默认开启**：生产鉴权 fail-closed，敏感配置使用 `secret_refs`，高风险写回必须经过策略与审批。

## 项目状态

AgentForge `3.1.0` 已达到 **可运行、可测试、可扩展、可私有化交付的商业基线**：

- 平台共享内核、模块 SDK、租户模块配置和三个业务模块已完成；
- SaaS 租户生命周期、套餐、计量、账单和运营控制面已完成；
- Temporal、Outbox、DLQ、对象存储、Valkey 和真实基础设施测试入口已完成；
- 安全基线、审计脱敏、PII 生命周期、Helm 和运维手册已完成；
- 离线测试基线：**884 passed，7 skipped**，其中 platform 测试 **418 项**。

生产上线仍需结合客户环境完成：真实 IdP/SSO、Vault/KMS、WAF/DLP、PostgreSQL/Temporal/MinIO/Valkey 高可用、镜像 CVE/SBOM 扫描，以及 Kubernetes 安装、升级、回滚和灾备演练。

---

## 当前项目结构

```text
AgentForge/
├── agentforge/
│   ├── agents/                       # Agent 实现
│   ├── api/                          # 编排层 FastAPI 入口
│   ├── cli/                          # 编排层 CLI
│   ├── core/                         # Agent、Memory、Tool、Context、Registry
│   ├── gateway/                      # 模型路由、语义缓存、成本、模型注册
│   ├── llm/                          # LLM 适配与网关
│   ├── observability/                # Trace、Metrics、结构化日志
│   ├── orchestration/                # DAG、Planner、LoopBlock、超时、降级
│   ├── prompts/                      # Prompt 模板与资源
│   ├── rag/                          # AST 分块、混合检索、精排、幻觉防护
│   ├── safety/                       # 信任边界、请求整形、AIMD、冲突仲裁
│   ├── sdk/                          # 编排层客户端 SDK
│   ├── storage/                      # Redis 状态、任务和 Trace 存储
│   ├── tools/                        # Tool 实现
│   ├── workflow/                     # 编排工作流运行时
│   └── platform/                     # 企业 AI 平台层
│       ├── api/                      # 平台 REST API
│       ├── application/              # 策略、配额、评估、质量门禁、SaaS 控制面
│       ├── cli/                      # 平台 CLI
│       ├── connectors/               # Connector 基础设施
│       ├── core/                     # ModuleRegistry 与模块契约基础设施
│       ├── domain/                   # 租户、RBAC、审计、事件、用量等模型
│       ├── infrastructure/           # Memory/SQLAlchemy、Outbox、Temporal、S3、Valkey
│       ├── modules/                  # 业务模块（平台核心不直接导入）
│       │   ├── support/              # 客服工单模块
│       │   │   ├── api/              # Support/Feishu Router
│       │   │   ├── application/      # 分类、处理、审核、SLA、通知、写回
│       │   │   ├── connectors/       # Feishu Connector
│       │   │   ├── domain/           # Ticket 与状态机
│       │   │   ├── infrastructure/   # Memory/SQLAlchemy、通知、Feishu 回复
│       │   │   ├── workflows/        # 工单工作流和 SLA 扫描
│       │   │   ├── config.py         # Support 配置 schema
│       │   │   ├── module.py         # ModuleManifest / ModuleRuntime
│       │   │   ├── ports.py          # 模块 Port
│       │   │   ├── runtime.py        # 模块运行时
│       │   │   └── README.md
│       │   ├── expense/              # 报销模块
│       │   │   ├── api/              # 报销、OCR、发票、台账、写回 API
│       │   │   ├── application/      # Claim、OCR、审批、政策、发票门禁、台账
│       │   │   ├── domain/           # Claim、Invoice、Attachment、OCR、Ledger
│       │   │   ├── infrastructure/   # Memory/SQLAlchemy 仓储
│       │   │   ├── workflows/        # OCR、写回和门禁扫描工作流
│       │   │   ├── config.py         # Expense 配置 schema
│       │   │   ├── module.py         # ModuleManifest / ModuleRuntime
│       │   │   ├── ports.py          # 模块 Port
│       │   │   ├── runtime.py        # 模块运行时
│       │   │   └── README.md
│       │   └── demo_asset/           # 第三方模块参考实现
│       │       ├── api/              # Asset API
│       │       ├── application/      # Asset 用例、Audit、Outbox
│       │       ├── domain/           # Asset 领域模型
│       │       ├── infrastructure/   # Memory/SQLAlchemy 仓储
│       │       ├── workflows/        # Asset Temporal Workflow/Activity
│       │       ├── config.py         # Asset 配置 schema
│       │       ├── module.py         # ModuleManifest / ModuleRuntime
│       │       ├── ports.py          # 模块 Port
│       │       └── README.md
│       ├── observability/            # 平台观测扩展
│       ├── sdk/                      # 模块 Port、契约测试和 Connector SDK
│       ├── security/                 # Secret、OIDC、脱敏、PII 生命周期
│       ├── workflows/                # 平台工作流注册
│       └── runtime.py                # ServiceContainer 与 composition root
├── bench/                            # 负载生成与性能测试脚本
├── configs/
│   ├── dev/                          # 开发环境配置
│   ├── prod/                         # 生产环境配置
│   ├── workflows/                    # DAG 工作流配置
│   └── logging.yaml                  # 日志配置
├── tests/
│   ├── unit/                         # 单元测试
│   ├── integration/                  # 集成测试
│   ├── platform/                     # 平台与模块测试
│   └── infra/                        # PostgreSQL/Temporal/MinIO/Valkey 真实基础设施测试
├── docs/
│   ├── architecture.md               # 当前架构
│   ├── commercial/                   # SaaS 控制面
│   ├── infrastructure/               # 生产基础设施集成
│   ├── modules/                      # 模块接入与版本策略
│   ├── release/                      # 3.1.0 发布与迁移
│   └── security/                     # 安全清单与私有化运行手册
├── alembic/                          # PostgreSQL 数据库迁移
│   └── versions/                     # Alembic revision
├── deploy/
│   ├── grafana/                      # Grafana 配置
│   ├── helm/agentforge/              # 私有化 Helm Chart
│   │   ├── templates/                # Kubernetes 资源模板
│   │   ├── Chart.yaml
│   │   └── values.yaml
│   └── platform/                     # 本地、演示和基础设施 Compose
├── templates/module-template/        # 可运行第三方模块模板
├── examples/                         # 编排和装配示例
├── migrations/                       # 早期 SQL 基线；正式迁移使用 alembic/
├── scripts/                          # 发布、备份、恢复、迁移演练、安全扫描
├── requirements/                     # 分拆依赖文件
├── .github/                          # CI、Issue 和 PR 模板
├── CHANGELOG.md
├── CONTRIBUTING.md
├── README.md
├── README.en.md
├── SECURITY.md
├── Makefile
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml                # 早期编排层 Compose，保留兼容
```

---

## 快速开始

### 安装

```bash
python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows
pip install -r requirements-dev.txt
pip install -e .
```

### 启动平台层

```bash
make platform-up
```

平台 API 默认监听 `http://localhost:8000`，健康检查：

```text
GET /health/live
GET /health/ready
```

`/health/live` 表示进程存活，`/health/ready` 表示应用已初始化；两者都不是数据库、Temporal、Valkey 或对象存储的深度健康检查。

只启动本地基础设施：

```bash
make platform-lite-up
```

等价于：

```bash
docker compose -f deploy/platform/docker-compose.lite.yml up -d
```

完整 Compose 包含 PostgreSQL、Valkey、Temporal、MinIO、Kafka、OTel Collector、API、Worker 和 Outbox Worker。详细说明见 [deploy/platform/README.md](deploy/platform/README.md)。

### 鉴权

平台鉴权默认开启（fail-closed）。生产环境未配置 API Key 时会拒绝启动。

```bash
export AGENTFORGE_ADMIN_API_KEY='replace-with-a-strong-secret'
export AGENTFORGE_API_KEYS='{"replace-with-tenant-key":"tenant-a"}'
```

仅本地临时开发可显式关闭鉴权：

```bash
export AGENTFORGE_ALLOW_NO_AUTH=true
```

该开关禁止用于公开环境。

### 模块裁剪

```bash
AGENTFORGE_ENABLED_MODULES=support
AGENTFORGE_ENABLED_MODULES=expense
AGENTFORGE_ENABLED_MODULES=support,expense
```

默认启用 `support,expense`；`asset` 参考模块通过模块插件或测试装配启用。

### 私有化 Helm

```bash
kubectl create namespace agentforge
helm upgrade --install agentforge deploy/helm/agentforge \
  -n agentforge \
  --set image.repository=registry.example.com/agentforge \
  --set image.tag=3.1.0 \
  --set existingSecret=agentforge-secrets
```

生产安装、备份、恢复、升级与回滚见 [私有化部署运行手册](docs/security/PRIVATE_DEPLOYMENT_RUNBOOK.md)。

---

## 平台 API

主要 API 分组：

| 前缀 | 能力 |
|---|---|
| `/v1/support` | Support 工单与兼容业务入口 |
| `/v1/expense` | 报销、OCR、附件、审批、台账、发票门禁 |
| `/v1/assets` | Demo Asset 参考模块（Manifest 前缀） |
| `/v1/console` | 运营控制台聚合与审批收件箱 |
| `/v1/rbac` | 角色、权限和用户角色赋值 |
| `/v1/authorize` | 声明式授权决策 |
| `/v1/policies` | 声明式策略查询与热加载 |
| `/v1/quotas` | 租户配额管理 |
| `/v1/audit` | 审计查询、导出、保留期清理 |
| `/v1/costs` | 成本与模型分布 |
| `/v1/knowledge` | 知识入库与混合检索 |
| `/v1/evaluations` | 检索和分类评估 |
| `/v1/regression` | Golden Dataset 与离线回归 |
| `/v1/release` | Prompt/模型版本发布与质量门禁 |
| `/v1/connectors` | Connector 注册和管理 |
| `/v1/outbox` | Outbox、DLQ、重放与丢弃 |
| `/v1/admin/*` | 租户、套餐、计量、账单和运营总览 |

SaaS API 细节见 [SaaS 控制面](docs/commercial/SAAS_CONTROL_PLANE.md)。

---

## 开发与测试

```bash
make format       # black + isort
make lint         # flake8 + isort + black
make type-check   # mypy
make test         # 全量离线测试
make test-unit
make test-integration
```

平台和模块测试：

```bash
python -m pytest tests/platform -q
```

真实基础设施测试：

```bash
make test-infra
# Windows PowerShell
./scripts/run_infra_tests.ps1
```

`tests/infra` 在没有 `AGENTFORGE_RUN_INFRA_TESTS=1` 时会跳过真实基础设施用例。脚本会自动启动 `docker-compose.lite.yml`，创建测试数据库并执行基础设施测试和 migration drill。

发布验证：

```bash
make release-check
python scripts/security_scan.py
```

详细测试范围和环境变量见 [生产基础设施集成](docs/infrastructure/PRODUCTION_INTEGRATION.md)。

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [架构设计](docs/architecture.md) | 当前分层、模块边界、数据路径和部署形态 |
| [模块接入指南](docs/modules/MODULE_INTEGRATION_GUIDE.md) | 第三方模块实现、契约、租户隔离和验收 |
| [模块版本与弃用](docs/modules/VERSIONING_AND_DEPRECATION.md) | 语义版本、事件兼容和弃用窗口 |
| [Support 模块](agentforge/platform/modules/support/README.md) | 工单、SLA、审核、通知和写回 |
| [Expense 模块](agentforge/platform/modules/expense/README.md) | 报销、OCR、审批、发票门禁和台账 |
| [Demo Asset 模块](agentforge/platform/modules/demo_asset/README.md) | 第三方模块参考实现 |
| [模块模板](templates/module-template/README.md) | 可运行模块模板说明 |
| [SaaS 控制面](docs/commercial/SAAS_CONTROL_PLANE.md) | 租户生命周期、套餐、计量、账单和运营 |
| [基础设施集成](docs/infrastructure/PRODUCTION_INTEGRATION.md) | PostgreSQL、Temporal、MinIO、Valkey、Outbox 与测试 |
| [私有化部署运行手册](docs/security/PRIVATE_DEPLOYMENT_RUNBOOK.md) | Helm 安装、备份、恢复、升级和回滚 |
| [安全清单](docs/security/SECURITY_CHECKLIST.md) | 已实现控制项与现场验收项 |
| [迁移指南](docs/release/MIGRATION_GUIDE_3.1.0.md) | 3.0.0 到 3.1.0 的迁移步骤 |
| [发布说明](docs/release/RELEASE_NOTES_3.1.0.md) | 3.1.0 能力和兼容性 |

---

## 技术栈

- Python 3.10+、FastAPI、Pydantic 2、异步 SQLAlchemy 2
- PostgreSQL 15+、Alembic、pgvector、全文检索
- Temporal 1.32+、Outbox、Kafka
- Valkey/Redis 7+、MinIO/S3
- OpenTelemetry、Prometheus、Grafana
- Docker Compose、Helm
- Feishu、Webhook HMAC、OpenAPI Connector

---

## 安全

- 生产默认 fail-closed，必须配置 `AGENTFORGE_API_KEYS` 或 `AGENTFORGE_ADMIN_API_KEY`。
- Secret 引用支持 `env://`、`vault://`、`kms://`、`secret://`，配置拒绝明文敏感值。
- 审计导出默认递归脱敏 Bearer Token、邮箱、电话和身份证号。
- 附件下载 URL 有效期限制为 1-3600 秒，默认 300 秒。
- 私有化容器默认非 root、只读根文件系统并丢弃 Linux capabilities。
- 漏洞报告流程见 [SECURITY.md](SECURITY.md)。

---

## 已知边界

- OIDC 已提供 Port、Principal 和租户/权限校验，但真实企业 IdP discovery、JWKS 和 group claim 映射需要按客户环境接入。
- Vault/KMS Provider 已提供适配接口，生产密钥托管、轮换和密钥策略仍需现场验收。
- Helm Chart 不内置 PostgreSQL、Temporal、MinIO 或 Valkey，生产使用外部高可用服务。
- 当前 Compose 用于本地开发、演示和集成测试，不是生产高可用方案。
- 更细粒度的部门/项目预算和门禁指标增量物化尚未实现。

---

## License

[MIT License](LICENSE) © 2024 彭黎
