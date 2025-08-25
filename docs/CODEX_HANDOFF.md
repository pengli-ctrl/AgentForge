# AgentForge 后续实施交接说明

## 1. 交接目标

本文件用于把 AgentForge 的历史背景、当前完成度、工程约束、后续阶段和验收方式完整交给后续 AI 工程师或人类工程师，避免从零重复分析。

当前目标不是继续扩展一个通用 Agent Demo，而是把 AgentForge 建设成面向中小企业的企业 AI 流程平台。第一个落地场景是“客服与售后工单智能处理”。

## 2. 必读信息

### 仓库

- 仓库路径：`C:/Users/HP/Documents/Codex/2026-09-17/mu/work/AgentForge`
- 当前分支：`codex/support-copilot-foundation`
- 交接基线提交：`1c83f2834b78c00aa54350b33dfa16fc63767952`，实际 HEAD 以 `git log -1` 为准。
- 远端仓库：`https://github.com/pengli-ctrl/AgentForge`

### 外部规划文档

- `C:/Users/HP/Documents/Codex/2026-09-17/mu/outputs/AgentForge-Enterprise-AI-Plan.md`
- `C:/Users/HP/Documents/Codex/2026-09-17/mu/outputs/AgentForge-Million-Scale-Engineering-Spec.md`
- `C:/Users/HP/Documents/Codex/2026-09-17/mu/outputs/AgentForge-MVP-Customer-Service-Scenario.md`

### 仓库内关键目录

- 平台 API：`agentforge/platform/api`
- 应用服务：`agentforge/platform/application`
- 领域模型：`agentforge/platform/domain`
- 基础设施：`agentforge/platform/infrastructure`
- Temporal 工作流：`agentforge/platform/workflows`
- 数据库迁移：`alembic/versions`
- 平台测试：`tests/platform`
- 部署配置：`deploy/platform`

## 3. 当前已经完成的能力

当前代码已经完成“阶段 A：客服 MVP 闭环”，包括：

1. 飞书消息签名校验、Challenge 和事件解析。
2. 工单创建、幂等键、状态机、风险分类和优先级判断。
3. 知识文档入库、分块、基础检索和引用返回。
4. 回复草稿生成、引用校验、模型路由、租户预算和成本记录。
5. Temporal 工作流、审批 Signal、Outbox、Kafka Publisher、失败重试和 DLQ 重放。
6. 人工审核：接受、编辑、驳回，以及审核后回复发布。
7. 飞书回复 Connector，包含令牌缓存、过期刷新、响应归一化和错误码处理。
8. 审计事件、操作者、`trace_id`、成本汇总和模型分布统计。
9. 租户级 API Key 鉴权和 Outbox 管理员 Key。
10. 人工反馈自动沉淀为评估样本，提供采纳率、编辑率、驳回率和草稿可用率。
11. Alembic `0001` 到 `0008` 迁移链路。
12. PostgreSQL FTS + pgvector 混合检索：向量列/HNSW 与 GIN 索引/embedding 版本字段、`KnowledgeRepository.search` 混合检索接口、Memory 与 SQLAlchemy 双实现、旧数据 embedding 回填、检索 `mode` 与混合权重。
13. 检索重排与召回评估：确定性 `HybridReranker`（基础分+查询词覆盖+位置分）、检索质量指标纯函数（Recall@K/Precision@K/MRR/引用正确率）、在线 `RetrievalEvaluationService`（GoldenQuery→QueryEvaluation→RetrievalReport）、`/v1/knowledge/search` 支持 `rerank`、新增 `POST /v1/evaluations/retrieval` 评估接口。
14. 结构化分类、版本与质量门禁：`ClassificationResult` 结构化字段与结构化输出校验、分类质量评估（分类准确率/优先级准确率/结构化合法率/高风险漏报率）、版本化 `PromptRegistry`（注册/激活/回退/解析）与 `ModelVersionRegistry`（选型+回退）、基于检索与分类评估的发布质量门禁（PASS/HOLD/BLOCK，高风险漏报一票否决）。详见第 8 节增量 3 记录。
15. 离线回归运行器与 Golden Dataset：`GoldenItem`/`RegressionRun`/`QualityReport` 领域模型、`RegressionRepository`（memory/sqlalchemy 双实现，`golden_items` 与 `regression_runs` 表 + Alembic `0008`）、`RegressionRunner` 离线回归（加载 Golden→召回+分类评估→质量门禁→报告持久化）、`/v1/regression/*` API（Golden 维护 + 触发回归 + 运行记录查询）。详见第 8 节增量 4 记录。
16. Connector SDK 与企业连接起点：`Connector` ABC（health/invoke/compensate）与 `ConnectorRegistry`（内存注册、租户隔离、动作白名单、disabled 校验）、`ConnectorContext`（幂等键/任务/追踪/操作者）、`CredentialReference` 凭据引用模型（只存 vault 引用不落机密）、通用签名 `WebhookSignatureVerifier` + `WebhookAdapter`（HMAC-SHA256、泛化事件规范化 `WebhookDelivery`→`to_ticket_event`）、`OpenAPIAdapter`（HTTP 调用带幂等键头、有界重试退避、令牌桶限流、审计回调）、`/v1/connectors/*` API。不引入新迁移（注册表内存态，与 PromptRegistry 一致）。详见第 8 节增量 1（阶段 C）记录。
17. 全仓测试基线，目前 `572 passed`（`tests/platform` 106 项）。

