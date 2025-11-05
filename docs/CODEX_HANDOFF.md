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
17. 连接器注册持久化与工单写回闭环：`ConnectorRepository` Protocol（memory/sqlalchemy 双实现 + `connector_specs` 表与 Alembic `0009`）、注册表 `ConnectorRegistry` 支持从仓储装载（`load_from_repository`/`set_adapter`）、`OpenAPIAdapter` 持久化重建工厂 `build_openapi_adapter`、`TicketWritebackService`（已审批/已发布工单按幂等键 `wb-{ticket_id}` 写回 CRM/工单系统，含审计、连接器解析与失败报错）、`POST /v1/connectors` 注册、`DELETE /v1/connectors/{id}`、`POST /v1/tickets/{id}/writeback` 写回接口。打通“读取→AI→审批→写回”闭环。详见第 8 节增量 2（阶段 C）记录。
18. 全仓测试基线，目前 `693 passed`（`tests/platform` 227 项）。
19. **RBAC + Policy Engine（阶段 C 增量 3）**：`Role`/`RoleAssignment`/`Permission` 领域模型（tenant 隔离、built-in 角色）、`ActionPolicy` 声明式动作策略（fail-closed、风险级、审批要求、角色/权限 allow-list），`PolicyEngine` 组合角色权限 + 动作策略 + OpenFGA 式关系检查给出决策（allowed / denied / requires_approval）；`OpenFGAClient` 提供内存态关系 tuple CRUD + check（可替换真实 OpenFGA 服务）；`RbacRepository` memory/sqlalchemy 双实现 + `rbac_roles`/`rbac_role_assignments` 表（Alembic `0010`）；`/v1/rbac/*` 接口（角色 CRUD、权限设置、用户-角色赋值、`/authorize` 授权检查）。
20. **租户配额管理（阶段 C 增量 4）**：`TenantQuota` 领域模型（月度预算/告警阈值/硬上限/enabled 开关）+ `TenantQuotaRepository` Protocol（memory/sqlalchemy 双实现）+ `tenant_quotas` 表（Alembic `0011`）；`QuotaAwareModelGateway` 扩展逐租户配额覆盖（`_resolve_budget` 返回 budget+enforce，禁用配额即不强制）；`/v1/quotas/*` 配额管理接口（PUT/GET/list/DELETE）与 `/v1/console/overview` 管理控制台聚合概览（配额+成本+DLQ 失败数+审计事件）。
21. **高风险动作审计闭环 + 人工授权边界（阶段 C 增量 5）**：`AuthorizationDecision` 授权审计记录（principal/action/outcome/reasons/approval_ref）+ `HighRiskActionAuthorizer` 授权门禁——解析调用者角色/权限、经 `PolicyEngine` 求值、强制执行"高风险动作须人工审批"边界（工单未到 READY_TO_PUBLISH/未获批 → DENIED），并把每次授权（放行与拒绝）写入审计事件（`{action}.authorization`，含 outcome/reasons/approval_ref/actor），回答"谁执行/为何允许"；`PolicyEngine` 修正为先验权限后验审批（无权限者无法借已审批工单绕过）；写回端点接入门禁（`PermissionError`→403）+ `POST /v1/authorize` 显式授权审计接口。
22. **管理控制台基础页面接口（阶段 D 增量 1）**：`TicketRepository` 新增 `list(tenant_id, status, limit, cursor)`（memory/sqlalchemy 双实现，支持状态过滤 + 游标分页、按 `created_at` 排序）；`/v1/console/tickets` 客服工作台按状态分页列工单、`/v1/console/inbox` 审批收件箱（仅 `waiting_approval`）并带风险级、`/v1/console/overview` 增加任务状态计数（tasks，按状态统计且租户隔离）；`CostRepository` 新增 `list_tenants()`（memory/sqlalchemy），`/v1/console/costs` 管理员多租户成本/配额总览（并集 cost 租户 + quota 租户、跨租户聚合）；DLQ 管理沿用 `/v1/outbox/failed`+`/replay`。
23. **Outbox/DLQ/任务状态、重试与故障操作维护（阶段 D 增量 2）**：`SQLAlchemyOutboxStore` 新增 `list_events(tenant_id|None, status|None, limit, cursor)`、`get_event(tenant_id|None, event_id)`、`count_events(tenant_id|None)`（pending/published/failed/discarded 分状态计数）、`discard(tenant_id|None, event_id)`（置 `status="discarded"`）；新增 `MemoryOutboxStore` 提供与 SQLAlchemy 相同的 outbox 管理表面（enqueue/fetch_pending/mark_published/mark_failed/list_failed/list_events/get_event/count_events/discard/replay），并在 `build_memory_container` 装配；`outbox_router` 新增 `GET /v1/outbox/events`（状态过滤 + 游标分页）、`GET /v1/outbox/events/count`、`GET /v1/outbox/events/{event_id}`、`POST /v1/outbox/events/{event_id}/discard`（admin-global 访问，detail/discard 以 `tenant_id=None` 免租户过滤）。
24. **成本/配额/模型分布/质量指标看板接口（阶段 D 增量 3）**：`CostRepository` 新增 `daily_summary(tenant_id, days)`（按天聚合 request/input
25. **审计查询、租户配置与连接器管理页面接口（阶段 D 增量 4）**：`AuditRepository` 新增 `query_events(tenant_id|None, action|None, actor_id|None, resource_id|None, resource_type|None, limit, cursor)`（过滤 + offset 游标分页，`tenant_id=None` 为 admin-global 多租户查询；memory/sqlalchemy 双实现）；`/v1/audit` 支持 action/actor_id/resource_type 过滤与游标分页，`tenant_id` 可选（缺省走 `authorize_admin`）；`/v1/console/tenants`（admin 多租户 quota 配置 + used + enabled）、`/v1/console/audit`（admin 审计查询）、`/v1/console/connectors`（admin 连接器全量列表 + registry health）与 `POST /v1/console/connectors/{id}/enabled`（启用/停用连接器，经 connector_repository 持久化）。以上 console 管理端点均经 `authorize_admin` 鉴权，服务未装配时 503。/output/amount，memory/sqlalchemy 双实现）；新增 `application/dashboard_service.py` `DashboardService`（组合 cost/quota/regression 仓储）提供 `cost_trend`（日趋势 + 汇总）、`model_distribution`（按模型聚合，按 cost 降序 + 占比 share）、`quota_snapshot`、`quality_metrics`（回归 run 序列 + 平均指标）；`console_router` 新增 `GET /v1/console/cost-trend`、`/v1/console/model-distribution`、`/v1/console/quality`、`/v1/console/dashboard`（聚合四块）；`runtime` 装配 `dashboard_service`，`app.py` 注入 console router。

## 4. 当前验证命令

在仓库根目录执行：

