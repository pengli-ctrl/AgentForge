# AgentForge 企业 AI 平台层（platform)评审报告

> 评审范围：`agentforge/platform/`（api / application / domain / infrastructure / workflows / connectors / cli / observability / runtime.py 等）
> 评审维度：代码合理性 + 注释专业性 + 与 README 设计意图一致性
> 评审方式：逐文件真实读取，下述所有文件:行号均指实际代码

---

## 一、代码不合理点（严重程度分级）

### 严重(High)

| # | 文件:行号 | 问题 | 说明 |
|---|---|---|---|
| H1 | `application/policy_engine.py:185-201, 230-247` | **RBAC 门禁可被配置笔误静默失效（fail-open）** | `required_permission` 是 `str`，在 authorize 内 `Permission(policy.required_permission)` 若遇非法枚举值(如拼写错误)被 `except ValueError: needed=None` 吞掉。此后若 `allowed_roles` 为空，则走到 `if not allowed_roles or ...:` 分支返回 `ALLOWED`（“open policy”）。即某条策略只要 `required_permission` 写错且未配 allow-list，**任何 principal 都可放行**，与类 docstring声称的 fail-closed 相悖。修复方向：策略在 reload/register 时即强校验 `required_permission` 为合法枚举，非法直接拒绝加载。 |
| H2 | `application/openapi_adapter.py:137` | **async 内同步 `time.sleep()` 阻塞整个事件循环** | 重试回退用 `time.sleep(self._retry_backoff * (2**attempt))`，在 async `invoke` 中会阻塞当前 loop 的全部协程。应使用 `await asyncio.sleep(...)`。 |
| H3 | `application/openapi_adapter.py:186-205` + `infrastructure/db/models.py:406` + `api/connector_router.py:21,29,42` | **凭据以明文存入 config 并随 API 回显，违背“by-reference”设计** | `build_openapi_adapter` 从 `spec.config.get("auth_value")` 读取原始密钥（openapi_adapter.py 注记 `static_value = config.get("auth_value")`），该值落库为 `config: JSON` 明文（models.py:407），并通过 `GET /v1/connectors`、`/v1/connectors/{id}`、`POST /v1/connectors` 的 `spec.model_dump()` 直接返回。这与 `domain/connector.py:26-39 CredentialReference“绝不持有密钥”“secrets by reference”` 的设计声明冲突，属越权/敏感信息泄露风险。 |
| H4 | `api/connector_router.py:18-93` | **连接器路由全程无任何鉴权/租户绑定** | 与其它 router（都调用 `authenticator.authorize_tenant`）不同，`list/get/register/delete/invoke` 均未做 API Key 校验，也未做 admin 校验。任何匿名调用者都能注册/删除连接器并 invoke。叠加默认 `auth_enabled=False`，等于面向公众开放。 |

### 中等(Medium)