## 4. 当前验证命令

在仓库根目录执行：

```powershell
python -m pytest tests -q
python -m pytest tests/platform -q
python -m black --check --line-length 100 agentforge tests alembic
python -m isort --check-only --profile black agentforge tests alembic
python -m flake8 --max-line-length=100 --extend-ignore=E203,W503 agentforge tests alembic
python -m mypy agentforge/platform/application/reranker.py agentforge/platform/application/retrieval_metrics.py agentforge/platform/application/retrieval_evaluation_service.py agentforge/platform/application/classification_evaluation_service.py agentforge/platform/application/quality_gate_service.py agentforge/platform/application/prompt_registry.py agentforge/platform/application/version_registry.py agentforge/platform/application/regression_runner.py agentforge/platform/application/connector_registry.py agentforge/platform/application/webhook_adapter.py agentforge/platform/application/openapi_adapter.py agentforge/platform/domain/retrieval.py agentforge/platform/domain/quality.py agentforge/platform/domain/regression.py agentforge/platform/domain/connector.py agentforge/platform/domain/knowledge.py agentforge/platform/application/knowledge_service.py agentforge/platform/application/ports.py agentforge/platform/api/evaluation_router.py agentforge/platform/api/release_router.py agentforge/platform/api/regression_router.py agentforge/platform/api/connector_router.py agentforge/platform/api/knowledge_router.py agentforge/platform/infrastructure/memory_regression_repository.py agentforge/platform/infrastructure/sqlalchemy_regression_repository.py agentforge/platform/infrastructure/db/models.py agentforge/platform/runtime.py
python -m alembic upgrade head --sql
```

> 说明：`mypy` 命令仅针对本仓库新增/改动的增量源文件。全仓 `mypy` 仍会在阶段 A 遗留的 `workflows/support_ticket.py`、`infrastructure/kafka_publisher.py`、`outbox_worker.py` 报存量类型错误（非增量引入，未在增量范围内改动）。

本地环境没有 Docker，因此目前不能实际启动 PostgreSQL、Kafka、Temporal、Valkey、MinIO 和 OTel Collector。Compose 配置只能做解析和静态测试。后续接管方如果具备 Docker，应优先补真实集成测试。

## 5. 不可破坏的工程约束

1. 不要回退或覆盖已有提交，尤其不要使用 `git reset --hard` 和 `git checkout --`。
2. 每个增量都应该独立提交，提交信息使用清晰的 `feat:`、`fix:` 或 `test:` 前缀。
3. 未经用户明确要求，不要推送远端。
4. 每次修改后必须运行相关测试；涉及共享能力时运行全仓测试。
5. 新增数据库结构时必须同时修改 ORM 模型、Alembic 迁移和仓储测试。
6. 所有业务表必须带 `tenant_id`，所有跨租户查询必须显式携带租户条件。
7. 高风险动作必须经过审批，未经审批不得执行写回、退款、支付、合同修改等动作。
8. 生产环境必须保持默认关闭的宽松行为只能存在于开发模式，生产鉴权和审计不能被绕过。
9. 不提交真实密钥、Token、用户隐私数据或生产数据库连接串。
10. 优先复用现有工程模式：Repository、Protocol Port、Memory/SQLAlchemy 双实现、FastAPI Router、pytest。