```powershell
python -m pytest tests -q
python -m pytest tests/platform -q
python -m black --check --line-length 100 agentforge tests alembic
python -m isort --check-only --profile black agentforge tests alembic
python -m flake8 --max-line-length=100 --extend-ignore=E203,W503 agentforge tests alembic
python -m mypy agentforge/platform/application/reranker.py agentforge/platform/application/retrieval_metrics.py agentforge/platform/application/retrieval_evaluation_service.py agentforge/platform/application/classification_evaluation_service.py agentforge/platform/application/quality_gate_service.py agentforge/platform/application/prompt_registry.py agentforge/platform/application/version_registry.py agentforge/platform/application/regression_runner.py agentforge/platform/application/connector_registry.py agentforge/platform/application/webhook_adapter.py agentforge/platform/application/openapi_adapter.py agentforge/platform/application/ticket_writeback.py agentforge/platform/application/quota_service.py agentforge/platform/domain/retrieval.py agentforge/platform/domain/quality.py agentforge/platform/domain/regression.py agentforge/platform/domain/connector.py agentforge/platform/domain/knowledge.py agentforge/platform/domain/tenant_quota.py agentforge/platform/application/knowledge_service.py agentforge/platform/application/ports.py agentforge/platform/api/evaluation_router.py agentforge/platform/api/release_router.py agentforge/platform/api/regression_router.py agentforge/platform/api/connector_router.py agentforge/platform/api/knowledge_router.py agentforge/platform/api/support_router.py agentforge/platform/api/rbac_router.py agentforge/platform/api/quota_router.py agentforge/platform/api/console_router.py agentforge/platform/infrastructure/memory_regression_repository.py agentforge/platform/infrastructure/sqlalchemy_regression_repository.py agentforge/platform/infrastructure/memory_connector_repository.py agentforge/platform/infrastructure/sqlalchemy_connector_repository.py agentforge/platform/infrastructure/memory_rbac_repository.py agentforge/platform/infrastructure/sqlalchemy_rbac_repository.py agentforge/platform/infrastructure/memory_tenant_quota_repository.py agentforge/platform/infrastructure/sqlalchemy_tenant_quota_repository.py agentforge/platform/domain/rbac.py agentforge/platform/domain/policy.py agentforge/platform/application/policy_engine.py agentforge/platform/application/openfga_adapter.py agentforge/platform/application/builtin_policies.py agentforge/platform/infrastructure/db/models.py agentforge/platform/runtime.py agentforge/platform/domain/authorization.py agentforge/platform/application/high_risk_authorizer.py agentforge/platform/api/authorization_router.py agentforge/platform/infrastructure/memory_ticket_repository.py agentforge/platform/infrastructure/sqlalchemy_ticket_repository.py agentforge/platform/infrastructure/memory_cost_repository.py agentforge/platform/infrastructure/sqlalchemy_cost_repository.py agentforge/platform/infrastructure/outbox_store.py agentforge/platform/infrastructure/memory_outbox_store.py agentforge/platform/api/outbox_router.py agentforge/platform/application/dashboard_service.py agentforge/platform/infrastructure/memory_audit_repository.py agentforge/platform/infrastructure/sqlalchemy_audit_repository.py agentforge/platform/api/audit_router.py agentforge/platform/domain/reporting.py agentforge/platform/domain/cron.py agentforge/platform/application/report_service.py agentforge/platform/infrastructure/memory_scheduled_report_repository.py agentforge/platform/infrastructure/sqlalchemy_scheduled_report_repository.py agentforge/platform/infrastructure/memory_report_run_repository.py agentforge/platform/infrastructure/sqlalchemy_report_run_repository.py
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
- Connector SDK、通用签名 Webhook Adapter 与 OpenAPI Adapter 已上线（见第 8 节阶段 C 增量 1 记录）；阶段 C 增量 2 已将连接器注册持久化（`ConnectorRepository` + `connector_specs` 表 + Alembic `0009`）并落地了基于 `TicketWritebackService` 的 CRM/工单写回闭环。但写回连接器仍是面向 HTTP/OpenAPI 的通用实现，尚无真实 CRM（Salesforce 等）、工单系统（Zendesk 等）或具体业务数据库的原生适配器，凭据仍只存引用、无真实 vault/密钥后端。
- 已有 RBAC（角色/权限/赋值）、Policy Engine（动作策略/风险/审批要求）、内存态 OpenFGA 式关系检查（阶段 C 增量 3）与高风险动作授权审计闭环 + 人工授权边界（`HighRiskActionAuthorizer` + `POST /v1/authorize` + 写回门禁 403，阶段 C 增量 5）；弹租户配额管理（`TenantQuota` + `/v1/quotas`）与管理控制台聚合概览（`/v1/console/overview`，含配额/成本/DLQ/审计，见第 8 节阶段 C 增量 4 记录）。但仍缺真实 OpenFGA 服务、企业级身份/身份提供方对接、管理员权限矩阵和策略热加载/审计策略变更。
- 配额 enforce 为进程内估算（基于模型元数据 estimated_cost，达到上限后拒绝新调用）；成本估算与 DLQ/审计统计均基于进程内存态仓储/事件，尚无真实 CRM 集成、真实 DB 聚合查询或近实时运营看板。API Key 仍为静态映射（见下）。
- 管理控制台基础页面接口已落地（阶段 D 增量 1：客服工作台 `/v1/console/tickets`、审批收件箱 `/v1/console/inbox`、运营成本总览 `/v1/console/costs`、任务状态计数、DLQ 管理 `/v1/outbox/*`）；阶段 D 增量 2 已落地 Outbox/DLQ/任务状态的列表、详情、计数与丢弃操作（`/v1/outbox/events`、`/events/count`、`/events/{event_id}`、`/events/{event_id}/discard`，同时支持 memory/sqlalchemy 双实现）；阶段 D 增量 3 已落地成本/配额/模型分布/质量指标看板接口（`/v1/console/cost-trend`、`/model-distribution`、`/quality`、`/dashboard`）；阶段 D 增量 4 已落地审计查询（`/v1/audit` 过滤/分页 + `/v1/console/audit` admin 多租户）、租户配置（`/v1/console/tenants`）与连接器管理（`/v1/console/connectors` + `/connectors/{id}/enabled` 启停）；阶段 D 增量 5 已落地运营报表导出与定时化（`/v1/console/reports/export` JSON/CSV 即时导出 + `/reports/schedule`、`/reports/schedules`、`/reports/run-due` 排程，`ScheduledReportRepository` + `scheduled_reports` 表 Alembic `0012`）；阶段 D 增量 6 已落地运营报表产物持久化与历史查询（`/v1/console/reports/runs` 历史列表 + `/reports/runs/{run_id}` 按需取回 JSON/CSV，`ReportRunRepository` + `report_runs` 表 Alembic `0013`）；阶段 D 增量 7 已落地报表 run 保留/清理策略（`/v1/console/reports/runs/prune` 按保留天数清理，`ReportRunRepository.delete_older_than` 双实现）；阶段 D 增量 8 已落地排程保留策略配置持久化与 `run_due` 自动联动清理（`ScheduledReport.retention_days` + `scheduled_reports.retention_days` Alembic `0014`）；阶段 D 增量 9 已落地排程暂停/恢复（`POST /v1/console/reports/schedule/{report_id}/enabled`）与全局默认保留策略（`run_due` 对未显式配置保留的排程按全局默认清理，环境变量 `AGENTFORGE_REPORT_DEFAULT_RETENTION_DAYS`）；阶段 D 增量 10 已落地 cron 表达式排程（`domain/cron.py` 自研 5 段解析器，`cadence` 支持 cron 表达式或 daily/weekly/monthly 标签）。仍缺前端页面实现、审批收件箱决策详情页、成本/质量指标看板可视化与按日/按模型趋势图，以及 `run_due` 异步化（接入 Temporal/worker）。
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
2. CRM、工单系统或业务数据库连接器。⚠️ 已完成（见第 8 节增量完成记录）。
3. RBAC、Policy Engine、OpenFGA 和权限模型。⚠️ 已完成（见第 8 节增量完成记录）。
4. 密钥管理、租户隔离、限流、幂等写回和对账。（租户配额管理与管理控制台聚合概览已部分落地，见第 8 节增量 4 记录；密钥管理/分布式限流/对账仍缺口）
5. 高风险动作审计闭环和人工授权边界。⚠️ 已完成（见第 8 节增量完成记录）。

### 阶段 D：管理控制台与运营

共 4 个增量：

1. 工单列表、详情、审批收件箱和人工编辑界面。（基础接口接口已落地：`/v1/console/tickets`、`/v1/console/inbox`，见第 8 节阶段 D 增量 1 记录；详情/编辑页面与前端待做）
2. Outbox、DLQ、任务状态、重试和故障操作页面。⚠️ 已落地后端接口（`/v1/outbox/events`、`/events/count`、`/events/{event_id}`、`/events/{event_id}/discard`，见第 8 节阶段 D 增量 2 记录；重试沿用 `/v1/outbox/{id}/replay`、`/replay-failed`；前端页面待做）
3. 成本、配额、模型分布和质量指标看板。⚠️ 已落地后端聚合接口（`/v1/console/cost-trend`、`/model-distribution`、`/quality`、`/dashboard`，见第 8 节阶段 D 增量 3 记录；前端可视化待做）
4. 审计查询、租户配置和连接器管理页面。⚠️ 已落地后端接口（`/v1/audit` 过滤/分页、`/v1/console/audit`、`/v1/console/tenants`、`/v1/console/connectors`、`POST /v1/console/connectors/{id}/enabled`，见第 8 节阶段 D 增量 4 记录；前端待做）

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

阶段 A 与阶段 B 已完成（阶段 B 全 4 个增量均已完成，见第 8 节增量完成记录）。阶段 C 全 5 个增量已完成（增量 1 Connector 适配、增量 2 连接器注册持久化 + 工单写回闭环、增量 3 RBAC/Policy/OpenFGA 权限模型、增量 4 租户配额 + 管理控制台概览、增量 5 高风险动作审计闭环 + 人工授权边界）。阶段 D 增量 1（管理控制台基础页面接口）、增量 2（Outbox/DLQ/任务状态维护接口）、增量 3（成本/配额/模型分布/质量指标看板接口）、增量 4（审计查询、租户配置与连接器管理页面接口）与增量 5（运营报表导出与定时化）已完成；后续剩余 2 个建议增量。每个增量应控制在 0.5 到 2 天内可完成、可测试、可提交的范围内。

## 8. 增量完成记录

阶段 A（7 个增量）、阶段 B（4 个增量）、阶段 C（5 个增量）均已完成；阶段 D 增量 1（管理控制台基础页面接口）、增量 2（Outbox/DLQ/任务状态/重试与故障操作接口）、增量 3（成本/配额/模型分布/质量指标看板接口）、增量 4（审计查询、租户配置与连接器管理页面接口）、增量 5（运营报表导出与定时化）、增量 6（运营报表产物持久化与历史查询）、增量 7（报表 run 保留/清理策略）、增量 8（排程保留策略持久化 + `run_due` 自动联动清理）、增量 9（排程暂停/恢复 + 全局默认保留策略）、增量 10（cron 表达式排程）、增量 11（报表 run 归档 + 批量 ZIP 归档导出）、增量 12（归档与保留清理联动）、增量 13（报表管理操作审计日志接入）、增量 14（ZIP 归档导出流式化）与增量 15（报表 run 列表游标分页）已完成。阶段 B 增量 1-4、阶段 C 增量 1-5、阶段 D 增量 1-15 的完成记录如下；下一步进入阶段 D 增量 16（`run_due` 移入 worker 异步化，或剩余管理页面收尾）。

### 阶段 D 增量 4 完成记录（2026-09-18）

- 范围：审计查询、租户配置与连接器管理页面接口（配合管理控制台，供审计查询、租户配额配置与连接器运维页面）。
- 端口：`application/ports.py` `AuditRepository` 新增 `query_events(tenant_id=None, action=None, actor_id=None, resource_id=None, resource_type=None, limit, cursor) -> tuple[list[AuditEvent], str|None]`（过滤 + offset 游标分页；`tenant_id=None` 为 admin-global 多租户查询）。
- 仓储实现：`memory_audit_repository.py` 遍历内存事件按过滤条件筛出并 offset 分页；`sqlalchemy_audit_repository.py` 逐条件 `where` + `.offset(start).limit(limit+1)` 计算 has_more 与 next_cursor。
- 接口：
  - `api/audit_router.py` `/v1/audit` 扩展：`tenant_id` 改为可选（缺省走 `authorize_admin`），新增 `action`/`actor_id`/`resource_type` 过滤与 `cursor` 分页；返回 `{"events", "next_cursor"}`。
  - `api/console_router.py` 新增 admin 管理端点（均经 `_authorize_admin` 鉴权，拆分为 `_authorize_admin(authenticator, request)` helper；`authenticator` 作为新参数注入）：
    - `GET /v1/console/tenants`：admin 多租户配置（quota + used + usage_status + enabled；租户集为 cost 租户 ∪ quota 租户）。
    - `GET /v1/console/audit`：admin 审计查询（action/actor_id/resource_id/resource_type 过滤 + 游标分页），`tenant_id` 可选。
    - `GET /v1/console/connectors`：admin 连接器全量列表（经 connector_repository 持久化 spec）+ 每个连接器经 registry.health 附加健康状态。
    - `POST /v1/console/connectors/{connector_id}/enabled`：启用/停用连接器，经 connector_repository `get_spec`+`save_spec` 持久化（404 兜底）。
- 装配：`app.py` 把 `connector_registry`/`connector_repository`/`authenticator` 注入 console router；`audit_router` 复用 `container.audit_repository` 与 `container.authenticator`。
- 验证：`tests/platform` 170 passed（净 +9）、全仓 636 passed（净 +9）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`，仅 `workflows/support_ticket.py:57` 为阶段 A 存量 Temporal overload）；新增 `tests/platform/test_increment4_admin.py`（9 项：memory 审计过滤/过滤条件/admin-global/游标分页、sqlalchemy 审计过滤/分页、`/v1/audit` 过滤与 admin-global 与分页端到端、`/v1/console/audit` admin 多租户、`/v1/console/tenants` admin 列表、连接器列表与启停 toggle 与 404）。`alembic heads` 仍为 `20260918_0011`（本增量复用 `audit_events`/`connector_specs` 表，无新迁移）。
- 剩余风险：审计 `query_events` 的时间过滤、按风险等级/事件类型过滤暂未提供（如需可按需扩展）；`/v1/console/connectors` 的健康状态依赖 registry 中已绑定 adapter，持久化 spec 但进程重启后 registry adapter 重建（health 可能为空）；admin 管理端点鉴权依赖 admin key，无独立操作者级 RBAC 细分；真实 PostgreSQL 上的多租户审计聚合查询未在 Docker 端到端跑通。
- 下一步：阶段 D 增量 5（运营报表导出与定时化、或剩余管理页面收尾）。

### 阶段 D 增量 5 完成记录（2026-09-18）

- 范围：运营报表导出与定时化——把成本/审计/质量聚合为行式报表（JSON/CSV）即时导出，并支持按 cadence（daily/weekly/monthly）定时生成。
- 领域模型：新增 `domain/reporting.py`（`ReportType` cost/audit/quality、`ReportFormat` json/csv、`OperationsReport` 含 rows/summary/generated_at/to_json()/to_csv()、`ScheduledReport` 含 report_id/tenant_id/report_type/cadence/enabled/last_run_at/next_run_at 及各字段默认值）。
- 端口：`application/ports.py` 新增 `ScheduledReportRepository` Protocol（`save`/`get`/`list_schedules`/`delete`/`list_due`）。方法命名 `list_schedules`（而非 `list`）避免类内 `list` 方法遮蔽内建 `list` 类型触发 mypy valid-type 报错。
- 仓储实现（memory + sqlalchemy 双实现）：
  - `memory_scheduled_report_repository.py`：内存 dict，`list_due` 过滤 `enabled and next_run_at <= before`。
  - `sqlalchemy_scheduled_report_repository.py`：`scheduled_reports` 表对应 `ScheduledReportRecord`（`models.py` 新增 `from_domain`/`to_domain`，时区缺失自动补 UTC）`merge` upsert、`list_due` 走 `where(enabled.is_(True)).where(next_run_at <= now)`。
- 迁移：`alembic/versions/20260918_0012_scheduled_reports.py`（down_revision=`20260918_0011`）建 `scheduled_reports` 表（report_id PK / tenant_id idx / report_type / cadence / enabled / created_at / last_run_at nullable / next_run_at）。`alembic heads` 推进到 `20260918_0012`。
- 应用：新增 `application/report_service.py` `ReportService(cost_repository, audit_repository, regression_repository, schedule_repository)`：
  - `generate(type, tenant_id, fmt, days)`：聚合成本（daily_summary 行）、审计（query_events 行）、质量（regression list_runs 行）为行式报表，支持 JSON/CSV 序列化。
  - `schedule`/`list_schedules`/`delete_schedule`：排程 CRUD。
  - `run_due()`：`list_due` 取出到期排程逐一 `generate`，写 `last_run_at` 并推进 `next_run_at`（daily +1d / weekly +7d / monthly +30d），幂等（已推进则不会重复生成）。
- 接口（`api/console_router.py`，均经 `_authorize_admin` 鉴权）：
  - `GET /v1/console/reports/export?report_type&tenant_id&format=json&days`：即时导出，JSON 返回 `application/json`，CSV 返回 `text/csv` + `Content-Disposition`。
  - `POST /v1/console/reports/schedule`：创建排程（body: tenant_id/report_type/cadence）。
  - `GET /v1/console/reports/schedules?tenant_id`：排程列表。
  - `DELETE /v1/console/reports/schedule/{report_id}`：删除排程。
  - `POST /v1/console/reports/run-due`：跑到期排程。
- 装配：`runtime.py` `ServiceContainer` 新增 `scheduled_report_repository`（缺省 memory）与 `report_service`，两个 builder（memory/sqlalchemy）均注入相应仓储；`app.py` 把 `container.report_service` 注入 console router。
- 验证：`tests/platform` 181 passed（净 +11）、全仓 647 passed（净 +11）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）；新增 `tests/platform/test_reports.py`（11 项：memory 排程仓储 CRUD/到期、sqlalchemy 排程仓储 CRUD/到期、ReportService JSON/CSV 成本、审计报表、调度+run_due 幂等、导出 JSON/CSV/非法类型、排程生命周期列表过滤、run-due 端点、删除排程）。`alembic heads` 为 `20260918_0012`。
- 剩余风险：`run_due` 为同步执行（调用触发器逐条生成），未接入 Temporal/worker 异步任务；无排程产物落盘/历史归档（只返回运行摘要）；cadence 用简化标签（daily/weekly/monthly 固定步长），未支持 cron 表达式；真实 PostgreSQL 上定时生成与到期检测未在 Docker 端到端跑通。
- 下一步：阶段 D 增量 6（运营报表产物持久化/历史查询、cron 表达式排程，或剩余管理页面收尾）。

### 阶段 D 增量 6 完成记录（2026-09-18）

- 范围：运营报表产物持久化与历史查询——把每次生成的报表（rows+summary+format）落盘为不可变 run，提供历史列表与按需取回（JSON/CSV）接口，使排程/导出产物可追溯复用，无需重新聚合。
- 领域模型：`domain/reporting.py` 新增 `ReportRun`（run_id/tenant_id/report_type/format/rows/summary/generated_at/scheduled_report_id，含 `from_operations()`、`to_json()`/`to_csv()`），作为 `OperationsReport` 的持久化快照。
- 端口：`application/ports.py` 新增 `ReportRunRepository` Protocol（`save`/`get`/`list(tenant_id?, report_type?, limit)`）。
- 仓储实现（memory + sqlalchemy 双实现，遵循既有 Protocol 模式）：
  - `memory_report_run_repository.py`：内存 dict，`list` 按 `generated_at` 倒序。
  - `sqlalchemy_report_run_repository.py`：`report_runs` 表对应 `ReportRunRecord`（`models.py` 新增 `from_domain`/`to_domain`，时区缺失自动补 UTC），`list` 走 `where` 过滤 + `order_by(generated_at.desc())`。
- 迁移：`alembic/versions/20260918_0013_report_runs.py`（down_revision=`20260918_0012`）建 `report_runs` 表（run_id PK / tenant_id / report_type / format / rows JSONB / summary JSONB / scheduled_report_id nullable / generated_at，含 4 个索引）。`alembic heads` 推进到 `20260918_0013`。
- 应用：`application/report_service.py` `ReportService` 构造参数新增 `run_repository`；`generate()` 完成后经 `_persist()` 把产物落为 `ReportRun`；新增 `list_runs(tenant_id?, report_type?, limit)`（返回元信息）与 `get_run(run_id)`（含 `to_json()`/`to_csv()`）。
- 接口（`api/console_router.py`，均经 `_authorize_admin` 鉴权）：
  - `GET /v1/console/reports/runs?tenant_id&report_type&limit`：历史报表列表（最新在前）。
  - `GET /v1/console/reports/runs/{run_id}?format=json`：取回单次产物，JSON 返回 `application/json`、CSV 返回 `text/csv` + `Content-Disposition`；run 不存在返回 404。
- 装配：`runtime.py` `ServiceContainer` 新增 `run_repository`（缺省 memory `MemoryReportRunRepository`）并注入 `report_service`；memory builder 用 `MemoryReportRunRepository`、sqlalchemy builder 用 `SQLAlchemyReportRunRepository(session_factory)`。
- 验证：`tests/platform` 186 passed（净 +5）、全仓 652 passed（净 +5）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）；新增 5 项到 `tests/platform/test_reports.py`（memory run 仓储 CRUD/列表、sqlalchemy run 仓储 CRUD/列表、ReportService 落盘+历史列表、`/reports/runs` 历史与按需取回 JSON/CSV、`/reports/runs` 过滤与 404）。`alembic heads` 为 `20260918_0013`。
- 剩余风险：`run_due` 仍为同步执行，未接入 Temporal/worker 异步任务；排程 run 无清理/保留策略（run 不断累积）；cadence 仍为简化标签（daily/weekly/monthly），未支持 cron 表达式；真实 PostgreSQL 上 `report_runs` 写入与历史查询未在 Docker 端到端跑通。
- 下一步：阶段 D 增量 7（cron 表达式排程、run 保留/清理策略，或剩余管理页面收尾）。

### 阶段 D 增量 7 完成记录（2026-09-18）

- 范围：报表 run 保留/清理策略——提供按保留天数清理历史报表 run 的能力，避免持久化 run 无限累积；支持全局或按租户清理。
- 端口：`application/ports.py` `ReportRunRepository` Protocol 新增 `delete_older_than(cutoff, tenant_id=None) -> int`（删除 `generated_at < cutoff` 的 run，`tenant_id` 可选则全局清理）。
- 仓储实现（memory + sqlalchemy 双实现）：
  - `memory_report_run_repository.py`：过滤 `generated_at < cutoff`（可按 tenant）后从内存 dict 移除，返回删除数。
  - `sqlalchemy_report_run_repository.py`：先 `select(run_id)` 统计匹配行，再按同条件 `delete`，`commit` 后返回删除行数（避免依赖 `CursorResult.rowcount` 类型）。
- 应用：`application/report_service.py` `ReportService` 新增 `prune_runs(retention_days, tenant_id=None)`，计算 `cutoff = now - retention_days` 调用 `delete_older_than`，返回 `{retention_days, cutoff, tenant_id, removed}` 摘要。
- 接口（`api/console_router.py`，`_authorize_admin` 鉴权）：`POST /v1/console/reports/runs/prune`（body: `retention_days` 默认 30、`tenant_id` 可选）。
- 验证：`tests/platform` 190 passed（净 +4）、全仓 656 passed（净 +4）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）；新增 4 项到 `tests/platform/test_reports.py`（memory `delete_older_than` 全局/按租户、sqlalchemy `delete_older_than`、`ReportService.prune_runs`、`/reports/runs/prune` 端到端）。本增量无 schema 变更，`alembic heads` 保持 `20260918_0013`。
- 剩余风险：`run_due` 仍为同步执行，未接入 Temporal/worker 异步任务；cadence 仍为简化标签（daily/weekly/monthly），未支持 cron 表达式；保留策略是显式按需清理（未与运行频次自动联动、无保留策略配置持久化）；真实 PostgreSQL 上清理删除未在 Docker 端到端跑通。
- 下一步：阶段 D 增量 8（cron 表达式排程、保留策略配置持久化，或剩余管理页面收尾）。

### 阶段 D 增量 8 完成记录（2026-09-18）

- 范围：排程保留策略配置持久化 + `run_due` 自动联动清理——为每个排程配置 `retention_days` 并持久化，运行到期排程后按策略自动清理该租户过期报表 run，避免历史 run 无限累积。
- 领域模型：`domain/reporting.py` `ScheduledReport` 新增 `retention_days: int | None = None`（None 表示该排程生成后不自动清理）。
- ORM/迁移：`models.py` `ScheduledReportRecord` 新增 `retention_days` 列（`Integer` nullable），补 `from_domain`/`to_domain` 双向映射；`alembic/versions/20260918_0014_scheduled_report_retention.py`（down_revision=`20260918_0013`）`op.add_column`（downgrade `op.drop_column`）。`alembic heads` 推进到 `20260918_0014`。
- 应用：`application/report_service.py`：
  - `schedule(..., retention_days=None)` 接受并持久化保留策略。
  - `run_due()` 对到期排程生成后，按该排程 `retention_days` 调用 `prune_runs` 清理该租户过期 run（同租户多排程取最严格/最小 retention；返回新增 `pruned` 计数字段）。
- 接口：`api/console_router.py` `POST /v1/console/reports/schedule` body 支持 `retention_days`（非法值返回 400）。
- 验证：`tests/platform` 194 passed（净 +4）、全仓 660 passed（净 +4）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）；新增 4 项到 `tests/platform/test_reports.py`（memory/sqlalchemy 排程仓库 `retention_days` 持久化往返、`ReportService.run_due` 按保留策略自动清理旧 run、`/reports/schedule` 支持保留天数与非法值 400）。`alembic heads` 为 `20260918_0014`。
- 剩余风险：`run_due` 仍为同步执行，未接入 Temporal/worker 异步任务；cadence 仍为简化标签，未支持 cron 表达式；保留策略已随排程持久化但无全局默认值配置（未设置 `retention_days` 的排程不自动清理）；真实 PostgreSQL 上 `scheduled_reports.retention_days` 加列迁移与自动清理未在 Docker 端到端跑通。
- 下一步：阶段 D 增量 9（cron 表达式排程、全局保留策略默认值，或剩余管理页面收尾）。

### 阶段 D 增量 9 完成记录（2026-09-18）

- 范围：排程暂停/恢复开关 + 全局默认保留策略——为排程管理补齐「暂停而不删除」能力，并为未显式设置 `retention_days` 的到期排程提供平台级默认保留窗口，让 `run_due` 自动清理对所有排程兜底，杜绝历史 run 无限累积。
- 应用：`application/report_service.py`：
  - `ReportService.__init__` 新增 `default_retention_days: int | None = None` 构造注入。
  - `run_due(fmt=..., default_retention_days=None)` 对每个到期排程先取显式 `retention_days`，为空则回退到本次调用覆盖值或服务级全局默认；同租户多排程仍取最严格（最小）保留。
  - 新增 `set_schedule_enabled(report_id, enabled)`——复用 `get`+`save` 切换 `enabled`（memory/sqlalchemy 双实现均支持；`list_due` 已按 `enabled` 过滤，暂停后不再生成 run，但配置保留）。缺失排程抛 `KeyError`。
- 接口：`api/console_router.py` 新增 `POST /v1/console/reports/schedule/{report_id}/enabled`（body `{"enabled": bool}`，缺失排程 404）；`POST /v1/console/reports/run-due` 支持 body `{"default_retention_days": N}`（非法值 400）。
- 装配：`runtime.py` `ServiceContainer` 新增 `default_report_retention_days` 注入；`build_memory_container`/`build_sqlalchemy_container` 从环境变量 `AGENTFORGE_REPORT_DEFAULT_RETENTION_DAYS` 读取全局默认保留天数（缺失/非法则关闭兜底）。
- 验证：`tests/platform` 199 passed（净 +5）、全仓 665 passed（净 +5）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）；新增 5 项到 `tests/platform/test_reports.py`（memory 排程暂停/恢复且暂停不再入 `list_due`、缺失排程暂停抛 `KeyError`、`run_due` 全局默认保留清理旧 run、`/reports/schedule/{id}/enabled` 端点启停与 404、`/reports/run-due` 默认保留天数覆盖与非法值 400）。`alembic heads` 保持 `20260918_0014`（本增量无 schema 变更）。
- 剩余风险：`run_due` 仍为同步执行，未接入 Temporal/worker 异步任务；cadence 仍为简化标签，未支持 cron 表达式；全局默认保留策略仅在创建时未显式设置 `retention_days` 的排程上生效（不覆盖已显式配置的排程），且依赖环境变量注入；真实 PostgreSQL 上自动清理未在 Docker 端到端跑通。
- 下一步：阶段 D 增量 10（cron 表达式排程、报表产物归档/导出下载页收尾，或剩余管理页面收尾）。

### 阶段 D 增量 10 完成记录（2026-09-18）

- 范围：cron 表达式排程——让报表排程的 cadence 支持标准 5 段 cron 表达式（如 `0 2 * * *`、`*/15 * * * *`），同时保持简化标签（daily/weekly/monthly）兼容；`run_due` 按 cron 计算准确的 next_run，替代原来的固定标签推进。
- 领域：新增 `agentforge/platform/domain/cron.py`：
  - `CronField.parse` 支持 `*`、`*/step`、`a-b`、`a,b`、单值，非法值（越界/空/步进非正）抛 `CronExpressionError`。
  - `CronSchedule` 解析 5 字段（minute/hour/day-of-month/month/day-of-week），day-of-week 0-7（0 和 7 均为周日）；当日与周字段同时受限时按经典 cron OR 规则匹配，仅一方受限时按该方匹配；`matches(dt)` 判断给定时刻是否命中，`next_after(dt)` 带 5 年有界前向扫描返回严格晚于 dt 的下一次命中。
  - `is_cron_cadence(cadence)` 判断字符串是否形如 5 段 cron 表达式。
- 应用：`application/report_service.py` `_advance_next_run(cadence, last_run)`（取代原 `_next_run_for`）——若 cadence 为 cron 表达式则用 `CronSchedule.next_run_from` 计算下一次命中，否则沿用 daily/weekly/monthly 标签推进；`run_due` 调用处同步更新。
- 接口：`api/console_router.py` `POST /v1/console/reports/schedule` 校验 cadence：cron 表达式非法（解析失败）返回 400，非 daily/weekly/monthly 且非 cron 的标签也返回 400。
- 验证：`tests/platform` 206 passed（净 +7）、全仓 680 passed（净 +7；一次全仓 run 出现 1 个既有 circuit_breaker 计时类偶发失败，重跑通过，属 pre-existing flaky）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）；新增 7 项到 `tests/platform/test_reports.py`（cron 解析与 next、非法表达式、`is_cron_cadence`、service 用 cron cadence 推进 next_run、`/reports/schedule` cron cadence 接受与非法 400、工作日受限与 OR 规则语义）。`alembic heads` 保持 `20260918_0014`（本增量无 schema 变更，`cadence` 字段已是 str）。
- 剩余风险：`run_due` 仍为同步执行，未接入 Temporal/worker 异步任务；cron 计算为自研轻量实现（未被第三方 cron 库交叉验证，5 年有界扫描）；未支持秒级/年字段（`@reboot` 等宏未实现）；真实 PostgreSQL 上排程运行未在 Docker 端到端跑通。
- 下一步：阶段 D 增量 12（`run_due` 移入 worker 异步化、归档与保留联动，或剩余管理页面收尾）。

### 阶段 D 增量 11 完成记录（2026-09-18）

- 范围：报表产物归档状态 + 批量 ZIP 归档导出——为持久化的报表 run 增加 `archived` 标记（可从默认活跃列表隐藏/恢复），并提供把多个 run 打包为 ZIP 的归档导出能力，完善运营报表生命周期管理。
- 领域：`domain/reporting.py` `ReportRun` 增加 `archived: bool = False`（默认非归档）。
- 持久化：`infrastructure/db/models.py` `ReportRunRecord` 增加 `archived` 列（`Boolean`, nullable=False, default False）+ `from_domain`/`to_domain` 映射；新增 `alembic/versions/20260918_0015_report_run_archive.py` 加列迁移（0014 -> 0015）。
- 端口：`application/ports.py` `ReportRunRepository` 增加 `set_archived(run_id, archived)`，`list` 增加 `archived: bool | None` 过滤参数。
- 仓储：`memory_report_run_repository.py` 直接更新内存记录；`sqlalchemy_report_run_repository.py` 以 UPDATE 语句切换 archived 位、`list` 按 archived 过滤（沿用 select + scalars 模式）。
- 应用：`application/report_service.py` `list_runs` 支持 `archived` 过滤；新增 `archive_run(run_id, archived)`（缺失抛 `KeyError`）与 `export_archive(tenant_id, limit) -> (bytes, info)`，用 `zipfile`（标准库，无新依赖）把每个 run 按其原生格式（json/csv）写入 `run_{run_id}.{ext}` 并返回 ZIP 字节 + ArchiveInfo 清单。
- 接口：`api/console_router.py` `POST /v1/console/reports/runs/{run_id}/archive`（body `{"archived": bool}`，缺失 404）、`GET /v1/console/reports/runs` 增加 `archived` 过滤参数、`GET /v1/console/reports/runs/archive` 返回 `application/zip`；`/runs/archive` 字面路径注册在 `/{run_id}` 之前避免路径抢占。
- 验证：`tests/platform` 210 passed（净 +4）、全仓 680 passed（净 +4）、Black/isort/Flake8 通过、7 个相关源文件 mypy 通过（`Success: no issues found`）；新增 4 项到 `tests/platform/test_reports.py`（service archive_run 归档/恢复/缺失、export_archive 的 ZIP 内容与清单、内存/sqlalchemy 仓储 set_archived 与 list 过滤、`/reports/runs/{id}/archive` 与 `/reports/runs/archive` 端点）。
- alembic head 现在为 `20260918_0015`。
- 剩余风险：`/reports/runs/archive` 一次性打包到内存（大数据量 run 需流式/对象存储）；`run_due` 仍同步；归档仅为标记，未与保留清理（prune）联动（已归档 run 仍会按 retention 被清理）；真实 PostgreSQL 端到端未验证。
- 下一步：阶段 D 增量 12（`run_due` 移入 worker 异步化、归档与保留联动、或剩余管理页面收尾）。
### 阶段 D 增量 12 完成记录（2026-09-18）

- 范围：归档与保留清理联动——保留策略清理（prune / `run_due` 自动清理）默认跳过已归档的报表 run，使"归档"真正成为合规长期保留的保护；同时暴露 `include_archived=True` 显式强制清理已归档 run 的选项。
- 端口：`application/ports.py` `ReportRunRepository.delete_older_than` 增加 `include_archived: bool = False` 参数，默认 False（仅删未归档）。
- 仓储：`memory_report_run_repository.py` 过滤 `(include_archived or not r.archived)`；`sqlalchemy_report_run_repository.py` 在 select_ids 与 DELETE 语句上对 `not include_archived` 追加 `ReportRunRecord.archived.is_(False)`（沿用 count-then-delete 模式）。
- 应用：`application/report_service.py` `prune_runs(retention_days, tenant_id=None, include_archived=False)` 透传参数并在返回中带 `include_archived`；`run_due` 内部调用的自动清理不传该参数，从而默认保护已归档 run。
- 接口：`api/console_router.py` `POST /v1/console/reports/runs/prune` 支持 body `include_archived`（bool，默认 False）。
- 验证：`tests/platform` 214 passed（净 +4）、全仓 680 passed（净 +4）、Black/isort/Flake8 通过、5 个相关源文件 mypy 通过（`Success: no issues found`）；新增 4 项到 `tests/platform/test_reports.py`：默认 prune 跳过已归档 run 且在强 `include_archived` 下删除、memory 仓储默认/强制清理行为、sqlalchemy 仓储默认/强制清理行为、`/reports/runs/prune` 端点默认保留与强制清理。
- alembic head 保持为 `20260918_0015`（本增量无 schema 变更）。
- 剩余风险：已归档 run 与保留清理解耦完成，但不影响显式 `include_archived` 手动兜底清理；`run_due` 仍同步；真实 PostgreSQL 端到端未验证。
- 下一步：阶段 D 增量 13（`run_due` 移入 worker 异步化、或剩余管理页面收尾）。

### 阶段 D 增量 13 完成记录（2026-09-18）

- 范围：报表关键管理操作审计日志接入——为报表模块的变更型管理操作（生成、排程创建/删除/启停、run 归档/恢复、run 清理、归档导出、run_due 批量执行）统一写入审计事件，满足横切审计与合规追溯需求（纯后端、可独立闭环；`run_due` 异步化需外部 worker，前端管理页超出后端范围，均不在本增量）。
- 应用：`application/report_service.py` 新增私有辅助 `_record_audit(tenant_id, action, resource_type="report", resource_id="", risk_level=RiskLevel.LOW, payload=None)`，复用 `AuditEvent`/`RiskLevel`，统一 `actor_type="admin"`/`actor_id="console"`（对 `self._audit` 为 None 时静默跳过，保持无审计仓储可装配）。
- 接入点（action 分类）：
  - `generate` → `report.generate`（payload: report_type/format/rows/scheduled_report_id）
  - `schedule` → `report.schedule.create`（payload: report_type/cadence/retention_days；resource_id=report_id）
  - `delete_schedule` → `report.schedule.delete`（resource_id=report_id；先取 sched 以得 tenant_id，缺失则 "system"）
  - `set_schedule_enabled` → `report.schedule.enable` / `report.schedule.disable`（payload: enabled）
  - `archive_run` → `report.run.archive` / `report.run.unarchive`（payload: archived）
  - `prune_runs` → `report.runs.prune`（RiskLevel.MEDIUM；payload: retention_days/cutoff/include_archived/removed）
  - `export_archive` → `report.archive.export`（payload: count/tenant_id/limit）
  - `run_due` → `report.run_due`（tenant_id=None 汇总；payload: generated/pruned）
- 验证：`tests/platform` 221 passed（净 +7）、全仓 687 passed（净 +7）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）；新增 8 项到 `tests/platform/test_reports.py`：schedule 创建/删除/启停、generate、archive/unarchive、prune、run_due 写审计及 action 分类与 payload/risk_level/actor 断言。
- alembic head 保持为 `20260918_0015`（本增量无 schema 变更）。
- 剩余风险：`run_due` 仍同步；报表 ZIP 导出一次性加载到内存；审计事件真实性依赖审计仓储装配（服务层对 None 静默跳过）；真实 PostgreSQL 端到端未验证。
- 下一步：阶段 D 增量 14（`run_due` 移入 worker 异步化、或剩余管理页面收尾）。


### 阶段 D 增量 14 完成记录（2026-09-18）

- 范围：报表 ZIP 归档导出流式化——把报表 run 打包 ZIP 归档由"整包 bytes 缓冲到内存后一次性返回"改为"写入临时文件后经 `StreamingResponse` 分块流式下发"，消除大归档常驻内存的剩余风险（纯后端、可独立闭环）。
- 应用：`application/report_service.py` 把原 `export_archive` 的 ZIP 构建逻辑抽取为私有 `_write_archive(sink, tenant_id, limit)`，写入任意可写二进制 sink 并返回 ArchiveInfo JSON：
  - `export_archive(...)`：兼容包装，写入 `io.BytesIO` 并返回 `(bytes, info)`（保留既有调用与测试）。
  - 新增 `export_archive_to(sink, tenant_id, limit)`：将 ZIP 增量写入调用方提供的 sink（如临时文件），返回 info——供流式路径使用，整包不驻留内存。
- 接口：`api/console_router.py` `GET /v1/console/reports/runs/archive` 改为 `tempfile.mkstemp` 落盘 → `report_service.export_archive_to(sink, ...)` → 用 `StreamingResponse` 以 64KiB 分块回读下发，`_iter_zip` 生成器 `finally` 中删除临时文件；新增 imports `os/tempfile/Iterator/StreamingResponse`。Content-Type 仍为 application/zip，Content-Disposition 保持 attachment。
- 验证：`tests/platform` 223 passed（净 +2）、全仓 689 passed（净 +2）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）；新增 2 项到 `tests/platform/test_reports.py`（`export_archive_to` 写入磁盘后 ZIP 内文件数与格式有效、`/reports/runs/archive` 端点流式返回可解压 JSON/CSV 且 content-type/disposition 正确）。
- alembic head 保持为 `20260918_0015`（本增量无 schema 变更）。
- 剩余风险：`run_due` 仍同步（未接 worker）；流式路径依赖临时文件落盘（磁盘 I/O 与生命周期由路由器管理，异常时 `finally` 清理）；真实 PostgreSQL 端到端未验证。
- 下一步：阶段 D 增量 15（`run_due` 移入 worker 异步化、或剩余管理页面收尾）。


### 阶段 D 增量 15 完成记录（2026-09-18）

- 范围：报表 run 列表游标分页——为管理控制台报表 run 列表增加 cursor 分页，贴合既有的 cursor 分页模式（类 ticket/audit 的 `(items, next_cursor)`），支持大历史集合分批遍历（纯后端、可独立闭环）。
- 端口：`application/ports.py` `ReportRunRepository` 新增 `list_page(tenant_id, report_type, limit, archived, cursor) -> tuple[list[ReportRun], str | None]`（`list` 保持兼容返回 `list[ReportRun]`）。
- 仓储：
  - `memory_report_run_repository.py`：`list_page` 复用 `list` 的过滤/排序（`generated_at desc`），按 offset（`int(cursor)`）切片，返回 `(bucket, next_cursor)`。
  - `sqlalchemy_report_run_repository.py`：`list_page` 复用 `list` 的过滤与排序，`offset(start).limit(limit+1)` 探测是否有下一页（limit+1 技巧），返回 `(page, next_cursor)`。
  - 两文件与 ports 均显式 `import builtins`，用 `builtins.list[...]` 规避 mypy 陷阱（`list_page` 定义在 `list` 方法之后，裸 `list` 注解会被解析成方法而非内建类型）。
- 应用：`application/report_service.py` 新增 `list_runs_paginated(...) -> tuple[list[dict], str | None]`（透传 cursor，复用 `_run_meta`；`list_runs` 保留向后兼容）。
- 接口：`api/console_router.py` `GET /v1/console/reports/runs` 新增 `cursor` 查询参数，返回 `{"runs": [...], "next_cursor": ...}`。
- 验证：`tests/platform` 227 passed（净 +4）、全仓 693 passed（净 +4）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）；新增 4 项到 `tests/platform/test_reports.py`（memory `list_page` 2/2/1 不重叠、sqlalchemy `list_page` 3/2、service `list_runs_paginated`、`/reports/runs` 端点 cursor 遍历且两页无重叠）。
- alembic head 保持为 `20260918_0015`（本增量无 schema 变更）。
- 剩余风险：`run_due` 仍同步（未接 worker）；游标为 offset 语义（非 keyset，服务端无"页间数据增删导致偏移漂移"的加固）；真实 PostgreSQL 端到端未验证。
- 下一步：阶段 D 增量 16（`run_due` 移入 worker 异步化、或剩余管理页面收尾）。

### 阶段 D 增量 3 完成记录（2026-09-18）

- 范围：成本/配额/模型分布/质量指标看板接口（配合管理控制台，供运营看板聚合数据）。
- 端口：`application/ports.py` `CostRepository` 新增 `daily_summary(tenant_id, days) -> list[dict]`（按天聚合 request_count/input_tokens/output_tokens/amount，按日期升序，跳过超出 days 窗口与跨租户记录）。
- 仓储实现：`memory_cost_repository.py` 直接遍历记录按 `created_at.date()` 分桶；`sqlalchemy_cost_repository.py` 按窗口查询后 Python 分桶（避免跨方言日期函数差异）。
- 应用：新增 `application/dashboard_service.py` `DashboardService(cost_repository, quota_repository, regression_repository)`，只读聚合方法：
  - `cost_trend(tenant_id, days)`：日趋势 + days/total_amount/total_requests 汇总。
  - `model_distribution(tenant_id)`：按模型聚合（复用 summary 的 by_model），按 cost 降序并补充 `share`（模型金额占比）。
  - `quota_snapshot(tenant_id)`：配额配置 + 用量 + usage_status（configured 与否）。
  - `quality_metrics(tenant_id, limit)`：回归 run 序列（run_id/candidate/status/verdict/recall/citation/classification/priority/structured/high_risk_miss）+ recent + 平均指标（averages）。
- 接口（`api/console_router.py`）新增（tenant 维度，service 未装配时 503）：
  - `GET /v1/console/cost-trend?tenant_id=&days=`（days 夹紧 1-365）。
  - `GET /v1/console/model-distribution?tenant_id=`。
  - `GET /v1/console/quality?tenant_id=&limit=`。
  - `GET /v1/console/dashboard?tenant_id=`（聚合 cost_trend/model_distribution/quota/quality 四块）。
- 装配：`runtime.py` `ServiceContainer` 新增 `dashboard_service`；`build_memory_container`/`build_sqlalchemy_container` 自动装配（复用 cost/quota/regression 仓储）；`app.py` 把 `container.dashboard_service` 注入 console router。
- 验证：`tests/platform` 161 passed（净 +4）、全仓 627 passed（净 +4）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`，仅 `workflows/support_ticket.py:57` 为阶段 A 存量 Temporal overload 错误非本增量）；新增 `tests/platform/test_dashboard.py`（4 项：memory 日趋势分桶/过滤、DashboardService 四块聚合、sqlalchemy 日趋势、内存端点）。`alembic heads` 仍为 `20260918_0011`（本增量复用 `cost_records`/`regression_runs` 表，无新迁移）。
- 剩余风险：成本/质量统计基于进程内存态仓储/记录，费用于管理看板为历史快照非近实时；`daily_summary` 为 Python 分桶（非 DB 原生 date_trunc），大数据量下应改为 SQL 按日聚合；质量指标仅来自回归 run（未含线上抽样 Recall/置信度）；真实 PostgreSQL 端到端看板查询未在 Docker 跑通。
- 下一步：阶段 D 增量 5（运营报表导出与定时化，或剩余管理页面收尾）。

