# Support Module

## 模块定位

Support 的 domain、application、infrastructure、api 和 workflow 已物理迁入本模块。
平台 `ServiceContainer` 不再持有 Ticket 仓储、分类器、回复连接器或 Support 业务服务；
这些依赖由 composition root 注入，SupportModule 自己完成业务服务图装配。

## 对外入口

- 新模块入口：`/v1/support/tickets/*`、`/v1/support/events/im`、`/v1/support/workflows/support`
- 兼容入口：`/v1/tickets/*`、`/v1/events/im`、`/v1/workflows/support`
- Temporal Task Queue：`support-copilot`

## 已迁入

- Ticket / TicketStatus / PriorityLevel 兼容别名
- SupportTicketService
- SupportTicketProcessingService
- ReplyDraftService
- TicketWritebackService
- Support Router / Feishu Router
- Ticket Repository / TicketRecord
- Feishu Reply Connector
- Support Temporal Workflow / Activities
- 来源感知的工单路由与 Priority / Queue 元数据
- 工单 SLA 截止时间、关闭结果和跨租户指标
- 财务发票门禁专用队列 `finance-invoice-gate`
- 工单负责人 `assignee_id` 与 Console 运营筛选
- SLA due-soon / breached 事件、周期扫描和逾期自动升级
- 内置 Memory/Webhook 通知投递与通知证据
- `tenant_modules` 租户级启停、版本化配置和部署默认值
- 模块 schema migration、租户隔离测试与 SaaS/私有化装配验证
- `ModuleManifest` / `ModuleRuntime` 契约校验和模块 Task Queue

## 模块装配约束

- Application 层只依赖 SDK Port 和本模块 Port。
- 高风险写回通过 `PolicyPort`、`AuditPort`、`RbacPort` 组合，不直接持有平台具体实现。
- Infrastructure 层可以使用共享数据库 Base 和 Outbox 模型。
- 模块禁止导入 `platform.runtime`、`platform.application`、`platform.api` 或平台 `core`。
- 测试通过 ModuleRuntime 获取业务服务，不通过全局 ServiceContainer 取 Support 字段。

## SLA 配置

```text
AGENTFORGE_SUPPORT_DEFAULT_SLA_MINUTES=480
AGENTFORGE_SUPPORT_SLA_DUE_SOON_SECONDS=900
AGENTFORGE_SUPPORT_INVOICE_GATE_TEAM=finance-invoice-gate
AGENTFORGE_SUPPORT_INVOICE_GATE_SLA_MINUTES=60
AGENTFORGE_SUPPORT_INVOICE_GATE_ASSIGNEE=finance-bot
AGENTFORGE_SUPPORT_SLA_SWEEP_MINUTES=5
AGENTFORGE_SUPPORT_SLA_ESCALATION_ASSIGNEE=sla-manager
AGENTFORGE_SUPPORT_NOTIFICATION_TARGET=finance-room
AGENTFORGE_SUPPORT_NOTIFICATION_WEBHOOK_URL=https://hooks.example.com/agentforge
AGENTFORGE_SUPPORT_NOTIFICATION_WEBHOOK_TOKEN=replace-me
AGENTFORGE_SUPPORT_NOTIFICATION_TIMEOUT_SECONDS=10
```

Console 支持按 `assigned_team`、`assignee_id`、`queue`、`overdue`、`due_before` 过滤工单，可直接形成财务专用队列、个人待办和逾期视图。

## 当前边界与后续

- Feishu Router 的加密、verification token 和签名配置仍由平台 composition root 传入；后续可进一步收敛为模块配置声明。
- 更细粒度的组织/团队通知策略仍依赖客户 Connector 和外部消息系统配置。