## 6. 当前明确缺口

当前代码还不是生产可交付版本，主要缺口如下：

- 重排器与召回评估（Recall@K/引用正确率）已上线基础版本（见第 8 节增量 2、增量 4 记录）；增量 4 已引入持久化的离线回归运行器（`RegressionRunner` + `golden_items`/`regression_runs` 表），可触发离线回归并回查质量报告。
- PostgreSQL FTS + pgvector 的 SQL 路径已通过方言编译与离线迁移验证，但本地无 Docker，尚未对真实 PostgreSQL 做端到端跑通。
- Connector SDK、通用签名 Webhook Adapter 与 OpenAPI Adapter 已上线（见第 8 节阶段 C 增量 1 记录），但连接器注册表为进程内存态（进程重启即空），且尚无 CRM、工单系统或业务数据库的专有写回连接器实现。
- 缺少 RBAC、策略引擎、OpenFGA、用户级权限和管理员权限矩阵。
- 缺少客服工作台、审批收件箱、DLQ 管理页面和运营成本/质量看板。
- 缺少数据集版本（Golden Dataset 的版本化快照）与跨进程一致的发布历史；Prompt/模型版本当前为进程内存注册表（进程重启即清空），未落库、未有跨进程一致性（见第 8 节增量 3、增量 4 记录）。
- 缺少 PostgreSQL、Kafka、Temporal 的真实端到端集成测试和故障演练。
- 缺少生产部署、Helm、Terraform、备份、升级、回滚和灾备方案。
- 当前 API Key 是静态映射，不是企业级身份系统。

## 7. 后续路线图

原工程书使用“阶段 0 到阶段 5”。基于当前真实完成度，后续建议重新基线为“阶段 A 到阶段 F”，避免把已经部分完成的阶段重复计算。

### 阶段 A：客服 MVP 闭环，已完成

共 7 个增量：

1. 工单模型、状态机、幂等和持久化。
2. 飞书事件接入与知识检索。
3. 草稿、引用、模型路由、成本和 Trace。
4. Temporal、Outbox、Kafka、重试和 DLQ。
5. 审批、人工审核、编辑和回复发布。
6. 审计、成本汇总、API Key 和评估样本。
7. 全仓测试基线和兼容层修复。

### 阶段 B：检索与模型质量升级

共 4 个增量：

1. PostgreSQL FTS + pgvector 混合检索与 Alembic 迁移。⚠️ 已完成（见第 8 节增量完成记录）。
2. 重排器、召回评估、引用正确率和 Recall@K。⚠️ 已完成（见第 8 节增量完成记录）。
3. 结构化分类、Prompt 版本、模型版本和质量门禁。⚠️ 已完成（见第 8 节增量完成记录）。
4. 基于评估样本的离线回归运行器与质量报告。⚠️ 已完成（见第 8 节增量完成记录）。

### 阶段 C：企业连接与治理

共 5 个增量：

1. Connector SDK、Webhook Adapter、OpenAPI Adapter。⚠️ 已完成（见第 8 节增量完成记录）。
2. CRM、工单系统或业务数据库连接器。
3. RBAC、Policy Engine、OpenFGA 和权限模型。
4. 密钥管理、租户隔离、限流、幂等写回和对账。
5. 高风险动作审计闭环和人工授权边界。

### 阶段 D：管理控制台与运营

共 4 个增量：

1. 工单列表、详情、审批收件箱和人工编辑界面。
2. Outbox、DLQ、任务状态、重试和故障操作页面。
3. 成本、配额、模型分布和质量指标看板。
4. 审计查询、租户配置和连接器管理页面。

### 阶段 E：真实试点与效果优化

共 5 个增量：

1. 收集 200-500 条真实历史工单并建立 Golden Dataset。
2. 建立人工基线、影子运行和抽样评估。
3. 优化 Prompt、检索、路由和错误降级。
4. 完成一个真实客户或高保真模拟客户试点。
5. 输出案例报告、演示视频、指标报告和面试材料。

### 阶段 F：生产化与产品化

共 6 个增量：

