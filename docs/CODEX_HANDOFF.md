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
11. Alembic `0001` 到 `0006` 迁移链路。
12. 全仓测试基线恢复，目前 `506 passed`。

## 4. 当前验证命令

在仓库根目录执行：

```powershell
python -m pytest tests -q
python -m pytest tests/platform -q
python -m black --check --line-length 100 agentforge tests alembic
python -m isort --check-only --profile black agentforge tests alembic
python -m flake8 --max-line-length=100 --extend-ignore=E203,W503 agentforge tests alembic
python -m alembic upgrade head --sql
```

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

- 检索仍以关键词为主，没有完整 PostgreSQL FTS + pgvector 混合检索和重排。
- 没有真正的 Connector SDK，也没有 CRM、工单系统或业务数据库写回连接器。
- 缺少 RBAC、策略引擎、OpenFGA、用户级权限和管理员权限矩阵。
- 缺少客服工作台、审批收件箱、DLQ 管理页面和运营成本/质量看板。
- 评估样本已采集，但还没有真正的 Golden Dataset 离线回归运行器。
- 缺少 Prompt 版本、模型版本、数据集版本和发布门禁。
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

1. PostgreSQL FTS + pgvector 混合检索与 Alembic 迁移。
2. 重排器、召回评估、引用正确率和 Recall@K。
3. 结构化分类、Prompt 版本、模型版本和质量门禁。
4. 基于评估样本的离线回归运行器与质量报告。

### 阶段 C：企业连接与治理

共 5 个增量：

1. Connector SDK、Webhook Adapter、OpenAPI Adapter。
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

阶段 A 已完成，后续剩余 5 个阶段，共 24 个建议增量。每个增量应控制在 0.5 到 2 天内可完成、可测试、可提交的范围内。

## 8. 下一步立即执行项

从阶段 B 的第 1 个增量开始：

目标：把当前关键词检索升级为 PostgreSQL FTS + pgvector 混合检索。

必须包含：

1. 设计向量列、索引和 embedding 版本字段。
2. 扩展 KnowledgeRepository 的检索接口。
3. 保留 MemoryKnowledgeRepository，保证单元测试无需 PostgreSQL。
4. 新增 SQLAlchemy 混合检索实现。
5. 增加 Alembic 迁移。
6. 增加召回率、租户隔离和空结果测试。
7. 更新知识 API 的检索参数和返回结构。
8. 更新架构文档和交接文档。

验收标准：

- 同一租户才能检索到自己的文档。
- 关键词命中与向量相似度可以合并排序。
- 旧数据可以回填 embedding。
- 单元测试、格式检查、Alembic SQL 生成全部通过。

## 9. 给扣子或后续 AI 工程师的最短提示词

```text
项目路径：C:/Users/HP/Documents/Codex/2026-09-17/mu/work/AgentForge
当前分支：codex/support-copilot-foundation
交接文档：C:/Users/HP/Documents/Codex/2026-09-17/mu/work/AgentForge/docs/CODEX_HANDOFF.md
工程书：C:/Users/HP/Documents/Codex/2026-09-17/mu/outputs/AgentForge-Million-Scale-Engineering-Spec.md
场景基线：C:/Users/HP/Documents/Codex/2026-09-17/mu/outputs/AgentForge-MVP-Customer-Service-Scenario.md

先完整阅读仓库内交接文档和外部规划文档，再检查当前分支、提交记录、测试和代码结构。当前阶段 A 已完成，下一步从阶段 B 的第 1 个增量开始：PostgreSQL FTS + pgvector 混合检索。

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