### 阶段 D 增量 2 完成记录（2026-09-18）

- 范围：Outbox/DLQ/任务状态的列表、详情、计数与丢弃维护接口（配合既有 replay/replay-failed 重试能力，支撑 DLQ 管理与故障操作页面）。
- 仓储扩展（`infrastructure/outbox_store.py` `SQLAlchemyOutboxStore`）：
  - `list_events(tenant_id=None, status=None, limit, cursor)`：按租户/状态过滤、`created_at` 升序、`limit+1` 判断 has_more 的游标分页。
  - `get_event(tenant_id|None, event_id)`：按主键取详情，`tenant_id=None` 为 admin-global。
  - `count_events(tenant_id=None)`：按状态分组计数，返回 pending/published/failed/discarded 四态。
  - `discard(tenant_id|None, event_id)`：把事件置为 `status="discarded"`（补 `last_error="discarded by operator"`）。
- 双实现（新增 `infrastructure/memory_outbox_store.py`）：`MemoryOutboxStore` 提供与 SQLAlchemy 相同的 outbox 管理表面（enqueue/fetch_pending/mark_published/mark_failed/list_failed/list_events/get_event/count_events/discard/replay），使本地/无库运行也可用虚拟机故障操作。
- 接口（`api/outbox_router.py`）新增（均为 admin 鉴权）：
  - `GET /v1/outbox/events`：状态过滤 + limit/cursor 分页列事件。
  - `GET /v1/outbox/events/count`：四态计数。
  - `GET /v1/outbox/events/{event_id}`：事件详情。
  - `POST /v1/outbox/events/{event_id}/discard`：置为 discarded。
  - 保留 `/v1/outbox/failed`、`/v1/outbox/{id}/replay`、`/v1/outbox/replay-failed` 重试能力。
  - 关键点：admin-global 的 detail/discard 必须传 `tenant_id=None`（store 中 `tenant_id is not None` 视为租户过滤；传 `""` 会被当成租户 ID 导致匹配失败返回 404）。