1. Kubernetes、Helm、Terraform 和一套可重复部署方案。
2. PostgreSQL、Kafka、Temporal、Valkey、MinIO 的生产高可用拓扑。
3. CI/CD、数据库迁移、灰度发布、升级和回滚。
4. 安全、合规、备份、容灾和密钥轮换。
5. 稳定版本、兼容策略、Connector SDK 和行业模板。
6. 开源核心与企业控制面、许可和企业支持方案。

阶段 A 与阶段 B 已完成（阶段 B 全 4 个增量均已完成，见第 8 节增量完成记录）。阶段 C 已启动并完成第 1 个增量（Connector SDK + Webhook/OpenAPI Adapter），后续剩余 4 个阶段半程，共 19 个建议增量。每个增量应控制在 0.5 到 2 天内可完成、可测试、可提交的范围内。

## 8. 增量完成记录

阶段 A（7 个增量）、阶段 B（4 个增量）均已完成；阶段 C 已启动并完成第 1 个增量。阶段 B 增量 1-4 与阶段 C 增量 1 的完成记录如下；下一步进入阶段 C 增量 2（CRM/工单系统/业务数据库连接器）。

### 阶段 C 增量 1 完成记录（2026-09-18）

- 提交：见本记录末尾（阶段 C 增量1 提交 hash）。
- 改动：
  - 新增 `agentforge/platform/domain/connector.py`：`ConnectorKind`、`ConnectorRiskLevel`、`CredentialReference`（凭据只存 vault 引用、不落机密，对齐 SC-303）、`ConnectorContext`（tenant_id/task_id/idempotency_key/trace_id/actor）、`ConnectorSpec`（租户/名称/类型/版本/风险级/端点/动作白名单/凭据引用/开关）、`ConnectorHealth`、`ConnectorInvocationResult`、`WebhookDelivery`（入站事件规范化 + `to_ticket_event()` 转 `SupportTicketService` 入站形状）。
  - 新增 `agentforge/platform/application/connector_registry.py`：Connector SDK 契约 `Connector` ABC（`health`/`invoke`/`compensate`，对齐工程书 5.11/6.10）与 `ConnectorRegistry`（内存注册、按 connector_id 查 spec/adapter、租户隔离校验、动作白名单、disabled 拦截、批量健康聚合、带幂等/租户/动作约束的 `invoke`）。
  - 新增 `agentforge/platform/application/webhook_adapter.py`：通用 `WebhookSignatureVerifier`（HMAC-SHA256 校验 timestamp+nonce+body，支持按租户查秘钥 provider / 默认秘钥，SC-301 通用签名 webhook）与 `WebhookAdapter`（把 provider 信封规范化为 `WebhookDelivery`，含通用文本解析器）。
  - 新增 `agentforge/platform/application/openapi_adapter.py`：`OpenAPIAdapter` 实现 Connector ABC，基于 HTTP 端点执行 GET/POST/PUT/PATCH，转发幂等键头 `X-Idempotency-Key`、有界重试退避（`max_retries`+指数 backoff）、令牌桶限流（`rate_per_second`）、引用式鉴权注入（`auth_header`+`auth_value_provider`）、可选审计回调（记录动作/租户/任务/幂等键/成败，且审计失败不影响主调用）。
  - `runtime.py` 装配共享 `ConnectorRegistry`；`app.py` 挂载 `create_connector_router`（`GET /v1/connectors`、`GET /v1/connectors/{id}`、`GET /v1/connectors/{id}/health`、`POST /v1/connectors/{id}/invoke`，未注册 404、失败 502）。
  - 新增 `tests/platform/test_connector.py`（14 项：Webhook 签名校验有效/无效/缺秘钥/provider、WebhookAdapter 解析与转工单事件、注册契约与幂等键头转发、租户隔离、动作白名单、disabled/未注册、健康与列表、失败重试、审计回调、凭据引用不含机密）与 `tests/platform/test_connector_api.py`（4 项：空列表、404、健康 404、未注册 invoke 404）。
- 验证：`tests/platform` 106 passed、全仓 572 passed、Black/isort/Flake8 通过、增量相关 6 个源文件 mypy 通过（`Success: no issues found`）、`alembic heads` 仍为 `20260918_0008`（本增量不引入新迁移，注册表内存态）。
- 剩余风险：Connector 注册表为进程内存态（重启即空），凭据仅存引用但尚无真实 vault/密钥后端；OpenAPI Adapter 的限流/重试为进程内令牌桶实现，未接分布式限流；真实 CRM/工单系统写回需在阶段 C 增量 2 落地；PostgreSQL/Kafka 真实集成仍未在 Docker 跑通。
- 下一步：阶段 C 增量 2 CRM、工单系统或业务数据库连接器。

