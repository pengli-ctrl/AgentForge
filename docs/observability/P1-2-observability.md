# P1-2 可观测闭环：LLM 埋点 + trace 视图 + OTLP/Langfuse 接线

## 目标与定位

把平台的 **LLM 调用链路**从"只对任务本身可观测"补全为**对调用可观测**：每次推理都能看到用了哪个模型、多少 token、成本、耗时、属于哪个租户/工单，并能在 dashboard 回查。这是生产可靠性闭环的硬证据。

### 落地约束（重要）

- 开发/本地环境**无 Docker**，无法真正自托管 Langfuse（其运行需要 Postgres + Redis + 自建 UI）。
- 因此 P1-2 在本仓库落地为两段：
  1. **进程内 trace 闭环（本次已实现）**：LLM 调用被记录进 `TraceRecorder`，可通过 `/v1/console/traces` 查询，不依赖任何外部服务，离线/单机即可验证。
  2. **OTLP/Langfuse 接线（配置 + 文档）**：`settings` 已内置 `otel_exporter_otlp_endpoint` / `langfuse_host`，生产接 OTel Collector 或 Langfuse 自托管时，把采集到的 span/trace 导出即可，无需改业务代码。
- 这符合仓库"仅做本地闭环、不依赖外部"的原则，同时保留接成熟可观测件（Langfuse/OTel）的升级路径。

## 已实现的能力

### 1. LLM 埋点（`agentforge/platform/infrastructure/llm/`）

- `StaticModelGateway`（本地回归用）与 `LiteLLMModelGateway`（真实 LLM）在每次 `complete` 成功返回时，构造一条 `TraceRecord` 写入注入的 `TraceRecorder`。
- 记录字段：`trace_id`、`tenant_id`、`model`、`provider`、`input_tokens`、`output_tokens`、`cost_amount`、`latency_ms`、`status`、`error`、`created_at`。
- `trace_id` / `tenant_id` 由 `ReplyDraftService.create_draft` 从工单处理链路传入 `ModelRequest.metadata`，实现**工单 → 推理调用**的关联。

### 2. 进程内 TraceRecorder（`agentforge/platform/observability/trace_recorder.py`）

- 有界内存队列，`max_records` 默认 1000，FIFO 淘汰，防止无界增长。
- 提供：
  - `record(record)`：写入一条 trace。
  - `list_recent(tenant_id=None)`：返回最近记录（可租户过滤，最新在前）。
  - `summary(tenant_id)`：聚合 `count / total_cost / total_latency_ms / avg_latency_ms / ok_rate` + 明细 `records`。

### 3. dashboard trace 视图（`agentforge/platform/application/dashboard_service.py`）

- `DashboardService.recent_traces(tenant_id)` 把 recorder 的 summary 原样暴露给上层。

### 4. HTTP 端点（`agentforge/platform/api/console_router.py`）

```
GET /v1/console/traces?tenant_id=<tenant>
```

返回该租户最近一次 LLM 调用的追踪明细与聚合统计（成本、平均延迟、成功率、token 数）。

## trace→eval 闭环

`TraceRecorder` 与平台已有的**质量门禁（quality gate）**、**回归评估（regression）** 属于同一可观测主线：

- 每次真实/回归推理都有 trace 记录的 **cost + latency + ok_rate** 可量化。
- 配合 P0-5 的质量门禁（BLOCK/HOLD/RELEASE），可用"成本 + 质量"双轴评估模型变更。

`/v1/console/traces` 提供的是**原始调用证据**，无论后续是否接入外部 UI，这条闭环本身完整可回查。

## 生产接线：OTLP / Langfuse

### 方案 A：接标准 OTel Collector（推荐，成熟件、免自研 UI）

1. 部署 OTel Collector 作为接收端。
2. 在 `settings.py` 设置：
   ```yaml
   AGENTFORGE_OTEL_EXPORTER_OTLP_ENDPOINT: http://otel-collector:4317
   ```
3. 平台现有的 `agentforge/platform/observability/tracing.py`（`configure_tracing`) 已支持 exporter，采集到的 LLM span（成本/延迟/token 属性）统一导出。
4. collector 可下行接 Grafana Tempo / Jaeger / Langfuse。

### 方案 B：接自托管/云 Langfuse

Langfuse 通过 OTLP 兼容 intake，仓库保留 `langfuse_host` 配置位：

```yaml
AGENTFORGE_LANGFUSE_HOST: https://cloud.langfuse.com   # 或自托管
AGENTFORGE_OTEL_EXPORTER_OTLP_ENDPOINT: <langfuse otlp intake>
```

把平台 OTel span 的 `langfuse.*` 属性（model/token/prompt 等）接入后，即可在 Langfuse UI 获得完整的 trace→eval 观测与成本看板，而**无需在本仓库自研可观测 UI**。

> 说明：本仓库未内置 Langfuse SDK 导出器，是因本地无 Docker 无法验证端到端。生产需要时，在 `tracing.py` 增加一个导出到 Langfuse 的 `SpanProcessor` 即可，业务零改动。

## 复现 / 验证

```bash
# 跑 trace 闭环测试
python -m pytest tests/platform/test_observability_trace.py -q

# 本地起服务后查询某租户的推理 trace
curl "http://localhost:8000/v1/console/traces?tenant_id=tenant-a"
```

## 验收清单

- [x] 每次 LLM 调用被记录（model/tokens/cost/latency/tenant/work-order 关联）
- [x] 有界内存，无无限增长
- [x] dashboard `/v1/console/traces` 端到端可用（5 项闭测试通过）
- [x] 工单 → 推理 trace_id 传播
- [x] OTLP/Langfuse 接线方式文档化，本地零外部依赖闭环成立