- 装配：`runtime.py` `build_memory_container` 装配 `MemoryOutboxStore()` 作 `outbox_store`，使内存容器也具备 outbox 管理表面。
- 测试：`tests/platform` 157 passed（净 +4）、全仓 623 passed（净 +4）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（仅 `workflows/support_ticket.py:57` 为阶段 A 存量 Temporal overload 错误，非本增量）；新增 `tests/platform/test_outbox_operations.py`（SQLAlchemy list/detail/discard/count + Memory store surface + 双容器 admin 端点）；`test_api_auth.py` 中"tenant 访问 outbox 401、admin 访问 200"断言随内存容器装配 `outbox_store` 从 503（未配置）调整为 200（已配置）。
- 本增量无新增库表、无 Alembic 变更（discard 复用 `status` 字段，`discarded` 为既有枚举外的操作态字符串）。
- 剩余风险：`discarded` 状态仅为操作标记，未被消费者/重放器排除（需在 worker/publisher 索引时显式跳过 `discarded`）；真实 PostgreSQL 端到端 outbox 操作未在 Docker 跑通；replay 与 discard 未做并发（乐观锁）；admin-global 访问依赖 `authorize_admin`，无独立 per-tenant operator 权限面。
- 下一步：阶段 D 增量 5（运营报表导出与定时化，或剩余管理页面收尾）。