| # | 文件:行号 | 问题 | 说明 |
|---|---|---|---|
| M1 | `application/quota_service.py:40-48` | **配额仅用 `monthly_limit`，告警阈值/硬上限未强制；且判定非原子（TOCTOU）** | `TenantQuota` 提供了 `warning_threshold`/`hard_limit` 分级，但网关只用 `used + estimated_cost > budget` 一票否决，`hard_limit/warning_threshold` 完全未参与（README #4 声称三者逐租户强制，见一致性表）。同时判定是“读已用量→比较→放行”，无预留/加锁，并发请求可集体越过预算；且用的是 `metadata.estimated_cost` 估算值(默认 0.01)，非实际成本。 |
| M2 | `api/support_router.py:14-23` | **通用 IM 入站端点 `POST /v1/events/im` 完全不做签名校验** | README #6/#8 声称“Webhook 泛化(HMAC 验签) + 幂等”。该端点只按可选 `tenant_id` 做 API Key 校验（默认关闭），对任意伪造 payload 直接建票。HMAC 验签只在 feishu 端实现。 |
| M3 | `api/feishu_router.py:39` | **飞书签名校验 fail-open** | `if encrypt_key and not verifier.verify(...)` —— 当 `encrypt_key` 为空(默认 `""`，settings.py:23)时整个校验被跳过。README #6 声称“签名校验”，生产默认即绕过。另 `connectors/feishu.py:15` `sha256(timestamp+nonce+key+body)` 拼接式签名与飞书官方事件签名算法（多次换行拼接）很可能不一致，且缺少时间戳新鲜度窗口（防重放）。 |
| M4 | `application/support_ticket_service.py:219-241` | **对外回复先发后存，状态/数据一致性脆弱** | `publish_reply` 先调 `_reply_connector.send_text` 真正发给客户，成功后才落库置 `PUBLISHED`。若 save 抛错，回复已发出但工单未记录（或反之审计失败），无事务/Outbox 兜底；“先发后确认”违背可靠谢绝重复原则，仅靠 `reply-{ticket_id}` 幂等键弱约束。 |
| M5 | `application/builtin_policies.py:52-82` | **`seed_rbac` 定义但全仓无调用点（死代码）** | 经扫描无任何 `seed_rbac(...)` 调用，内置角色(含 `TICKET_WRITEBACK`)从不初始装配。加上未配角色则 `ticket.writeback` 因缺 `required_permission` 恒被 DENIED，导致开箱即用的写回闭环实际不可用（除非手动通过 rbac API 造角色/赋值）。 |
| M6 | `application/connector_registry.py:90-108` + `api/app.py` | **`load_from_repository` 从未被调用** | SQL 容器把 `SQLAlchemyConnectorRepository` 注入容器(connector_repository)，但 registry 默认仍是新建的内存 `ConnectorRegistry()`，且启动时从未 `load_from_repository`，重启后已持久化的连接器不会重建 adapter，`registry.invoke` 会返回 “connector not registered”，写回在重启用例下失效。 |
| M7 | `application/openapi_adapter.py:75-87` | **令牌桶限流失效（从不真正限流）** | `_acquire_token` 当 `_bucket_tokens < 1` 时无条件 `+=1`，等价于每次都补一个 token，请求永不被节流，与 README #8 “令牌桶限流”不符。 |
| M8 | 默认配置安全基线 | **多租户隔离整体“信任调用方”** | `settings.py:27 auth_enabled=False`、`runtime.py:153` 默认 `ApiKeyAuthenticator(enabled=False)`，叠加 M2/H4，多个端点(尤其 connectors、events/im)对跨租户访问无真实防护；租户隔离在内存仓储层有 `tenant_id` 过滤(get 检查、connector tenant mismatch)，但 API 层依赖调用方自觉传租户。 |

### 低(Low)

| # | 文件:行号 | 问题 | 说明 |
|---|---|---|---|
| L1 | `application/support_ticket_service.py:38-40` + `infrastructure/db/models.py:41-43,139` | **幂等 check-then-insert 存在并发竞态** | 并发重复事件时两处 `get_by_idempotency_key` 均返回 None，随后双双 insert，唯一约束(tenant_id,idempotency_key)触发 `IntegrityError` 未捕获 → 500（而非返回既有工单）。DB 约束兜底存在，但应用层无 `IntegrityError` 重抓处理。 |
| L2 | `infrastructure/sqlalchemy_ticket_repository.py:28-37` | **`version` 字段未做乐观锁** | `apply_domain` 无条件覆写 `version`，DB `WHERE version=?` 校验缺失，“版本并发控制”仅停留在字段层，实际不防丢更新。 |
| L3 | `infrastructure/db/models.py:406` | **连接器 config/credential 明文 JSON 落库** | 与 H3 同源：密钥明文存库（含 `auth_value`），无加密、无脱敏、无访问审计。 |
| L4 | `application/policy_engine.py:203-258` | **双层重复权限判定逻辑冗余且误导** | 185-201 先查权限，到 230-245 又查一遍才返回 ALLOWED，中间靠 `require_approval` 分支隔断；两段语义相同、易被误改，属可达死代码。 |
| L5 | `infrastructure/temporal/client.py:36-41` | **workflow 启动无线程/执行超时，未显式回收策略** | `start_workflow` 未设 `workflow_execution_timeout/run_timeout`，id 复用默认策略下重复提交可能抛 `AlreadyStarted`。 |
| L6 | `application/report_service.py:32-36` | **monthly 用 30 天近似、cron 推进与 `now` 基准存在漂移**（低，非 README 声称） | 仅为实现备注，非缺陷清单重点。 |