### 阶段 B 增量 1 完成记录（2026-09-18）

- 提交：见 `git log -1` 阶段 B 增量1 提交。
- 改动：
  - 新增 `agentforge/platform/application/knowledge_embedder.py`：确定性特征哈希 Embedder（维度 64），`EMBEDDING_DIM/MODEL/VERSION`，可替换为真实语义模型。
  - 新增 `agentforge/platform/infrastructure/hybrid_scores.py`：关键词分与向量分归一化加权融合 + 排序回填。
  - `KnowledgeChunk` 增加可选 `embedding/embedding_model/embedding_version`；`RetrievedChunk` 增加 `mode/fts_score/vector_score`。
  - `KnowledgeRepository.search` 扩展 `mode`(hybrid/keyword/vector) 与 `fts_weight/vector_weight`；新增 `backfill_embeddings`。
  - `MemoryKnowledgeRepository` 同步支持混合检索与回填，单元测试无需 PostgreSQL。
  - `SQLAlchemyKnowledgeRepository` 方言分支：postgresql 用 `to_tsvector @@ plainto_tsquery`+`ts_rank` 与 `embedding <=> query` 余弦；sqlite 回退 ILIKE + Python 余弦。
  - Alembic `0007`：`knowledge_chunks` 增加 `embedding VECTOR(64)`/`embedding_model`/`embedding_version`，建 GIN FTS 索引与 HNSW 向量索引。
  - 知识 API `/v1/knowledge/search` 增加 `mode`、`fts_weight`、`vector_weight` 参数，返回结构含各检索模式与分数。
  - 新增 `tests/platform/test_hybrid_retrieval.py`（10 项）：召回率、租户隔离、空结果、双实现一致性、回填。
- 验证：`tests/platform` 52 passed、全仓 518 passed、Black/isort/Flake8、`alembic upgrade head --sql` 均通过。
- 剩余风险：PostgreSQL 真实集成（真实 FTS rank/pgvector 距离/迁移执行）未在 Docker 环境跑通；生产建议替换 `HashEmbedder` 为真实语义 embedding 模型并重跑迁移回填。
- 下一步：阶段 B 增量 2 重排器与 Recall@K 召回评估。

### 阶段 B 增量 2 完成记录（2026-09-18）

- 提交：见 `git log -1` 阶段 B 增量2 提交。
- 改动：
  - 新增 `agentforge/platform/application/reranker.py`：`Reranker` Protocol + 确定性 `HybridReranker`（FTS/向量基础分 + 查询词覆盖度 + 标题/内容位置加权），为离线可测设计。
  - 新增 `agentforge/platform/application/retrieval_metrics.py`：纯函数 `recall_at_k`/`precision_at_k`/`mean_reciprocal_rank`/`citation_accuracy`/`average`。
  - 新增 `agentforge/platform/domain/retrieval.py`：`GoldenQuery`（tenant_id/query/expected_chunk_ids/expected_citations）、`QueryEvaluation`、`RetrievalReport`。
  - 新增 `agentforge/platform/application/retrieval_evaluation_service.py`：`RetrievalEvaluationService.evaluate(queries, k, rerank, mode)` 逐条执行检索→可选重排→计算指标→聚合报告。评估为在线计算，不落库（回归运行器属增量 4）。
  - `KnowledgeService.search` 支持可选 `rerank`；`/v1/knowledge/search` 增加 `rerank: bool` 参数。
  - `evaluation_router.py` 新增 `POST /v1/evaluations/retrieval`（GoldenQueries 批量评估 + 租户隔离校验）。
  - `runtime.py` 装配共享 `HybridReranker()` 实例，注入 `KnowledgeService` 与 `RetrievalEvaluationService`。
  - 新增 `tests/platform/test_retrieval_evaluation.py`（12 项）：指标纯函数、HybridReranker 行为（关键词覆盖优先于向量分）、评估评分（memory/sqlalchemy 参数化）、租户隔离。
  - 新增 `tests/platform/test_retrieval_evaluation_api.py`（3 项）：search rerank、retrieval 评估接口、租户隔离。
