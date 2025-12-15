# AgentForge 未实现项 / 风险 / 漏洞 Backlog

> 目的：把所有**未实现**、**当前环境无法解决**、**被推后**的问题固化成一份可跟踪、
> 可逐一核销的清单。原则：先记录完整闭环，能当下解决的在代码里落地；依赖外部
> 基础设施（Temporal/真实 PostgreSQL/前端/K8s/真实 CRM 等）的跳过并在本表登记，
> 后续具备条件时按编号补写。本表是"整个流程走完后再回来补"的最终依据。

- 基线提交：`06eee7b`（阶段 D 增量 15 收尾）
- 建立日期：2026-09-18
- 状态字段：`开` / `done` / `skip(需外部环境)` / `skip(超范围)`

---

## 1. 阶段 D 未实现项（管理控制台与运营）

| 编号 | 问题 | 状态 | 说明 / 前置条件 |
|------|------|------|------|
| D-01 | 前端管理页面：工单列表/详情、审批收件箱、人工编辑界面 | skip(超范围) | 后端接口 `/v1/console/tickets`、`/v1/console/inbox` 已落地；前端页面在本后端仓库范围外 |
| D-02 | 前端页面：Outbox / DLQ / 任务状态 / 重试 / 故障操作 | skip(超范围) | 后端 `/v1/outbox/events` 等已落地；重试沿用 `/v1/outbox/{id}/replay`、`/replay-failed` |
| D-03 | 前端可视化：成本/配额/模型分布/质量指标看板、按日/按模型趋势图 | skip(超范围) | 后端 `/v1/console/dashboard`、`/cost-trend`、`/model-distribution`、`/quality` 已落地 |
| D-04 | 前端页面：审计查询、租户配置、连接器管理 | skip(超范围) | 后端 `/v1/console/audit`、`/tenants`、`/connectors` 已落地 |
| D-05 | `run_due` 仍为同步执行，未接入 Temporal/worker 异步 | skip(需外部环境) | 依赖 Temporal/worker 基础设施；当前只能同步跑通排程链路 |
| D-06 | 报表列表分页为 offset 语义，非 keyset/游标 | done（增 16） | 已改为基于 `(generated_at, run_id)` 的 keyset 游标，消除偏移漂移，重复时间戳下稳定翻页 |
| D-07 | 报表 ZIP 导出经临时文件落盘后流式 | done（审定为已满足） | 增量 14 已用 temp-file + StreamingResponse 分段流式，避免全量内存；ZIP 需可 seek sink，temp-file 为合理实现，非漏洞 |

---

## 2. 阶段 C 相关风险 / 漏洞

| 编号 | 问题 | 状态 | 说明 |
|------|------|------|------|
| C-01 | 无真实 CRM（Salesforce 等）/ 工单系统（Zendesk 等）/ 业务数据库原生适配器 | skip(需外部环境) | 现状为面向 HTTP/OpenAPI 的通用写回实现 + 注册能力 |
| C-02 | 凭据仅存引用，无真实 vault / 密钥后端 | skip(需外部环境) | 需企业级密钥管理 |
| C-03 | OpenFGA 为内存态实现，无真实 OpenFGA 服务 | skip(需外部环境) | 需部署真实 OpenFGA；RBAC/Policy/授权闭环已验证（C-05 已落地） |
| C-04 | 无企业级身份提供方（IdP）对接 | skip(需外部环境) | API Key 仍为静态映射 |
| C-05 | 管理员权限矩阵、策略热加载、审计策略变更 | done（增 18，热加载+版本化审计） | `PolicyFileLoader`（JSON 严格解析）+ `PolicyEngine.reload/reload_from_loader`（原子换载、source_revision 追踪、坏配置保旧）+ 版本化审计（`PolicyReloadEvent`→`reload_listener`）；管理员权限矩阵/运行时策略编辑 API 尚未实现，属前端/多进程范畴登记待补 |

---

## 3. 配额 / 成本 / 运营数据风险

| 编号 | 问题 | 状态 | 说明 |
|------|------|------|------|
| Q-01 | 配额 enforce 为进程内估算（基于模型元数据 estimated_cost） | done（复核） | 已由 `QuotaAwareModelGateway` + `CostRepository.total_for_tenant` 走 SQL 聚合裁决（memory/sqlalchemy 双实现），`estimated_cost` 仅用于请求预估，非配额统计来源 |
| Q-02 | 成本 / DLQ / 审计统计基于进程内存态仓储/事件 | done（复核） | SQLA 仓已用 `SUM`/`GROUP BY`（`daily_summary`/`summary_for_tenant`）；审计聚合接口 `/v1/console/audit`、看板 `/v1/console/dashboard`、`/cost-trend` 已落地。真实 DB 聚合在无 Docker 的本地由 aiosqlite 验证 |
| Q-03 | Prompt/模型版本为进程内存注册表，进程重启即清空、无跨进程一致性 | skip(需外部环境) | 需落库 + 跨进程一致性的版本表 |

---

## 4. 基础设施 / 集成 / 部署风险

| 编号 | 问题 | 状态 | 说明 |
|------|------|------|------|
| I-01 | 未对真实 PostgreSQL 端到端跑通 | skip(需外部环境) | 本地无 Docker；仅方言编译 + 离线迁移验证通过 |
| I-02 | 缺 PostgreSQL / Kafka / Temporal 真实端到端集成测试与故障演练 | skip(需外部环境) | |
| I-03 | 缺生产部署方案：K8s / Helm / Terraform / CI-CD / 迁移 / 灰度 / 回滚 | skip(需外部环境) | 阶段 F 范畴 |
| I-04 | 缺生产高可用拓扑（PG / Kafka / Temporal / Valkey / MinIO） | skip(需外部环境) | |
| I-05 | 缺安全合规、备份、容灾、密钥轮换方案 | skip(需外部环境) | |
| I-06 | 缺稳定版本、兼容策略、行业模板、开源核心与企业控制面等产品化项 | skip(需外部环境) | 阶段 F 范畴 |

---

## 5. 数据 / 评估 / 试点（阶段 E）缺口

| 编号 | 问题 | 状态 | 说明 |
|------|------|------|------|
| E-01 | 缺真实 Golden Dataset（200-500 条历史工单）与数据集版本快照 | skip(需外部环境) | 需真实或高保真数据源 |
| E-02 | Sug 缺人工基线 / 影子运行 / 抽样评估过程数据 | skip(需外部环境) | 回归运行器已具备（`RegressionRunner` + `golden_items`/`regression_runs` 表） |
| E-03 | 缺真实客户或高保真模拟客户试点、案例报告、演示与指标材料 | skip(需外部环境) | |

---

## 6. 可在当前环境继续落地（非跳过）的跟进项

> 这些不依赖外部基础设施，具备条件后直接补，无需外部环境准备。

- **D-06** 分页改为滚动游标（keyset），消除 offset 漂移。
- **C-05**（done）策略配置源热加载 + 版本化审计（`PolicyReloadEvent`→`reload_listener`）；配额裁决经 SQL 聚合已闭环。
- **Q-01 / Q-02**（done，复核）配额/成本已由 SQL 聚合闭环；看板/趋势接口已落地，无需再补。

---

### 更新记录

- 2026-09-18：建立。将阶段 C/D/E 未实现项、基础设施缺口与本地可补项全部登记；基线 `06eee7b`。
    - 2026-09-19：C-05 补齐版本化审计（`PolicyReloadEvent`→`reload_listener`，增 18），策略套件 15 通过；同步清理第 6 节与 D-07/Q 已审定结论相矛盾的过时文字。内部可闭环项全部核销。