---

## 二、注释专业性问题

### 做得好的（专业、解释“为什么”）
- `application/high_risk_authorizer.py:17-27` 类 docstring 点明“关闭’谁执行/为何允许’审计闭环”“fails closed”，符合工程 spec 引用。
- `application/policy_engine.py:32-40`、`_swap:101-108`、`reload_from_loader:88-99` docstring 清晰说明原子替换与调用方职责、失败时引擎不变。
- `application/report_service.py:448-462 run_due` 用 docstring 解释“幂等、严格保留下最严格 retention、审计回退默认窗口”的设计缘由。
- `domain/connector.py:26-39 CredentialReference` 明确“只存引用、密钥进 vault”，方向正确（尽管实现 H3 违背了它）。
- `domain/policy.py:74-105 PolicyFileLoader`、`retrieval_metrics.py`（Recall@K/MRR/引用率）均有中英混合、含边界(空集/除零)解释的 docstring。
- `runtime.py:269-281`、`_resolution_budget` 等穷举“enforce=False 语义”。

### 缺失/误导/不一致
| # | 位置 | 问题 |
|---|---|---|
| C1 | `application/support_ticket_service.py:18`, `application/ports.py` 全部 Protocol | 核心公共服务类 `SupportTicketService` 与全部仓储 Protocol 的**方法级 docstring 基本缺失**（ports 中仅方法签名 `...`，无“为什么/何时用”说明），与 P 层其他类的高质量注释形成落差。 |
| C2 | `application/quota_service.py:25-38 _resolve_budget` | docstring 称“告警阈值/硬上限”语义，但代码只用 `monthly_limit`，**注释与实现不符**（见 M1），误导读者以为分级生效。 |
| C3 | `application/openapi_adapter.py:75-87` | 注释“Refill enough for one token on the next attempt window”实际逻辑是无条件 `+1`，注释掩盖了限流失效（见 M7）。 |
| C4 | `domain/connector.py:26-39` vs `openapi_adapter.py:191-195` | “凭据 by-reference”注释与“读明文 auth_value”实现互相矛盾（见 H3）。 |
| C5 | `connectors/feishu.py:8-17 FeishuSignatureVerifier` | 未注释该签名算法与飞书官方规范的对应关系/兼容边界，且(见 M3)未说明 `encrypt_key` 为空时由上层跳过校验，易被当作已做验签。 |
| C6 | `workflows/support_ticket.py:32-66` | 工作流 run 中对“等待 Signal 无超时、无心跳/关闭策略”无注释说明，未来维护者难判断这是有意长期等待还是泄漏。 |

> 结论：**P 层注释整体专业、多为中英混合解释“为什么”（明显优于一般开源仓库）**，但集中在服务类/工具函数；对外的仓储 Protocol、以及 3 处“注释与实现相悖”的点需要补齐修正。

---

## 三、README 一致性核对表

### 设计意图 12 条