- 验证：`tests/platform` 67 passed、全仓 533 passed、Black/isort/Flake8 通过、增量相关 10 个源文件 mypy 通过、`alembic upgrade head --sql` 通过。
- 剩余风险：现有 mypy 在 `kafka_publisher.py`/`outbox_worker.py`/`support_ticket.py` 有 3 处存量类型错误（阶段 A 遗留，非本增量引入，未在本次范围改动）；PostgreSQL 真实检索回归未跑通；`HybridReranker` 是确定性启发式而非学习式重排。
- 下一步：阶段 B 增量 3 结构化分类、Prompt 版本、模型版本与质量门禁。

### 阶段 B 增量 3 完成记录（2026-09-18）

- 提交：见 `git log -1` 阶段 B 增量3 提交。
- 改动：
  - 新增 `agentforge/platform/domain/quality.py`：`PromptTemplate`（name/version/content/status）、`PromptStatus`(draft/active/deprecated)、`ModelVersion`、`ReleaseCandidate`、`QualityGateVerdict`(pass/hold/block)、`QualityGateResult`。
  - 扩展 `classifier.py`：`ClassificationResult` 与 `ClassificationModel` 增加结构化字段（含 schema_version / structured_output_valid / raw），新增 `StructuredClassifier` Protocol 与 `StructureValidator`。
  - 新增 `agentforge/platform/application/prompt_registry.py`：`PromptRegistry` 版本化注册/解析/激活/回退，同名版本同时唯一 ACTIVE。
  - 新增 `agentforge/platform/application/version_registry.py`：`ModelVersionRegistry` 版本注册与 `resolve`（回退 `*` 通配/默认版本）。
  - 新增 `agentforge/platform/application/classification_evaluation_service.py`：`ClassificationEvaluationService.evaluate(samples)` 输出分类准确率/优先级准确率/结构化输出合法率/高风险漏报率（用注入分类器执行，RuleBased 与可替换实现均可）。
  - 新增 `agentforge/platform/application/quality_gate_service.py`：`QualityGateService` 基于 `RecoveryReport` 与分类报告的发布门禁（阈值：召回硬门槛/引用硬门槛/分类硬门槛，高风险漏报一票否决 → FILTER）。
  - `evaluation_router.py` 新增 `POST /v1/evaluations/classification`；新增 `agentforge/platform/api/release_router.py`：`POST /v1/release/prompt`、`POST /v1/release/model`、`POST /v1/release/gate`（门禁聚合检索+分类，复查找 PASS/HOLD/BLOCK），挂载到 `app.py`；`runtime.py` 装配以上 registry 与服务。
  - 新增 `tests/platform/test_quality_gate.py`（12 项）：publish 回退（v2 激活后 v1 自动 deprecated）、resolve 默认/`*` 回退、分类评估准确率/高风险漏报、门禁 PASS/HOLD/BLOCK、`v1 门禁复找出 degraded。
  - 新增 `tests/platform/test_quality_gate_api.py`（4 项）：分类评估接口、门禁接口通过/召回拦截/缺数据校验。
- 验证：`tests/platform` 83 passed、全仓 549 passed、Black/isort/Flake8 通过、增量相关 6 个新源文件 mypy 通过（`Success: no issues found`）、`alembic upgrade head --sql` 通过（增量 3 无迁移，`alembic_version` 仍为 `20260918_0007`）。
- 剩余风险：Prompt/模型版本注册表为进程内存实现，重启即空，未落库（离线回归运行器与持久化发布记录属增量 4）；分类准确率依赖识别器注入，真实 LLM 结构化输出闭环按增量 4 做 Golden Dataset 验证；质量问题 fully to Production 前应补充真实 PostgreSQL 集成回归。
- 下一步：阶段 B 增量 4 基于评估样本的离线回归运行器与质量报告（Golden Dataset 化）。

### 阶段 B 增量 4 完成记录（2026-09-18）

- 提交：见 `git log -1` 阶段 B 增量4 提交。
- 改动：
  - 新增 `agentforge/platform/domain/regression.py`：`GoldenItem`（离线 Gold 标准样本，含期望检索命中/期望分类）、`RegressionRunStatus`、`RegressionRun`（一次回归执行快照）、`QualityReport`（可持久化的质量报告）。
  - 新增 `RegressionRepository` Protocol（`save_golden`/`list_golden`/`save_run`/`save_report`/`get_run`/`list_runs`），memory/sqlalchemy 双实现。
  - 新增 `agentforge/platform/infrastructure/memory_regression_repository.py` 与 `sqlalchemy_regression_repository.py`。
  - `models.py` 新增 `GoldenItemRecord`/`RegressionRunRecord`；Alembic `0008` 新增 `golden_items` 与 `regression_runs` 表（含 tenant_id 索引、JSON 期望命中列、报告 JSON 列）。
  - 新增 `agentforge/platform/application/regression_runner.py`：`RegressionRunner.run()` 加载租户 Golden Dataset → 组装召回 GoldenQuery + 分类样本 → 调 `RetrievalEvaluationService` 与 `ClassificationEvaluationService` → 聚合指标 → 质量门禁 → 生成 `RegressionRun` + `QualityReport` 并持久化。
  - 新增 `agentforge/platform/api/regression_router.py`：`POST /v1/regression/golden`、`GET /v1/regression/golden`、`POST /v1/regression/run`（触发离线回归）、`GET /v1/regression/runs`、`GET /v1/regression/runs/{run_id}`，挂载到 `app.py`，runtime 装配共享 `regression_repository` 与 `regression_runner`。
  - 新增 `tests/platform/test_regression.py`（5 项）：端到端回归报告持久化、租户隔离、空数据集、SQLAlchemy golden/run/report 往返、API 种子与触发回归。
- 验证：`tests/platform` 88 passed、全仓 554 passed、Black/isort/Flake8 通过、增量相关 7 个源文件 mypy 通过（`Success: no issues found`）、`alembic upgrade head --sql` 通过（`golden_items`/`regression_runs` 建表 + `alembic_version` 到 `20260918_0008`）。
- 剩余风险：Golden Dataset 仍为演示级种子，真实回归需收集真实工单喂入 `golden_items`；回归运行当前同步串行（可加并发/异步队列）；`RegressionRepository` 已落库但用 JSON 存储报告快照，若需按指标字段 SQL 查询需升级为列式；真实 PostgreSQL 端到端回归仍未在 Docker 跑通。
- 下一步：阶段 C 企业连接与治理（Connector SDK、Webhook/OpenAPI Adapter 等），或先回填真实 Golden Dataset 后做回归指标校准。

## 9. 给扣子或后续 AI 工程师的最短提示词

```text
项目路径：C:/Users/HP/Documents/Codex/2026-09-17/mu/work/AgentForge
当前分支：codex/support-copilot-foundation
交接文档：C:/Users/HP/Documents/Codex/2026-09-17/mu/work/AgentForge/docs/CODEX_HANDOFF.md
工程书：C:/Users/HP/Documents/Codex/2026-09-17/mu/outputs/AgentForge-Million-Scale-Engineering-Spec.md
场景基线：C:/Users/HP/Documents/Codex/2026-09-17/mu/outputs/AgentForge-MVP-Customer-Service-Scenario.md

