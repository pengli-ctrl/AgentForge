# AgentForge

![CI](https://img.shields.io/badge/CI-passing-brightgreen)
![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Tests](https://img.shields.io/badge/Tests-466%20passed-brightgreen)
![Code Style](https://img.shields.io/badge/code%20style-black-000000)

> 多Agent编排+治理一体化平台——DAG编排、智能路由、语义缓存、全链路可观测的一站式AI Agent基础设施。

AgentForge 是一个多Agent编排+治理一体化平台，采用三层架构设计（编排层/运行时层/网关层），内置DAG任务引擎（最大50节点）、5模型智能路由、语义缓存（命中率38%）、三级Memory、全链路Trace/Span追踪。支持12类Agent热插拔注册，提供三层超时/四级降级/请求放大管控等生产级可靠性保障。开源项目，466个自动化测试全部通过。

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
│  │CodeReview│  │  Test    │  │   Doc    │  │ Security │  ...×12 │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │         │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘           │
│  统一Agent基类(abc+5接口) · 三级Memory · Tool框架(Function Calling+MCP) │
├─────────────────────────────────────────────────────────────────┤
│                      网 关 层 (AI Gateway)                       │
│  5模型智能路由 · 语义缓存(命中率38%) · Token成本管控 · 全链路Trace  │
│  Qwen3-Pro · GLM-5 · Kimi · MiniMax · DeepSeek-V3              │
└─────────────────────────────────────────────────────────────────┘
```

| 层级 | 职责 | 核心组件 |
|---|---|---|
| **编排层** | 任务拆解、节点调度、数据流转 | DAG任务引擎(Kahn拓扑排序+并行调度), Planner Agent(自动拆解), LoopBlock(循环控制器), ContextStore(节点间数据流转) |
| **运行时层** | Agent执行、Memory管理、工具调用 | 统一Agent基类(abc+5标准接口), 12类Agent热插拔注册, 三级Memory(工作/短期/长期), Tool框架(Function Calling+MCP) |
| **网关层** | 模型路由、缓存、成本管控、可观测 | 5模型智能路由(能力/成本/延迟三维评分), 语义缓存(Embedding>0.92), Token级成本统计+P0-P3预算告警, 全链路Trace/Span(五种Span类型) |

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

## 量化成果

| 指标 | 数值 | 说明 |
|---|---|---|
| LLM调用成本降低 | **68%** | 缓存38%直接省 + 路由优化30% |
| 端到端延迟降低 | **38%** | 缓存跳过推理 + 路由优先低延迟模型 |
| 任务完成率 | **97%** | 15000+请求统计 |
| 级联失败率 | **<0.3%** | 结构化输出+交叉验证+兜底默认值 |
| 缓存命中率 | **38%** | Embedding相似度>0.92 |
| 自动化测试 | **466个** | 全部通过，CI绿灯 |
| Agent类型 | **12类** | 热插拔注册 |
| DAG最大规模 | **50节点** | Kahn拓扑排序+并行调度 |

> 以上数据来自基准测试（2000条标注query）和日常使用（持续3周，累计15000+请求），非商用生产环境。

---

## 技术栈

| 类别 | 技术选型 |
|---|---|
| 语言 | Python 3.10+ |
| LLM推理 | vLLM(私有化部署) + 5 API模型(Qwen3-Pro / GLM-5 / Kimi / MiniMax / DeepSeek-V3) |
| 任务编排 | DAG引擎(Kahn拓扑排序+并行调度) + Planner Agent |
| 事件通信 | Redis Pub/Sub → Kafka |
| 状态存储 | Redis |
| 向量检索 | FAISS |
| 关键词检索 | BM25 (rank_bm25) |
| 代码解析 | tree-sitter |
| 容器化 | Docker / Docker Compose |
| 可观测性 | OpenTelemetry + Prometheus + Grafana |
| 工具协议 | Function Calling + MCP |

---

## 项目结构

```
AgentForge/
├── agentforge/
│   ├── core/                     # 运行时层
│   │   ├── agent.py              # 统一Agent基类(abc+5标准接口)
│   │   ├── memory.py             # 三级Memory(工作/短期/长期)
│   │   ├── tool_framework.py     # Tool框架(Function Calling+MCP)
│   │   ├── agent_registry.py     # Agent注册表(12类热插拔)
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
│   │   ├── output_validator.py   # 输出校验器
│   │   └── conflict_arbiter.py   # 冲突仲裁
│   ├── tools/                    # 工具实现
│   │   ├── code_review_tool.py
│   │   ├── test_execution_tool.py
│   │   ├── security_scan_tool.py
│   │   └── ...
│   ├── agents/                   # Agent实现(12类)
│   │   ├── code_review_agent.py
│   │   ├── test_execution_agent.py
│   │   ├── security_scan_agent.py
│   │   ├── doc_generator_agent.py
│   │   ├── deploy_agent.py
│   │   └── ...
│   └── api/                      # FastAPI入口
│       ├── app.py
│       └── routes/
├── configs/
│   ├── workflows/                # DAG工作流配置
│   └── models.yaml               # 模型配置(5模型)
├── tests/                        # 466个测试
├── deploy/                       # 部署配置
└── ...
```

---

## 快速开始

```python
from agentforge.orchestration import DAGEngine, DAGNode
from agentforge.gateway import AIGateway

# 初始化AI Gateway（5模型路由+语义缓存+成本管控）
gateway = AIGateway(models=["qwen3-pro", "glm-5", "kimi", "minimax", "deepseek-v3"])

# 定义DAG工作流
dag = DAGEngine(max_nodes=50, global_timeout=300)
dag.add_node(DAGNode("code_scan", agent="security-scan",
                     input_mapping={"code": "$input.code"}))
dag.add_node(DAGNode("risk_analysis", agent="risk-analysis",
                     input_mapping={"vulnerabilities": "$ctx.code_scan.output"}))
dag.add_node(DAGNode("fix_plan", agent="fix-generator",
                     input_mapping={"risks": "$ctx.risk_analysis.output"}))
dag.add_edge("code_scan", "risk_analysis")
dag.add_edge("risk_analysis", "fix_plan")

# 执行
result = await dag.execute("task-001", input_data={"code": open("main.py").read()})
print(f"成本: ¥{result.cost:.4f}, 延迟: {result.latency:.1f}s, 完成率: {result.success_rate}")
```

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

## 关于作者

**彭黎** — 8年后端研发，3年团队管理，专注AI Agent架构方向。

- 📝 博客：https://pengli-ctrl.github.io/blog
- 💻 GitHub：https://github.com/pengli-ctrl
- 📧 邮箱：pl2847253@gmail.com
- 📖 掘金：https://juejin.cn/user/4140096632135322

---

## License

[MIT License](LICENSE) © 2024 彭黎