| # | README 声明 | 结论 | 差异说明 |
|---|---|---|---|
| 1 | 多租户隔离（工单/知识/RBAC/配额/审计/连接器全按租户） | **部分** | 仓储层有租户过滤（ticket.get 校验 tenant、connector_registry.invoke 校验 tenant mismatch、各仓储索引 tenant_id），方向正确；但 API 层多端点“信任调用方”且默认鉴权关闭，connector 路由完全无鉴权，飞书/IM 入站可被跨租户伪造。隔离“实现分层不完整”。 |
| 2 | RBAC + ActionPolicy（fail-closed/风险级/审批/allow-list + OpenFGA） | **一致(基本)** | `PolicyEngine.authorize` 本质 fail-closed、给出 allowed/denied/requires_approval、支持 allowed_roles 白名单与可选 `relation_check`(OpenFGA)。但 H1 的非法枚举 fail-open 使其“铁板闭环”打了折扣。 |
| 3 | HighRiskAuthorizer：未 READY_TO_PUBLISH/未获批→DENIED，每次授权写审计 | **一致** | `high_risk_authorizer.py:77-85` 仅当 `_approval_granted`(status==READY_TO_PUBLISH + metadata.approval.decision==approve) 才 ALLOWED，否则 DENIED；`_record_audit` 记录 outcome/reasons/approval_ref/actor。行为与声明吻合。 |
| 4 | 租户配额：月度预算/告警阈值/硬上限，QuotaAwareModelGateway 逐租户强制 | **部分→不一致** | 领域模型含三分级，但网关仅强制 `monthly_limit`，`warning_threshold/hard_limit` 未生效（M1）；判定非原子。README 声称“逐租户强制三者”不成立。 |
| 5 | 全过程审计（事件/操作者/trace_id/成本汇总） | **一致** | AuditEventRecord(tenant/action/actor/trace_id/payload)、support_ticket 每次动作记审计、cost 汇总由 cost 仓储+console/report 提供。 |
| 6 | 工单全流程（签名+幂等→建票/状态机→意图+风险→检索→草稿+引用→风险→审核/审批→写回→评估样本） | **部分** | 分段实现齐备（状态机、分类、pgvector+FTS 检索、引用校验、审批、写回、EvaluationSample 反馈）；但①“签名校验”仅在 feishu 端点且为空 key 即跳过、`/events/im` 无签名(M2/M3)；②检索+草稿+风险提升仅在 `processing_service`（被 Temporal activity 调用）内完成，而 `create_from_event`、`/events/im`、`/v1/events/feishu` 直接调用 `ticket_service.create_from_event` 只做分类、不生成草稿——内联端点并不走完整流水线。 |
| 7 | Temporal 工作流（审批 Signal、Outbox、失败重试、DLQ 重放） | **一致** | workflow 有 `approve` Signal/`wait_condition`、活动超时重试；ticket+outbox 事件同事务落库（sqlalchemy_ticket_repository.begin）；outbox DISPATCHER/worker 与 `/v1/outbox` 的 replay-failed/replay/discard 提供 DLQ 重放。 |
| 8 | 连接器（ABC+Registry、Webhook HMAC、OpenAPI 幂等键+有界重试+令牌桶+审计、CRM/工单写回闭环、Feishu） | **部分** | ABC+Registry/写回闭环/Webhook HMAC/webhook_adapter /OpenAPI 幂等头/有界重试/审计/FeishuConnector 均存在；但①令牌桶实现失效(M7)②重试用阻塞 sleep(M2)③连接器路由无鉴权(H4)④明文凭据(H3)，故“完整闭环”被打折。 |
| 9 | 检索评估（HybridReranker、Recall/Precision/MRR/引用率、RetrievalEvaluationService、离线 RegressionRunner+Golden） | **一致** | `reranker.HybridReranker`、`retrieval_metrics`、`retrieval_evaluation_service`、`regression_runner`、Golden repository 均实现。 |
| 10 | 质量门禁（分类/优先级/结构合法/高风险漏报，版本化 Prompt/Model 注册，PASS/HOLD/BLOCK，高危漏报一票否决） | **部分** | `QualityGateService` 高风险漏报 >0→BLOCK（一票否决✓）、classification_accuracy 硬/目标阈值生效；**但 `priority_accuracy` 与 `structured_output_rate` 只进 metrics 从不判级**（quality_gate_service.py:67-93），README 声称四指标纳入门禁不成立。PromptRegistry/ModelVersionRegistry 版本化存在。 |
| 11 | 策略配置源热加载（PolicyFileLoader strict+extra=forbid、reload 原子 swap、monotonic source_revision、versioned reload 事件） | **部分** | 引擎层全部就位（domain/policy.py strict JSON + ActionPolicy extra=forbid；policy_engine._swap 原子、source_revision 单调、PolicyReloadEvent 监听）；**但运行时无任何文件源/定时器/API 触发 reload**（`reload`/`reload_from_loader` 全仓无调用点），且无 `/v1/policies` 路由（见下表），即“配置源热加载”仅停留在可编程接口、未接入系统运行。 |
| 12 | 分层 domain/application/infrastructure(Protocol 双仓储)/api | **一致** | 目录结构与 Protocol 双 Memory/SQLAlchemy 实现清晰成立。 |

