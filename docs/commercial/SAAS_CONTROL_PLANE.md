# AgentForge SaaS 控制面

## 1. 租户生命周期

```text
provisioning -> active -> suspended -> active
                         └--------> cancelled
```

- `provisioning`：创建租户账号并应用套餐；模块配置或配额初始化失败时进入 `cancelled`。
- `active`：允许访问已启用模块并记录用量。
- `suspended`：模块 API 在租户边界 fail-closed；恢复后回到 `active`。
- `cancelled`：停止所有模块，保留生命周期审计和事件记录。

创建租户：

```http
POST /v1/admin/tenants
{
  "tenant_id": "tenant-a",
  "name": "Example Customer",
  "plan_name": "professional",
  "actor_id": "admin-1"
}
```

终止租户必须同时提交原因，并将 `confirmation` 设置为目标 `tenant_id`：

```http
POST /v1/admin/tenants/tenant-a/cancel
{
  "actor_id": "admin-1",
  "reason": "contract terminated",
  "confirmation": "tenant-a"
}
```

所有生命周期变更写入 Audit，并发布对应 Outbox 事件。管理员接口使用 `X-Admin-Key` 鉴权。

## 2. 默认套餐

| 套餐 | 模块 | OCR 页 | 模型 Token | Workflow | 存储 | 通知 | 超额策略 |
|---|---|---:|---:|---:|---:|---:|---|
| `starter` | support | 50 | 100,000 | 1,000 | 1 GiB | 1,000 | `warn` |
| `professional` | support, expense | 2,000 | 5,000,000 | 50,000 | 50 GiB | 50,000 | `allow` |
| `enterprise` | support, expense, asset | 不限 | 不限 | 不限 | 不限 | 不限 | `allow` |
| `private` | support, expense, asset | 不限 | 不限 | 不限 | 不限 | 不限 | `allow` |

说明：

- 限额 `0` 表示不限量。
- `private` 的 base fee 和 automation quota 均为 `0`，用于私有化合同交付。
- 套餐包含租户模块开关和模块默认配置；切换套餐会重新应用模块和配置。
- 默认套餐通过 `AGENTFORGE_SAAS_DEFAULT_PLAN=starter` 指定。

可通过 `AGENTFORGE_SAAS_PLANS_JSON` 覆盖或补充套餐。该变量必须是 JSON 数组，每个对象至少包含 `name`、`display_name`、`modules` 等 `PlanDefinition` 字段。

## 3. 计量指标

| 指标 | 来源 |
|---|---|
| `ocr_pages` | OCR 提取结果页数，默认最小计 1 页 |
| `model_tokens` | 配额感知模型网关记录的 input/output token |
| `workflow_executions` | Temporal 启动 Workflow 时记录一次 |
| `storage_bytes` | 附件和分片上传写入对象存储的字节数 |
| `notification_count` | Support 通知成功投递次数 |

业务调用通过 `UsageMeteringAdapter` 记录，采用 best-effort 语义：计量失败只记录告警，不中断主业务。超过套餐硬门禁时，由租户状态和配额边界拒绝后续请求。

手动记录用量：

```http
POST /v1/admin/tenants/tenant-a/usage
{
  "metric": "ocr_pages",
  "quantity": 120,
  "source": "ocr-worker",
  "idempotency_key": "ocr-job-123",
  "metadata": {"job_id": "job-123"}
}
```

`idempotency_key` 在租户和指标范围内幂等。重复提交不会重复计量，响应中的 `duplicate` 为 `true`。

查询：

```text
GET /v1/admin/tenants/{tenant_id}/usage
GET /v1/admin/tenants/{tenant_id}/usage/export
GET /v1/admin/tenants/{tenant_id}/usage/alerts
```

`start` 和 `end` 使用 ISO 时间格式。未指定时使用当前账单周期。

## 4. 超额与告警

- `block`：超过限额后拒绝本次计量，返回 `blocked=true`；写入 `tenant.usage.blocked` Audit 并发布 `platform.tenant.usage.overage.v1`。
- `warn`：允许调用但产生 overage，记录 Audit/Outbox，并可通过告警查询发现。
- `allow`：允许调用并记录 overage，不做硬阻断。

告警阈值：

- 使用率达到 **80%**：`warning`
- 使用率达到 **100%**：`critical`

告警包含租户、指标、已用量、限额、比例和状态。

## 5. 账单

```text
GET /v1/admin/tenants/{tenant_id}/invoice?format=json
GET /v1/admin/tenants/{tenant_id}/invoice?format=csv
```

账单由 `ConfigBillingAdapter` 生成，包括：

- 套餐基础费；
- 各计量指标用量与单价；
- 明细金额和总金额；
- 账单周期和币种。

`BillingAdapterPort` 是账单适配边界。生产可替换为 Stripe、ERP 或财务系统 Adapter；当前配置适配器用于可重复的本地和私有化账单计算，不会自动扣款。

## 6. 运营总览

```text
GET /v1/admin/operations/overview
```

返回：

- 租户总数和 active/suspended/cancelled 数量；
- 所有租户的用量汇总；
- 各租户套餐、状态和告警数量；
- 当前告警列表；
- Outbox failed/DLQ 事件。

该接口用于运营控制台和日常巡检，不替代完整 BI 或计费系统。

## 7. 主要 API

```text
GET  /v1/admin/plans
GET  /v1/admin/tenants
POST /v1/admin/tenants
GET  /v1/admin/tenants/{tenant_id}
POST /v1/admin/tenants/{tenant_id}/suspend
POST /v1/admin/tenants/{tenant_id}/resume
POST /v1/admin/tenants/{tenant_id}/cancel
POST /v1/admin/tenants/{tenant_id}/plan
POST /v1/admin/tenants/{tenant_id}/usage
GET  /v1/admin/tenants/{tenant_id}/usage
GET  /v1/admin/tenants/{tenant_id}/usage/export
GET  /v1/admin/tenants/{tenant_id}/usage/alerts
GET  /v1/admin/tenants/{tenant_id}/invoice
GET  /v1/admin/operations/overview
```

## 8. 配置

```text
AGENTFORGE_DELIVERY_MODE=saas|private
AGENTFORGE_SAAS_DEFAULT_PLAN=starter
AGENTFORGE_SAAS_PLANS_JSON=[]
```

- `delivery_mode=private` 用于私有化交付标识和运营配置。
- 套餐覆盖必须通过启动验证；未知指标或非法字段会导致启动失败。
- 租户配置中的敏感值只能使用 `secret_refs`，不能写入明文。

## 9. 当前边界

- 账单适配器不会自动执行支付或对接外部发票系统。
- 用量记录按当前数据库实现持久化；跨区域汇总和大规模数据仓库同步尚未实现。
- 部门/项目级预算和分账尚未实现。
- 生产环境应将管理员接口置于受控运维网络，并通过反向代理、WAF 和企业 IdP 进一步加固。