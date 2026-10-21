# Expense Module

## 模块定位

Expense 是平台化改造的第二个真实业务模块，用于验证“共享内核 + 业务模块”是否可复用。
当前已覆盖人工录入、附件上传、OCR 提取与确认建单、费用政策、提交审批、审批决定、已批准台账、审计和 Outbox。

## 已实现能力

- 人工录入关键字段：申请人、金额、币种、费用日期、类别、说明、票据数量
- `idempotency_key` 防重复创建
- 发票附件上传、元数据持久化和短时下载 URL
- 对象存储支持 Memory / S3 兼容（MinIO、云 S3）
- OCR Provider Port 与字段归一化
- OCR 结果服务端留存，确认后创建草稿，保留原文、置信度和人工修改字段
- 类别限额与月度预算校验，违规信息写入 Claim 和审批上下文
- 草稿提交后进入 `waiting_approval`
- 审批通过/驳回经共享 RBAC 与策略授权
- `/v1/expense/ledger` 返回已批准报销台账和汇总金额
- 所有查询按 `tenant_id` 隔离
- PostgreSQL 使用 `module_expense` schema
- Memory / SQLAlchemy 双仓储
- OCR 异步 Job、批量导入、状态查询、失败重试和导入汇总
- 审批通过后才进入全文索引，支持 Expense 范围内 RAG 检索和来源回链
- 发票登记、租户级指纹去重、Connector 验真和释放重提
- 发票门禁模式：off / duplicate_only / verified / strict
- 审批预检、强门禁和受审计的 override 流程
- 门禁 readiness、阻断、override、指标和告警事件
- 告警 active/resolved 生命周期、重复扫描幂等和恢复事件
- 告警 occurrence 编号、重复发生事件字段和历史状态指标
- 告警恢复自动关闭 Support Ticket
- Temporal 周期扫描 Expense 门禁告警
- 按模块 Task Queue 启动 Temporal Worker

## 主要接口

```text
# 附件与可分片上传
POST /v1/expense/attachments
POST /v1/expense/upload-sessions
GET  /v1/expense/upload-sessions/{upload_id}
PUT  /v1/expense/upload-sessions/{upload_id}/parts/{part_number}
POST /v1/expense/upload-sessions/{upload_id}/complete
GET  /v1/expense/attachments/{attachment_id}

# OCR 与导入
POST /v1/expense/extractions
POST /v1/expense/extractions/{extraction_id}/confirm
POST /v1/expense/ocr-jobs
POST /v1/expense/ocr-jobs/batch
GET  /v1/expense/ocr-jobs
GET  /v1/expense/ocr-jobs/summary
GET  /v1/expense/ocr-jobs/{job_id}
POST /v1/expense/ocr-jobs/{job_id}/retry
POST /v1/expense/imports
GET  /v1/expense/imports
GET  /v1/expense/imports/{batch_id}
POST /v1/expense/imports/{batch_id}/retry-failed

# 报销、检索与政策
POST /v1/expense/claims
GET  /v1/expense/claims
GET  /v1/expense/claims/{claim_id}
POST /v1/expense/claims/{claim_id}/submit
POST /v1/expense/claims/{claim_id}/decision
POST /v1/expense/claims/{claim_id}/index
GET  /v1/expense/policies
GET  /v1/expense/search
POST /v1/expense/answer

# 发票登记、门禁与验真
POST /v1/expense/invoices/check-duplicate
POST /v1/expense/claims/{claim_id}/invoices
GET  /v1/expense/claims/{claim_id}/invoices
GET  /v1/expense/claims/{claim_id}/invoice-readiness
GET  /v1/expense/invoices/gate-summary
GET  /v1/expense/invoices/gate-metrics
POST /v1/expense/invoices/gate-alerts/scan
POST /v1/expense/invoices/{invoice_id}/verify
POST /v1/expense/invoices/{invoice_id}/release

# 台账与写回
GET  /v1/expense/ledger
GET  /v1/expense/ledger/export
POST /v1/expense/ledger/writeback
POST /v1/expense/ledger/writebacks/verify
POST /v1/expense/ledger/writebacks/compensate
GET  /v1/expense/ledger/reconciliation
POST /v1/expense/ledger/writeback-jobs
GET  /v1/expense/ledger/writeback-jobs
GET  /v1/expense/ledger/writeback-jobs/summary
GET  /v1/expense/ledger/writeback-jobs/{job_id}
POST /v1/expense/ledger/writeback-jobs/{job_id}/retry-failed
```

## 后续增强

- 更细粒度的部门/项目预算与分账。
- 大规模门禁指标的增量物化和历史趋势分析。
- 与客户 ERP/财务系统的账单级对账和补偿流程。

财务专用工单队列与 SLA 由 Expense 门禁告警事件联动 Support 模块实现：Expense 负责产生告警和恢复事件，Support 负责创建、分派、升级和关闭财务队列工单。

## 设计边界

- Expense 不直接依赖平台 Runtime 或具体共享基础设施实现。
- 领域和应用层只依赖本模块 Port 与 SDK Port。
- SQLAlchemy 模型属于模块 Infrastructure 层，并运行在 `module_expense` schema。
- 金额使用整数分 `amount_cents`，避免浮点金额误差。
- `AGENTFORGE_EXPENSE_INVOICE_ALERT_SWEEP_MINUTES=0` 可关闭周期扫描，默认 15 分钟。