### 平台 API 表逐条核对

| README 列出的前缀 | 实际路由验证 | 结论 |
|---|---|---|
| `/v1/tickets` | 实际挂在 `support_router`(prefix=/v1) 下：`GET /v1/tickets/{id}`、`POST /v1/tickets/{id}/approve|reject|review|reply|writeback` | **部分**：详情/写回/审批/审核/回复都在；但**无 list()、无 create、无 delete**，README “工单 CRUD” 中的 C(create)/D(delete)/列表 R 缺失；且前缀不由独立 tickets router 承载。 |
| `/v1/console` | `console_router` prefix=/v1/console，含 overview/tickets/inbox/costs/cost-trend/model-distribution/quality/dashboard/tenants/audit/connectors/connector enabled/reports 系列 | **一致** ✓ |
| `/v1/rbac` | `rbac_router` prefix=/v1/rbac：roles CRUD、assignments、`/authorize` | **一致** ✓（另存在独立 `/v1/authorize`，README 未列入但不冲突） |
| `/v1/policies` | **全仓无此路由**（仅 `release_router` 为 /v1/release；PolicyEngine.reload/list_policies 无 API 暴露） | **不一致(缺失)** ✗：README 声称“声明式动作策略（配置源热加载）”的前缀完全不存在。 |
| `/v1/quotas` | `quota_router` prefix=/v1/quotas：GET/PUT/DELETE `/{tenant_id}` + list | **一致** ✓ |
| `/v1/audit` | `audit_router` prefix=/v1/audit：GET | **一致** ✓ |
| `/v1/costs` | `cost_router` prefix=/v1/costs：`/summary` | **一致** ✓ |
| `/v1/knowledge` | `knowledge_router` prefix=/v1/knowledge：`POST /documents`、`GET /search` | **一致** ✓ |
| `/v1/evaluations` | `evaluation_router` prefix=/v1/evaluations：summary/samples/retrieval/classification | **一致** ✓ |
| `/v1/regression` | `regression_router` prefix=/v1/regression：golden、run、runs | **一致** ✓ |
| `/v1/connectors` | `connector_router` prefix=/v1/connectors（CRUD+health+invoke） | **一致** ✓（但无鉴权，见 H4） |
| `/v1/outbox` | `outbox_router` prefix=/v1/outbox：failed、events、replay、discard、replay-failed | **一致** ✓ |
| （README 未列） | `/v1/events`(feishu)、`/v1/authorize`、`/v1/release` | **追加存在**，README 未提及但属增量，非冲突。 |

### README 一致性小结
- **逐条如实核对的 12 条中**：一致 5 条（#2、#3、#5、#7、#9、#12，计 6）、部分 5 条（#1、#6、#8、#10、#11）、基本不一致 1 条（#4）。
- **API 表 12 个前缀中**：10 个一致、`/v1/tickets` 部分（无 CRUD）、**`/v1/policies` 完全缺失**（README 宣称但代码不存在）。
- 最需先修正的 3 处 README/实现偏差：①`/v1/policies` 路由及策略热加载未接入运行；②配额分级（告警/硬上限）未在网关生效；③质量门禁未真正门禁优先级/结构化合法率。

---

## 附录：文件清单复核说明
本报告基于对 `runtime.py、policy_engine.py、high_risk_authorizer.py、support_ticket_service.py、support_ticket_processing_service.py、reply_draft_service.py、report_service.py、quota_service.py、quality_gate_service.py、openapi_adapter.py、webhook_adapter.py、connector_registry.py、ticket_writeback.py、builtin_policies.py、retrieval_metrics.py、ports.py、settings.py、policy.py、tenant_quota.py、ticket.py、connector.py、models.py、sqlalchemy_ticket_repository.py、temporal/client.py、workflows/support_ticket.py、connectors/feishu.py、api/{app,support_router,feishu_router,connector_router,authorization_router,security}.py` 等关键文件的逐行读取，并对 api/ 全量路由做了脚本扫描（12 前缀逐一比对），非臆测。