### 阶段 D 增量 1 完成记录（2026-09-18）

- 范围：管理控制台基础页面接口（客服工作台、审批收件箱、任务状态计数、运营成本/配额总览、DLQ），驱动阶段 D 页面。
- 领域/端口：`application/ports.py` 的 `TicketRepository` 新增 `list(tenant_id, status, limit, cursor) -> tuple[list[Ticket], str|None]`；`CostRepository` 新增 `list_tenants()`。
- 仓储实现：`memory_ticket_repository.py` 与 `sqlalchemy_ticket_repository.py` 实现 `list`（按状态过滤、`created_at` 升序、游标分页，SQLAlchemy 用 `offset/limit+1` 判断 has_more）；`memory_cost_repository.py` 与 `sqlalchemy_cost_repository.py` 实现 `list_tenants`（`.distinct()` 租户）。
- 接口（`api/console_router.py`）：
  - `GET /v1/console/tickets` 客服工作台：按 `status` 过滤、`limit`/`cursor` 分页列工单（含状态/优先级/意图/风险级/置信度/时间）。
  - `GET /v1/console/inbox` 审批收件箱：列 `waiting_approval` 待审批工单（带风险级），供审批动作（`approve`/`reject` 沿用 `/v1/tickets/{id}/approve`）支撑。
  - `GET /v1/console/overview` 增加 `tasks` 任务状态计数（遍历 9 种状态计数，租户隔离）。
  - `GET /v1/console/costs` 管理员多租户成本/配额总览：并集 cost 租户 + quota 租户，逐租户用量/配额状态，`total_cost` 全量聚合。
  - DLQ 沿用现有 `/v1/outbox/failed`、`/v1/outbox/{id}/replay`。
