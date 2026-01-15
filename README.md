# AgentForge

![CI](https://img.shields.io/badge/CI-passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Tests](https://img.shields.io/badge/Tests-728%20passed-brightgreen)
![Code Style](https://img.shields.io/badge/code%20style-black-000000)

> 面向中小企业的 **AI Agent 编排 + 企业治理平台**——从多 Agent 编排、智能路由、成本管控，到多租户客服工单全流程（检索→生成→审批→写回）的一站式 AI 平台基础设施。

> 📖 **想快速了解项目全貌？** 一页纲领性总览（做到什么程度 / 解决什么问题 / 核心亮点）见 [docs/PROJECT_OVERVIEW.md](docs/PROJECT_OVERVIEW.md)。

AgentForge 是一个 AI Agent 编排 + 企业治理一体化平台。上层是**多 Agent 编排引擎**：三层架构（编排层 / 运行时层 / 网关层），内置 DAG 任务引擎（最大 50 节点）、5 模型智能路由、语义缓存、三级 Memory、全链路 Trace。下层是**企业 AI 平台层**（首个落地场景：客服与售后工单智能处理）：多租户、RBAC + 声明式策略引擎、租户配额与成本治理、全过程审计、Temporal 工作流 + Outbox 可靠投递、检索评估与离线回归、连接器与工单写回。开源项目，**728 个自动化测试全部通过**（其中 platform 层 262 项），black/isort/flake8/mypy 全绿。

---

## 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                      编 排 层 (Orchestration)                    │
│  DAG任务引擎(50节点) · Planner Agent · LoopBlock · ContextStore  │
│  静态编排(Kahn拓扑排序) · 动态编排 · 运行时重编排                  │
├─────────────────────────────────────────────────────────────────┤
│                      运 行 时 层 (Runtime)                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐           │
│  │CodeReview│  │  Test    │  │   Doc    │  │ Security │  ...×5  │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │         │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│  统一Agent基类(abc+5接口) · 三级Memory · Tool框架(Function Calling) │
├─────────────────────────────────────────────────────────────────┤
│                      网 关 层 (AI Gateway)                       │
│  5模型智能路由 · 语义缓存(命中率38%) · Token成本管控 · 全链路Trace  │
│  Qwen3-Pro · GLM-5 · Kimi · MiniMax · DeepSeek-V3              │
├─────────────────────────────────────────────────────────────────┤
│                      企 业 AI 平 台 层 (Platform)                │
│  多租户 · RBAC+策略引擎 · 配额成本 · 全过程审计                   │
│  客服工单全流程 · Temporal工作流 · Outbox/DLQ · 检索评估 · 连接器  │
└─────────────────────────────────────────────────────────────────┘
```

| 层级 | 职责 | 核心组件 |
|---|---|---|
| **编排层** | 任务拆解、节点调度、数据流转 | DAG任务引擎(Kahn拓扑排序+并行调度), Planner Agent(自动拆解), LoopBlock(循环控制器), ContextStore(节点间数据流转) |
| **运行时层** | Agent执行、Memory管理、工具调用 | 统一Agent基类(abc+5标准接口), 5类Agent注册, 三级Memory(工作/短期/长期), Tool框架(Function Calling) |
| **网关层** | 模型路由、缓存、成本管控、可观测 | 5模型智能路由(能力/成本/延迟三维评分), 语义缓存(Embedding>0.92), Token级成本统计+P0-P3预算告警, 全链路Trace/Span(五种Span类型) |
| **平台层** | 企业治理 + 业务场景成环 | 多租户隔离, RBAC+声明式策略引擎, 租户配额与成本看板, 全过程审计, 客服工单全流程(检索→生成→审批→写回), Temporal工作流, Outbox/DLQ, 检索评估与离线回归, 连接器与Webhook |

---

## 核心设计

### DAG任务引擎

- 支持最大**50节点**的有向无环图
- **Kahn算法**拓扑排序 O(V+E)，无依赖节点并行执行
- **三种编排模式**：静态编排（开发者手动定义DAG）、动态编排（Planner Agent自动生成）、运行时重编排（执行中动态插入/替换节点）
- **ContextStore** 节点间数据流转，读写锁保护并行节点
- **LoopBlock**：DAG内嵌子图+循环控制器，最大5次硬约束，退出条件可配置

### 5模型智能路由

- 五个模型：**Qwen3-Pro、GLM-5、Kimi、MiniMax、DeepSeek-V3**
- Classifier Agent 评估任务类型和复杂度
- **三维评分矩阵**：能力(0.5)、成本(0.3)、延迟(0.2) 加权求和
- 简单任务→MiniMax（成本 1/10），复杂任务→Qwen3-Pro

### 语义缓存

- Embedding相似度 **>0.92** 阈值（实验调优的帕累托最优点）
- 命中率 **38%**，准确率 **98%+**
- LRU + TTL 24小时淘汰策略

### 三层超时体系

| 层级 | 超时 | 说明 |
|---|---|---|
| LLM调用 | 10s | 基于15000+请求P95分布调优 |
| Agent执行 | 30s | `asyncio.wait_for` |
| DAG全局 | 300s | `cancel` + `partial_success` |

### 四级降级策略

| 级别 | 策略 |
|---|---|
| **L1 模型级** | 主模型→备选模型→最轻量模型→预设回复 |
| **L2 节点级** | 重试2次→fallback默认值→degraded标记 |
| **L3 DAG级** | 失败节点>30%提前终止 |
| **L4 系统级** | 全局降级+P0告警 |

### 请求放大管控

三层限制防止级联失控：
- DAG规模 ≤ 50 节点
- 单请求LLM调用 ≤ 100 次
- 并发DAG ≤ 10 × 并行节点 ≤ 5

### 三级Memory

| 类型 | 类比 | 说明 |
|---|---|---|
| **工作记忆** | CPU寄存器 | 当前对话上下文 |
| **短期记忆** | 内存 | Session级缓存 |
| **长期记忆** | 硬盘 | 持久化知识库，基于RAG |

### 全链路可观测

- **五种Span类型**：`CacheSpan`、`RouteSpan`、`InferenceSpan`、`AgentSpan`、`LoopSpan`
- Token级成本统计 + **P0-P3** 四级预算告警
- 每个请求→Agent→模型→Token 全链路追踪

---

## AI 平台层（首个场景：客服智能工单处理）

面向中小企业客服/售后场景的企业 AI 平台，用**治理边界**把 AI 的自动化能力约束在企业可控范围内：AI 可以分类、检索、总结、起草，**但所有面向客户和高度风险的动作必须在人工审核批准后才能执行**。

### 治理与安全边界

- **多租户隔离**：所有领域模型（工单、知识、RBAC、配额、审计、连接器）均按租户隔离
- **RBAC + 声明式策略引擎**：角色/权限 + `ActionPolicy`（fail-closed、风险级、审批要求、allow-list）组合求值，给出 allowed / denied / requires_approval 决策；可选接 OpenFGA 式关系检查
- **高风险动作审计闭环**：`HighRiskActionAuthorizer` 对"写回工单系统"等高危动作强制人工审批边界（工单未到 READY_TO_PUBLISH / 未获批 → DENIED），并把每次授权（放行/拒绝）写入审计事件，回答"谁执行、为何允许"
- **租户级配额治理**：月度预算 / 告警阈值 / 硬上限，`QuotaAwareModelGateway` 逐租户强制
- **全过程审计**：审计事件、操作者、`trace_id`、成本汇总，支撑合规追踪

### 工单全流程闭环

```
飞书/Webhook → 签名校验+幂等 → 工单创建/状态机 → 意图+风险分类
  → 知识检索(pgvector+FTS混合) → 回复草稿生成+引用校验
  → 风险评估 → 低风险进人工审核 / 高风险进审批 → 审批通过 → 写回业务系统
  → 反馈沉淀为评估样本 → 成本/审计/Trace 全程记录
```

- **工单生命周期**：创建、幂等键、状态机、风险分类、优先级
- **Temporal 工作流**：审批 Signal、Outbox、失败重试、DLQ 重放
- **人工审核**：接受 / 编辑 / 驳回 / 升级，审核后回复发布
- **连接器与写回**：`Connector` ABC + Registry、Webhook 泛化（HMAC 验签）、`OpenAPIAdapter`（幂等键头+有界重试+令牌桶限流+审计）、CRM/工单系统写回闭环

### 检索、评估与版本治理

- **混合检索**：PostgreSQL FTS + pgvector（HNSW/GIN 索引），`KnowledgeRepository.search`，Memory 与 SQLAlchemy 双实现
- **检索重排与召回评估**：确定性 `HybridReranker`、Recall@K / Precision@K / MRR / 引用正确率、在线 `RetrievalEvaluationService`（GoldenQuery→QueryEvaluation→RetrievalReport）
- **结构化分类质量门禁**：分类准确率 / 优先级准确率 / 结构化合法率 / 高风险漏报率；版本化 `PromptRegistry` 与 `ModelVersionRegistry`；发布质量门禁（PASS / HOLD / BLOCK，高风险漏报一票否决）
- **离线回归 + Golden Dataset**：`RegressionRunner`（加载 Golden → 召回+分类评估 → 质量门禁 → 报告持久化）

### 平台 API 一览

| 路由前缀 | 能力 |
|---|---|
| `/v1/tickets` | 工单详情、审核（approve/reject）、质检（review）、回复、写回 |
| `/v1/console` | 客服工作台、审批收件箱、管理控制台聚合概览、多租户成本 |
| `/v1/rbac` | 角色 CRUD、权限设置、用户-角色赋值、`/v1/authorize` 授权检查 |
| `/v1/policies` | 策略热加载控制面：列出 + `source_revision`、`GET /v1/policies/revision`、`POST /v1/policies/reload`（原子换载，坏配置 422 保留旧策略） |
| `/v1/quotas` | 租户配额管理 |
| `/v1/audit` | 审计事件查询 |
| `/v1/costs` | 成本与模型分布 |
| `/v1/knowledge` | 知识入库与混合检索（支持重排） |
| `/v1/evaluations` | 检索/分类质量评估 |
| `/v1/regression` | Golden 维护 + 回归触发与记录 |
| `/v1/connectors` | 连接器注册与管理 |
| `/v1/outbox` | Outbox 事件管理、DLQ 查询与重放 |

---

## 量化成果

| 指标 | 数值 | 说明 |
|---|---|---|
| LLM调用成本降低 | **68%** | 缓存38%直接省 + 路由优化30% |
| 端到端延迟降低 | **38%** | 缓存跳过推理 + 路由优先低延迟模型 |
| 任务完成率 | **97%** | 15000+请求统计 |
| 级联失败率 | **<0.3%** | 结构化输出+交叉验证+兜底默认值 |
| 缓存命中率 | **38%** | Embedding相似度>0.92 |
| 自动化测试 | **728个** | 全部通过，CI绿灯（单元+集成+平台三层） |
| Agent类型 | **5类** | 代码审查/测试执行/文档生成/安全扫描/部署 |
| DAG最大规模 | **50节点** | Kahn拓扑排序+并行调度 |
| platform测试 | **262个** | 企业 AI 平台层专项测试 |

> 以上数据来自基准测试（2000条标注query）和日常使用（持续3周，累计15000+请求），非商用生产环境。

---

## 技术栈

| 类别 | 技术选型 |
|---|---|
| 语言 | Python 3.10+ |
| 后端框架 | FastAPI + 异步 SQLAlchemy |
| LLM推理 | vLLM(私有化部署) + 5 API模型(Qwen3-Pro / GLM-5 / Kimi / MiniMax / DeepSeek-V3) |
| 任务编排 | DAG引擎(Kahn拓扑排序+并行调度) + Planner Agent |
| 工作流 | Temporal Python SDK |
| 事件投递 | Outbox 模式 + Redis Pub/Sub → Kafka（带 DLQ 重放） |
| 状态存储 | Redis / Valkey |
| 数据库 | PostgreSQL（FTS + pgvector 混合检索）+ Alembic 迁移 |
| 向量检索 | FAISS / pgvector |
| 关键词检索 | BM25 (rank_bm25) / PostgreSQL FTS |
| 代码解析 | tree-sitter |
| 容器化 | Docker / Docker Compose |
| 可观测性 | OpenTelemetry + Prometheus + Grafana |
| 工具协议 | Function Calling |
| 连接器 | Feishu、Webhook（HMAC 验签）、OpenAPI（幂等+限流+审计） |

---

## 项目结构

```
AgentForge/
├── agentforge/
│   ├── core/                     # 运行时层
│   │   ├── agent.py              # 统一Agent基类(abc+5标准接口)
│   │   ├── memory.py             # 三级Memory(工作/短期/长期)
│   │   ├── base_tool.py          # Tool框架(Function Calling)
│   │   ├── agent_registry.py     # Agent注册表
│   │   └── context_store.py      # 节点间数据流转
│   ├── orchestration/            # 编排层
│   │   ├── dag_engine.py         # DAG任务引擎(Kahn拓扑排序+并行调度)
│   │   ├── planner.py            # Planner Agent(自动任务拆解)
│   │   ├── loop_block.py         # LoopBlock循环控制器
│   │   ├── timeout.py            # 三层超时体系
│   │   ├── degradation.py        # 四级降级策略
│   │   └── request_guard.py      # 请求放大管控
│   ├── gateway/                  # 网关层
│   │   ├── router.py             # 5模型智能路由
│   │   ├── semantic_cache.py     # 语义缓存(Embedding>0.92)
│   │   ├── cost_tracker.py       # Token级成本统计+预算告警
│   │   └── model_registry.py     # 模型注册表
│   ├── observability/            # 可观测性
│   │   ├── tracing.py            # Trace/Span(五种类型)
│   │   ├── metrics.py            # Prometheus指标
│   │   └── logger.py             # 结构化日志
│   ├── rag/                      # RAG工程化
│   │   ├── ast_chunker.py        # AST感知分块
│   │   ├── hybrid_retriever.py   # BM25+FAISS混合检索
│   │   ├── reranker.py           # LLM精排
│   │   └── hallucination_guard.py # 幻觉防护
│   ├── safety/                   # 安全防护
│   │   ├── trust_boundary.py     # 确定性校验
│   │   ├── pulse_shaper.py       # 请求整形
│   │   ├── aimd_controller.py    # AIMD 限速
│   │   └── conflict_arbiter.py   # 冲突仲裁
│   ├── tools/                    # 工具实现
│   ├── agents/                   # Agent实现(5类)
│   ├── api/                      # 编排层 FastAPI 入口
│   └── platform/                 # 企业 AI 平台层
│       ├── api/                  # 平台 REST API(工单/控制台/RBAC/配额/审计/...)
│       ├── application/          # 应用服务(策略引擎/配额/评估/质量门禁/连接器...)
│       ├── domain/               # 领域模型(工单/RBAC/配额/审计/策略/事件...)
│       ├── infrastructure/       # 基础设施(Memory/SQLAlchemy双实现, Outbox, Kafka, Temporal)
│       ├── workflows/            # Temporal 工作流(客服工单)
│       ├── connectors/           # 连接器(Feishu)
│       └── runtime.py            # 装配(ServiceContainer)
├── configs/
│   ├── workflows/                # DAG工作流配置
│   ├── dev/ · prod/              # 运行环境配置
│   └── logging.yaml              # 日志配置
├── tests/                        # 728个测试(单元+集成+平台)
├── docs/                         # 架构/ADR/总览 文档
├── alembic/                      # 数据库迁移
├── deploy/                       # 部署配置
└── ...
```

---

## 快速开始

### 编排层 Quick Start

```python
from agentforge.gateway import SmartRouter
from agentforge.orchestration import DAGEngine, DAGNode

# 初始化 AI Gateway（5模型智能路由 + 语义缓存 + 成本管控）
router = SmartRouter()

# 路由决策：按任务类型与复杂度选择模型（simple→MiniMax，complex→Qwen3-Pro）
decision = await router.route(
    task_type="code_gen",
    complexity=0.9,
    input_text="实现一个支持分页的 REST API",
)
print(f"selected={decision.selected_model}, scores={decision.scores_per_model}")

# 定义 DAG 工作流
dag = DAGEngine(max_nodes=50, global_timeout=300)
dag.add_node(DAGNode("code_scan", agent="security-scan",
                     input_mapping={"code": "$input.code"}))
dag.add_node(DAGNode("code_review", agent="code-review",
                     input_mapping={"code": "$ctx.code_scan.output"}))
dag.add_edge("code_scan", "code_review")

# 执行
result = await dag.execute("task-001", input_data={"code": open("main.py").read()})
print(f"成本: ¥{result.total_cost:.4f}, 延迟: {result.total_latency:.1f}s, 完成率: {result.success_rate}")
```

### 平台层 Quick Start（RBAC 授权检查）

```python
from agentforge.platform.runtime import build_memory_container

container = build_memory_container()
# 给用户分配角色，即可进行授权决策
decision = await container.policy_engine.authorize(
    tenant_id="tenant-a",
    principal="user-1",
    action="ticket.writeback",
    resource={"ticket_id": "t-1", "status": "READY_TO_PUBLISH"},
)
print(decision.outcome)  # allowed / denied / requires_approval
```

---

## 工程保障

- **测试**：700+ 自动化测试（单元 + 集成 + 平台三层，当前 728），本地全绿
- **静态检查**：black / isort / flake8（max-line-length=100）/ mypy 全仓零错误
- **CI**：GitHub Actions 全量测试（Python 3.10/3.11/3.12），不使用 continue-on-error 掩盖失败
- **类型安全**：mypy 严格模式覆盖全仓
- **性能**：本地负载压测（自研多进程压测器，零外部依赖）测得平台 API 峰值 ~580–630 rps、推荐承载 ~500 rps/25 并发，详见 [P1-1 压测报告](docs/bench/P1-1-load-capacity.md)
- **可观测闭环**：LLM 调用逐条 trace（model/tokens/cost/latency/tenant）+ 工单→推理 trace_id 传播 + 进程内 `TraceRecorder`（有界 FIFO）+ dashboard `GET /v1/console/traces`；Langfuse/OTLP 接线方式文档化（[docs/observability/P1-2-observability.md](docs/observability/P1-2-observability.md)），本地零外部依赖可回查，生产可平滑接成熟可观测件

---

## 技术文章

| 文章 | 主题 | 链接 |
|---|---|---|
| 三层架构设计 | 编排层/运行时层/网关层的设计哲学 | [阅读](https://pengli-ctrl.github.io/blog/posts/04-agentforge-architecture-evolution) |
| DAG编排引擎 | 从静态编排到Planner Agent动态拆解 | [阅读](https://pengli-ctrl.github.io/blog/posts/05-orchestration-engine-evolution) |
| AI Gateway | 5模型路由+语义缓存+Token级成本管控 | [阅读](https://pengli-ctrl.github.io/blog/posts/06-ai-gateway-design) |
| 可靠性设计 | 三层超时/四级降级/请求放大管控 | [阅读](https://pengli-ctrl.github.io/blog/posts/07-production-reliability) |
| RAG工程化 | 幻觉率从46%降到16.2%的五层防护 | [阅读](https://pengli-ctrl.github.io/blog/posts/01-rag-engineering-hallucination-prevention) |


---

## 部署

> 历史演进导致当前存在 **两套相互独立的 Compose 集群**。它们跑的是两个不同
> 的应用（早期「编排层」单 Agent 服务 vs 当前「平台层」企业 AI 平台），API
> 端口均为 `8000`、状态存储端口均为 `6379`，**不可在同一台主机同时启用**。
> 请按下面的取舍选择其一，并先 `down` 掉另一套。

### 两套集群一览

| 集群 | Compose 文件 | 组成 | 说明 |
|---|---|---|---|
| **平台层（推荐 / 当前主形态）** | `deploy/platform/docker-compose.platform.yml` | api + worker + outbox-worker + postgres / valkey / temporal / minio / otel / kafka | 企业客服 AI 平台全栈（工单 / RBAC / 配额 / 审计 / 质量门禁 / 连接器） |
| 平台层·基础设施(轻量) | `deploy/platform/docker-compose.lite.yml` | 仅 postgres / valkey / temporal / minio | 本地开发用基础依赖，无 api/worker/kafka |
| **编排层（遗留 / 早期形态）** | `docker-compose.yml` | app + redis / mysql / kafka | 早期 Stage-A 单 Agent 编排服务，被平台层替代，保留兼容 |

### 推荐入口：平台层全栈启动

```bash
# 启动平台层（api + worker + outbox-worker + 全部基础设施）
make platform-up        # 等价: docker-compose -f deploy/platform/docker-compose.platform.yml up -d
# 停止
make platform-down
```

平台层 API 默认监听 `http://localhost:8000`（各 `/v1/*` 路由见上表）。

#### 鉴权（安全默认开启）

平台层 **鉴权默认开启（fail-closed）**，与全局安全默认保持一致：

- 启动后用默认演示密钥调用需鉴权接口：请求头 `X-Admin-Key: dev-admin-key-please-override`；
- **生产环境必须覆盖默认密钥**，否则存在暴露风险：

```bash
AGENTFORGE_ADMIN_API_KEY='你的强密钥' docker-compose -f deploy/platform/docker-compose.platform.yml up -d api
```

- 未配置任何密钥且环境为 `prod`/`staging` 时，服务会 **拒绝启动**（fail-closed），
  需显式配置密钥，或临时 `AGENTFORGE_ALLOW_NO_AUTH=true`（严禁用于公开暴露）。

### 仅启动平台层基础设施（本地开发）

```bash
make platform-lite-up    # postgres / valkey / temporal / minio
make platform-lite-down
```

### 编排层（遗留入口）

```bash
# 若确需使用早期编排层
make docker-up           # 等价: docker-compose up -d
make docker-down
```

### 端口对照与互斥提醒

| 端口 | 编排层 | 平台层 |
|---|---|---|
| `8000` | app (0.0.0.0) | api (0.0.0.0) |
| `6379` | redis | valkey |
| `9092` | kafka | kafka |
| `5432` | — | postgres |
| `7233` | — | temporal |
| `8080` | — | temporal-ui |
| `9000/9001` | — | minio |

两套共享 `8000/6379/9092`。**同机请勿同时启用**，先用 `down` 停止一套再启另一套。


---

## 关于作者

**彭黎** — 8年后端研发，3年团队管理，专注 AI Agent 架构与企业 AI 平台方向。

- 📝 博客：https://pengli-ctrl.github.io/blog
- 💻 GitHub：https://github.com/pengli-ctrl
- 📧 邮箱：pl2847253@gmail.com
- 📖 掘金：https://juejin.cn/user/4140096632135322

---

## License

[MIT License](LICENSE) © 2024 彭黎