先完整阅读仓库内交接文档和外部规划文档，再检查当前分支、提交记录、测试和代码结构。当前阶段 A 与阶段 B 已完成（FTS+pgvector 混合检索、重排与召回评估、结构化分类/Prompt/模型版本与质量门禁、离线回归运行器与 Golden Dataset 均已落地），阶段 C 已启动并完成第 1 个增量（Connector SDK、通用签名 Webhook Adapter、OpenAPI Adapter）。下一步从阶段 C 的第 2 个增量开始：CRM、工单系统或业务数据库连接器。

要求：
1. 不要回退已有提交。
2. 每个增量单独提交，不要推送远端。
3. 修改后运行相关测试、全仓测试、Black、isort、Flake8 和 Alembic SQL 检查。
4. 保持 tenant_id 隔离、审批、审计、成本和失败重试能力。
5. 遇到不明确的地方优先读取现有代码和文档，不要重新设计一套无关架构。
```

## 10. 每个增量的完成定义

一个增量只有同时满足以下条件才算完成：

1. 代码、迁移、测试和文档同步更新。
2. 相关测试通过，共享能力变更时全仓测试通过。
3. 格式检查通过。
4. 没有提交真实密钥或隐私数据。
5. 已完成独立 Git 提交。
6. 在回复或提交信息中明确说明改动、验证结果、剩余风险和下一步。