- 装配：`api/app.py` 向 `create_console_router` 传入 `ticket_repository = container.repository`。
- 验证：`tests/platform` 153 passed（净 +7）、全仓 619 passed（净 +7）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（0 error）；新增 `test_console_tickets.py`（端点 + 游标分页 + 租户隔离）与 `test_sqlalchemy_console_list.py`（SQLAlchemy `list` 过滤/分页 + `list_tenants`）。
- 本增量无新增库表，无 Alembic 变更（复用 `tickets`/`costs` 表）。
- 剩余风险：`_list_tenant_ids` 依赖 `cost_repository.list_tenants()` 与 `quota_repository.list()`；`TicketRepository.list` 为内存/SQLite 验证，真实 PostgreSQL 未端到端跑通；`/v1/console/costs` 与多租户接口当前未在 app 层做管理员鉴权（`_IncludedRouter` 惰性注册条件下构造无异常，鉴权由各端点/外层负责）。
- 下一步：阶段 D 增量 5（运营报表导出与定时化，或剩余管理页面收尾）。

### 阶段 C 增量 5 完成记录（2026-09-18）

- 范围：高风险动作审计闭环 + 人工授权边界（回答"谁执行、为何允许"，并强制高风险动作未经审批不得执行）。
- 领域：`domain/authorization.py`（`AuthorizationDecision`：authorization_id/tenant_id/action/resource/principal/outcome/reasons/approval_ref/decided_at，作为授权审计记录）。
- 应用：`application/high_risk_authorizer.py`（`HighRiskActionAuthorizer` 组合 rbac_repository + policy_engine + audit_repository）：解析调用者角色/权限 → `PolicyEngine.authorize` 求值 → 强制执行人工审批边界（工单未到 `READY_TO_PUBLISH` 或缺失已批准审批元数据 → `DENIED`，拒绝执行）→ 把每次授权（放行 allowed / 拒绝 denied / 待审批）写入审计事件 `{action}.authorization`（含 outcome/reasons/approval_ref/actor）；`execute_guarded` 封装"先授权后执行"，记录主体与结果。
- 授权边界修正：`application/policy_engine.py` 改为**先校验角色/权限、后校验审批**（原先审批检查在权限检查之前，会让"已审批工单 + 无权限调用者"被绕过放行）；approval 检查仅在已具备权限后触发，未批返回 `requires_approval`。
- 集成：`TicketWritebackService.write_back` 接收可选 `high_risk_authorizer`（注入即启用门禁），`write_back` 前先 `authorize_and_trace`；`support_router` 写回端点传 actor 并在 `PermissionError` 时映射为 `403`；新增 `api/authorization_router.py`（`POST /v1/authorize` 显式授权审计查询，挂载于 app）。
- 验证：`tests/platform` 146 passed（净 +11）、全仓 612 passed（净 +11）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（0 error）；`test_high_risk_authorizer.py`（授权决策 allowed/denied/审批边界/审计/execute_guarded）与 `test_authorization_api.py`（写回门禁 403、authorize 接口）。
- 本增量无新增库表，不涉及 Alembic 变更。
- 剩余风险：审批状态仍存于 ticket 元数据（无独立审批单仓储，无法跨票根或因票查询）；授权/审计仍走进程内存态 audit 仓储；`PermissionError` 与 RBAC 依赖在装配时默认 `Memory` 仓储；真实 OpenFGA/身份提供方（IdP）未接入。
- 下一步：阶段 D 增量 2（Outbox/DLQ/任务状态/重试与故障操作页面）。

### 阶段 C 增量 4 完成记录（2026-09-18）

- 范围：租户配额管理 + 管理控制台聚合概览。
- 领域：`domain/tenant_quota.py`（`TenantQuota`：tenant_id/monthly_limit/warning_threshold/hard_limit/enabled/updated_at + `usage_status(used)` 返回 active/warning/blocked 状态与 used/limit/ratio）。
- 仓储与库表：`TenantQuotaRepository` Protocol（memory/sqlalchemy 双实现）+ `TenantQuotaRecord` + `tenant_quotas` 表（Alembic `0011`）
- 应用：`application/quota_service.py` 扩展 `QuotaAwareModelGateway` 支持逐租户配额覆盖（`_resolve_budget(tenant_id)` 返回 `(budget, enforce)`，启用且未超限才 enforce budget；`enabled=False` 或未配置则回退默认 monthly_budget / 不强制），`complete()` 仅在 enforce 时按 `used + estimated > budget` 拦截。
- 接口：`api/quota_router.py`（`/v1/quotas`：PUT/GET/list/DELETE，GET 返回 `configured`+`usage`）；`api/console_router.py`（`/v1/console/overview`：聚合配额（含 configured/usage）+成本（used）+DLQ（outbox 失败数）+审计（近期事件））。`runtime.py` 装配 `tenant_quota_repository` 并经 `_wrap_gateway` 传入 gateway，`app.py` 挂载 quota+console router。
- 验证：`tests/platform` 135 passed（净 +9）、全仓 601 passed（净 +9）、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`，增量 4 新增/改动文件全部 0 error）、`alembic heads` 为 `20260918_0011`、`alembic upgrade 0010:0011 --sql` 生成 `tenant_quotas` 建表。
- 剩余风险：配额 enforce 为进程内估算（基于模型元数据 estimated_cost，达到上限后拒绝新调用），非持久账本、非近实时、未按真实计费；成本/DLQ/审计统计基于进程内存态仓储/事件；尚无完整客服工作台/审批收件箱/DLQ 页/运营看板（仅聚合概览落地）；真实 PostgreSQL/Kafka/Temporal 集成未在 Docker 跑通。
- 下一步：阶段 D 增量 2（Outbox/DLQ/任务状态/重试与故障操作页面）。

### 阶段 C 增量 3 完成记录（2026-09-18）

- 范围：RBAC（角色/权限/赋值）+ Policy Engine（动作策略/风险/审批）+ OpenFGA 式关系权限模型。
- 领域：`domain/rbac.py`（`Permission` 枚举、`Role`、`RoleAssignment`、内置角色权限矩阵 `role_permissions`）、`domain/policy.py`（`ActionPolicy`、`PolicyDecision` 含 `allowed`/`denied`/`requires_approval`、`RelationTuple`）。
- 应用：`application/policy_engine.py`（fail-closed 评估：未知/禁用动作拒绝、可选 OpenFGA 关系检查门禁资源访问、需审批高风险动作返回 requires_approval、角色/权限 allow-list）、`application/openfga_adapter.py`（内存态 OpenFGA 式关系 tuple CRUD + check，可替换真实服务）、`application/builtin_policies.py`（默认 `ticket.writeback`（high、需审批）、`ticket.view` 策略 + 内置角色 seed）。
- 仓储与库表：`RbacRepository` Protocol（memory/sqlalchemy 双实现）+ `RoleRecord`/`RoleAssignmentRecord` + `rbac_roles`/`rbac_role_assignments` 表（Alembic `0010`）。
- 接口：`api/rbac_router.py`（`POST /v1/rbac/roles`、`GET /v1/rbac/roles`、`POST /v1/rbac/roles/{id}/permissions`、`POST /v1/rbac/assignments`、`GET /v1/rbac/assignments`、`POST /v1/rbac/authorize`），已挂载 `app.py`，`runtime.py` 装配 rbac_repository/policy_engine/openfga_client。
- 提交：见 `git log` 阶段 C 增量3 提交（当前 HEAD）。
- 验证：`tests/platform` 126 passed、全仓 592 passed、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）、`alembic heads` 为 `20260918_0010`、`alembic upgrade head --sql` 生成 `rbac_roles`/`rbac_role_assignments` 建表 + 租户索引。
- 剩余风险：OpenFGA 为内存实现，未接真实 OpenFGA 服务；策略静态声明（无热加载/审计策略变更）；尚未与企业级身份提供方对接，API Key 仍为静态映射；admin 权限矩阵未落库为动态可配置。
- 下一步：阶段 C 增量 4 管理控制台（任务状态、失败重试与 DLQ、审批收件箱、成本/配额、审计查询）+ 租户配额强化。

### 阶段 C 增量 2 完成记录（2026-09-18）

- 提交：见 `git log` 阶段 C 增量2 提交（当前 HEAD）。
- 改动：
  - `ports.py` 新增 `ConnectorRepository` Protocol（`save_spec`/`get_spec`/`list_specs`/`delete_spec`），对齐 Repository 双实现模式。
  - 新增 `infrastructure/memory_connector_repository.py`（内存 dict）与 `sqlalchemy_connector_repository.py`（async SQLAlchemy，merge 保存、created_at 降序、租户过滤、delete）；`models.py` 新增 `ConnectorSpecRecord` ORM 模型（`connector_specs` 表，含 tenant_id 索引、allowed_actions/config/credential JSON、enabled、created_at）；Alembic `0009` 建 `connector_specs` 表。修复 sqlite naive datetime 往返时区（`to_domain` 补 UTC）。
  - `connector_registry.py` 新增 `set_adapter`（绑定/重绑 adapter）与 `load_from_repository`（从仓储装载 spec，可选 adapter_factory 懒重建 adapter）。
  - `openapi_adapter.py` 新增 `build_openapi_adapter(spec, auth_value_provider)` 从持久化 spec 重建 adapter（headers/auth_header/超时/重试/限流从 config 读取）。
  - 新增 `application/ticket_writeback.py`：`TicketWritebackService` 把已发布工单写回外部系统——按租户解析连接器（支持注入 `connector_resolver`，否则取租户第一个 enabled 且 allowed_actions 含 `writeback` 或为空集的连接器）、构建 POST /tickets payload（含 ticket/conversation/customer/subject/reply/draft/status/priority/intent）、用幂等键 `wb-{ticket_id}` 调用 registry.invoke（含租户/动作/disabled 校验）、写审计事件（结果/错误/幂等键）、写回失败抛 `RuntimeError`、无连接器抛 `ValueError`。
  - `connector_router.py` 新增持久化注册：`POST /v1/connectors`（保存 spec 到 registry + repository，用 adapter_factory 建 adapter）、`DELETE /v1/connectors/{id}`；`support_router.py` 新增 `POST /v1/tickets/{id}/writeback`（校验租户/工单、调 `TicketWritebackService.write_back`，ValueError→409、RuntimeError→502）。`runtime.py` 装配 `connector_repository`（memory/sqlalchemy 各自实现）与 `ticket_writeback_service`，`app.py` 挂载写回接口并把 repository+adapter_factory 注入 connector router。
  - 新增 `tests/platform/test_connector_repository.py`（5 项：memory 往返/删除、sqlalchemy 往返与租户隔离）与 `tests/platform/test_ticket_writeback.py`（5 项：写回成功+审计、无连接器抛错、失败抛错+审计失败、连接器解析器注入）。
- 验证：`tests/platform` 112 passed、全仓 578 passed、Black/isort/Flake8 通过、增量相关源文件 mypy 通过（`Success: no issues found`）、`alembic heads` 为 `20260918_0009`、`alembic upgrade head --sql` 生成 `connector_specs` 建表 + 租户索引。
- 剩余风险：写回仍是面向 HTTP/OpenAPI 的通用适配，尚无真实 CRM/工单系统原生适配器；凭据只存引用、无真实 vault/密钥后端（认证值依赖 `auth_value`/注入 provider）；写回为同步调用，失败仅抛错未做消息队列重试/补偿编排；真实 PostgreSQL 端到端写回未在 Docker 跑通。
- 下一步：阶段 C 增量 3 RBAC、Policy Engine、OpenFGA 和权限模型。

### 阶段 C 增量 1 完成记录（2026-09-18）

- 提交：`aa8c899`（阶段 C 增量 1）。
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

先完整阅读仓库内交接文档和外部规划文档，再检查当前分支、提交记录、测试和代码结构。当前阶段 A、阶段 B 与阶段 C 均已完成（FTS+pgvector 混合检索、重排与召回评估、结构化分类/Prompt/模型版本与质量门禁、离线回归运行器与 Golden Dataset、Connector 适配与写回闭环、RBAC/Policy/OpenFGA、租户配额 + 管理控制台、高风险动作审计闭环 + 人工授权边界）；阶段 D 增量 1（管理控制台基础页面接口：客服工作台/审批收件箱/成本配额总览/任务计数/DLQ）、增量 2（Outbox/DLQ/任务状态列表详情计数与丢弃维护接口）、增量 3（成本/配额/模型分布/质量指标看板接口）、增量 4（审计查询、租户配置与连接器管理页面接口）、增量 5（运营报表导出与定时化）、增量 6（运营报表产物持久化与历史查询）、增量 7（报表 run 保留/清理策略）、增量 8（排程保留策略持久化 + `run_due` 自动联动清理）、增量 9（排程暂停/恢复 + 全局默认保留策略）与增量 10（cron 表达式排程）已完成。下一步从阶段 D 增量 13 开始：`run_due` 移入 worker 异步化，或剩余管理页面收尾。

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
