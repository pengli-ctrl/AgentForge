# AgentForge

![CI](https://github.com/pengli-ctrl/AgentForge/actions/workflows/ci.yml/badge.svg)
![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)
![Tests: 466](https://img.shields.io/badge/tests-466-green.svg)
![Code Style: black](https://img.shields.io/badge/code%20style-black-000000.svg)

> 事件驱动的多 Agent 编排框架——从单 Agent PoC 到事件驱动架构的完整演进实践。

AgentForge 起源于内部代码审查工具，经过 V1（单 Agent PoC）→ V2（串行编排）→ V3（事件驱动）三版架构演进，最终形成了一套基于事件总线、Context Snapshot 隔离和动态路由的多 Agent 编排方案。

## 架构演进时间线

| 阶段 | 时间 | 持续 | 关键产出 |
|------|------|------|---------|
| V1 PoC | 2022.11 - 2022.12 | 3 周 | 单 Agent 代码审查工具上线，验证核心假设 |
| V2 工程化 | 2023.01 - 2023.06 | ~6 个月 | 4 个 Agent 拆分，Orchestrator 编排，上线后 2 次事故 |
| V3 事件驱动 | 2023.07 - 2024.03 | ~9 个月 | 事件总线 + Context Snapshot + 动态路由，稳定运行 |
| 通用化沉淀 | 2024.04 - 2024.08 | ~5 个月 | 多模型适配、Agent SDK、Docker 一键部署 |

## V3 架构总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        接 入 层                                    │
│    API Gateway  ·  Task Router  ·  Result Collector               │
├─────────────────────────────────────────────────────────────────┤
│                    Agent 运 行 时                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐         │
│  │ CodeReview│  │   Test   │  │   Doc    │  │ Security │         │
│  │  Agent   │  │  Agent   │  │  Agent   │  │  Agent   │         │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘         │
│       │              │              │              │               │
├───────┴──────────────┴──────────────┴──────────────┴─────────────┤
│                      事 件 总 线                                    │
│         Publish / Subscribe  ·  Correlation ID  ·  Routing        │
├─────────────────────────────────────────────────────────────────┤
│                    基 础 设 施 层                                   │
│  State Store (Redis)  ·  Tool Sandbox (Docker)  ·  LLM Gateway   │
└─────────────────────────────────────────────────────────────────┘
```

四层架构：

| 层级 | 职责 | 核心组件 |
|------|------|---------|
| **接入层** | 请求认证、任务路由、结果聚合 | API Gateway, Task Router, Result Collector |
| **Agent 运行时** | 独立的 Agent 执行环境，状态完全隔离 | CodeReview / Test / Doc / Deploy Agent |
| **事件总线** | 异步事件分发，Agent 间零直接依赖 | Event Bus (Publish/Subscribe) |
| **基础设施层** | 共享存储、工具执行、LLM 推理 | State Store(Redis), Tool Sandbox(Docker), LLM Gateway |

## 架构演进：V1 → V2 → V3

三个版本的代码都在仓库中，展示了完整的演进路径：

### V1：单 Agent PoC（2022.11-12，3周）

- **代码**：[`agentforge/core/v1_agent_engine.py`](agentforge/core/v1_agent_engine.py)
- **架构**：单 Agent + ReAct 循环（思考→行动→观察→再思考）
- **核心设计**：BaseTool 统一工具抽象，被 V2/V3 直接继承
- **验证结果**：工具调用成功率 94%，代码审查采纳率 67%，日活 200+
- **天花板**：3个以上工具调用后 Prompt 超 32K，无法拆分新 Agent

### V2：多 Agent 串行编排（2023.01-06，6个月）

- **代码**：[`agentforge/core/orchestrator.py`](agentforge/core/orchestrator.py)（已废弃，保留参考）
- **架构**：Agent 拆分 + Orchestrator 串行编排 + Redis 共享状态 + YAML 配置化
- **解决的问题**：Agent 拆分，每个 Prompt 控制在 8K 以内，耗时降至 2 分钟
- **引入的问题**：Orchestrator 上帝对象（2000+行）、共享状态定时炸弹、静态 pipeline 无法分支
- **事故驱动**：Redis 重启丢状态 + 2000行大方法变量名事故 → 推动V3重构

### V3：事件驱动架构（2023.07-2024.03，9个月）

- **代码**：[`agentforge/core/agent.py`](agentforge/core/agent.py) + [`agentforge/core/event_bus.py`](agentforge/core/event_bus.py) + [`agentforge/core/context_snapshot.py`](agentforge/core/context_snapshot.py)
- **架构**：事件总线 + Context Snapshot 隔离 + YAML 动态路由
- **核心突破**：Agent 间零直接依赖、状态完全隔离、新 Agent 只需订阅事件
- **V2→V3 迁移**：灰度切换（8周，2人），先建事件总线→逐个Agent迁移→并行2周→下线V2

## 核心设计点

### 1. 事件总线

所有 Agent 通过事件总线通信，不直接调用其他 Agent。每个 Agent 事件都携带 `correlation_id`（同一工作流共享）和 `context_snapshot`（上下文快照）。Agent 数量从 4 个增长到 10+ 个时，事件驱动把 N*(N-1) 条调用链路降为 N。

### 2. Context Snapshot 隔离

每个 Agent 在处理事件时，只从 `context_snapshot` 中提取自己需要的上下文，而不是接收全量数据。采用读时快照——事件发送时冻结一份上下文副本，接收方基于这份冻结副本工作。发送方决定下游能看什么，一举解决了共享状态无限膨胀和 Prompt 爆炸问题。

### 3. 动态路由引擎

编排不再是静态 pipeline，而是基于事件路由的条件分支引擎，通过 YAML 配置实现动态分支。代码审查发现安全问题→先跑安全扫描，测试不通过→重新审查——这种分支逻辑在 YAML 中配置，不改代码。

### 4. 工具抽象层

`BaseTool` 统一接口从 V1 PoC 阶段就认真设计，后来直接被 V2/V3 继承。每个工具有 JSON Schema 描述、异步执行、标准化结果输出，Agent 通过工具注册表统一管理所有工具调用。

## 量化效果

### 技术指标

| 指标 | V1 单Agent | V2 串行编排 | V3 事件驱动 |
|------|-----------|-----------|------------|
| 单次任务平均耗时 | 4.2 min | 2.8 min | **0.9 min** |
| Agent 平均 Prompt 长度 | 45K tokens | 12K tokens | **6K tokens** |
| LLM 幻觉率 | 23% | 11% | **3%** |
| 单 Agent 故障影响范围 | 全部任务失败 | 当前 pipeline 失败 | **仅当前 Agent** |
| 新 Agent 接入成本 | 重写全部逻辑 | 修改 Orchestrator | **只需订阅事件** |

### 业务影响

| 维度 | V2 | V3 | 变化 |
|------|----|----|------|
| 日均处理任务量 | 120 个 | 380 个 | **+217%** |
| 研发交付周期 | 平均 45 min/PR | 平均 15 min/PR | **-67%** |
| LLM 推理成本（月） | ¥8,400 | ¥3,200 | **-62%** |
| 线上故障恢复时间 | 平均 30 min | 平均 5 min | **-83%** |
| 新 Agent 上线周期 | 2-3 天 | 2-3 小时 | **从人天级到小时级** |

> **数据来源说明**：以上数据来自内部开发工具环境（2024 年 Q2-Q3 测量，日均活跃用户约 200），非商用生产环境流量。LLM 幻觉率从每版上线后第一周随机抽 200 样本，2 名高级工程师独立评审（Kappa 一致性 0.78）；任务耗时取 P50 值。

## 技术栈

| 类别 | 技术选型 |
|------|---------|
| 语言 | Python 3.10+ |
| LLM 推理 | vLLM (私有化部署) |
| 事件总线 | Redis Pub/Sub → Kafka |
| 状态存储 | Redis |
| 向量检索 | FAISS |
| 关键词检索 | BM25 (rank_bm25) |
| 代码解析 | tree-sitter |
| 容器化 | Docker / Docker Compose |
| 可观测性 | OpenTelemetry |
| 工作流配置 | YAML |

## 项目结构

```
AgentForge/
├── agentforge/
│   ├── __init__.py               # 包入口，版本信息
│   ├── core/                     # 核心模块
│   │   ├── __init__.py
│   │   ├── base_tool.py          # BaseTool 抽象基类
│   │   ├── agent.py              # Agent 基类 + execute 方法
│   │   ├── event_bus.py          # 事件总线（publish/subscribe）
│   │   ├── event_types.py        # 事件类型定义
│   │   ├── context_snapshot.py   # Context Snapshot 管理器
│   │   ├── orchestrator.py       # V2 串行编排器（deprecated）
│   │   ├── v1_agent_engine.py    # V1 单 Agent 引擎（参考）
│   │   └── circuit_breaker.py    # 熔断器（博客06 Layer 1）
│   ├── llm/                      # LLM 网关
│   │   ├── __init__.py
│   │   └── gateway.py            # LLM Gateway 抽象 + VLLMGateway
│   ├── tools/                    # 工具层
│   │   ├── __init__.py
│   │   ├── code_review_tool.py   # 代码审查工具
│   │   ├── test_execution_tool.py # 测试执行工具
│   │   ├── doc_generation_tool.py # 文档生成工具
│   │   ├── security_scan_tool.py # 安全扫描工具
│   │   ├── git_tool.py           # Git 操作工具
│   │   └── file_io_tool.py       # 文件读写工具
│   ├── agents/                   # Agent 实现
│   │   ├── __init__.py
│   │   ├── code_review_agent.py  # 代码审查 Agent
│   │   ├── test_execution_agent.py
│   │   ├── doc_generator_agent.py
│   │   ├── security_scan_agent.py # 安全扫描 Agent
│   │   └── deploy_agent.py       # 部署 Agent
│   ├── rag/                      # RAG 工程化
│   │   ├── __init__.py
│   │   ├── ast_chunker.py        # AST 感知分块器
│   │   ├── hybrid_retriever.py   # BM25+FAISS 混合检索
│   │   ├── reranker.py           # LLM Reranker 精排
│   │   ├── evaluation.py         # RAGAS评估框架
│   │   └── hallucination_guard.py # 幻觉防护层
│   ├── safety/                   # 四层容错防线
│   │   ├── __init__.py
│   │   ├── trust_boundary.py     # Trust Boundary 确定性校验
│   │   ├── conflict_arbiter.py   # 冲突仲裁器
│   │   ├── aimd_controller.py    # AIMD 拥塞控制
│   │   └── pulse_shaper.py       # 脉冲整形器
│   ├── api/                      # API 层（FastAPI）
│   │   ├── __init__.py
│   │   ├── app.py                # FastAPI 应用入口
│   │   ├── routes/               # REST 路由
│   │   │   ├── __init__.py
│   │   │   ├── tasks.py          # 任务管理接口
│   │   │   ├── agents.py         # Agent 管理接口
│   │   │   └── metrics.py        # Prometheus 指标接口
│   │   └── middleware/           # 中间件
│   │       ├── __init__.py
│   │       ├── auth.py           # API Key 认证
│   │       ├── rate_limit.py     # 令牌桶限流
│   │       └── error_handler.py  # 统一错误处理
│   ├── storage/                  # 存储层
│   │   ├── __init__.py
│   │   ├── task_store.py         # 任务持久化（MySQL）
│   │   ├── trace_store.py        # Trace 数据存储
│   │   ├── redis_state.py        # Redis 状态存储封装
│   │   └── models/               # 数据模型
│   │       ├── __init__.py
│   │       ├── task.py           # Task 数据模型 + 状态机
│   │       └── trace.py          # Trace 数据模型
│   ├── observability/            # 可观测性
│   │   ├── __init__.py
│   │   ├── metrics.py            # Prometheus 指标定义
│   │   ├── tracing.py            # 分布式追踪
│   │   └── logger.py             # 结构化 JSON 日志
│   ├── workflow/                 # 工作流引擎
│   │   ├── __init__.py
│   │   ├── engine.py             # YAML 解析 + 条件路由执行
│   │   ├── registry.py           # Agent 注册表
│   │   ├── conditions.py         # 条件表达式解析器
│   │   └── llm_router.py         # LLM路由器
│   ├── prompts/                  # Prompt 管理
│   │   ├── __init__.py
│   │   ├── manager.py            # Prompt 模板管理器
│   │   └── templates/            # Prompt 模板文件
│   │       ├── code_review.txt
│   │       ├── test_execution.txt
│   │       ├── doc_generation.txt
│   │       └── security_scan.txt
│   ├── sdk/                      # Python SDK
│   │   ├── __init__.py
│   │   ├── client.py             # AgentForgeClient
│   │   └── builder.py            # AgentBuilder（流式 API）
│   └── cli/                      # 命令行工具
│       ├── __init__.py
│       └── main.py               # CLI 入口
├── configs/
│   ├── workflows/
│   │   ├── code-review-pipeline.yaml
│   │   └── security-review-pipeline.yaml
│   ├── logging.yaml              # 日志配置（控制台+文件轮转）
│   ├── dev/
│   │   └── settings.yaml         # 开发环境配置
│   └── prod/
│       └── settings.yaml         # 生产环境配置
├── deploy/
│   ├── prometheus.yml            # Prometheus 抓取配置
│   └── grafana/
│       └── agentforge-dashboard.json  # Grafana 仪表盘
├── migrations/
│   └── 001_init.sql              # 数据库初始化 SQL
├── examples/
│   ├── quickstart.py
│   └── e2e_assembly.py            # 端到端组装示例
├── tests/                        # 测试
│   ├── __init__.py
│   ├── conftest.py               # pytest fixtures
│   ├── unit/                     # 单元测试
│   │   ├── __init__.py
│   │   ├── test_event_bus.py
│   │   ├── test_context_snapshot.py
│   │   ├── test_circuit_breaker.py
│   │   ├── test_workflow_engine.py
│   │   ├── test_llm_router.py
│   │   ├── test_hybrid_retriever.py
│   │   ├── test_reranker.py
│   │   ├── test_evaluation.py
│   │   ├── test_trust_boundary.py
│   │   ├── test_conflict_arbiter.py
│   │   ├── test_aimd_controller.py
│   │   ├── test_pulse_shaper.py
│   │   ├── test_ast_chunker.py
│   │   ├── test_hallucination_guard.py
│   │   ├── test_v1_agent_engine.py
│   │   ├── test_agent_react.py
│   │   ├── test_base_tool.py
│   │   ├── test_orchestrator.py
│   │   ├── test_llm_gateway.py
│   │   ├── test_api_app.py
│   │   ├── test_task_store.py
│   │   ├── test_redis_state.py
│   │   ├── test_sdk_client.py
│   │   ├── test_cli.py
│   │   ├── test_git_tool.py
│   │   ├── test_code_review_tool.py
│   │   └── test_test_execution_tool.py
│   └── integration/              # 集成测试
│       ├── __init__.py
│       └── test_code_review_pipeline.py
├── docs/
│   └── architecture.md
├── .github/
│   ├── workflows/
│   │   └── ci.yml                # CI 流水线
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   ├── feature_request.md
│   │   └── config.yml
│   ├── PULL_REQUEST_TEMPLATE.md
│   ├── CODEOWNERS
│   └── dependabot.yml            # 依赖自动更新
├── .dockerignore
├── .env.example                  # 环境变量模板
├── .pre-commit-config.yaml       # pre-commit 钩子配置
├── .gitignore
├── Dockerfile                    # 多阶段构建
├── docker-compose.yml            # 完整部署编排
├── Makefile                      # 常用命令
├── pyproject.toml                # 项目配置
├── CONTRIBUTING.md               # 贡献指南
├── SECURITY.md                   # 安全政策
├── CHANGELOG.md                  # 变更记录
├── requirements.txt
├── requirements-dev.txt          # 开发依赖
└── LICENSE
```

## 快速开始

```python
from agentforge.core.event_bus import EventBus
from agentforge.core.event_types import EventType, AgentEvent
from agentforge.agents.code_review_agent import CodeReviewAgent
from agentforge.agents.test_execution_agent import TestExecutionAgent

# 初始化事件总线
bus = EventBus(backend="redis")

# 注册 Agent
code_review = CodeReviewAgent(llm_gateway=my_llm)
test_agent = TestExecutionAgent(llm_gateway=my_llm)

bus.subscribe(EventType.TASK_SUBMITTED, code_review)
bus.subscribe(EventType.AGENT_COMPLETED, test_agent)

# 发布任务
await bus.publish(AgentEvent(
    event_type=EventType.TASK_SUBMITTED,
    source_agent="api-gateway",
    payload={"task": "review PR #42"},
    correlation_id="task-001",
    context_snapshot={},
))
```

更多示例见 [examples/quickstart.py](examples/quickstart.py)。

## API 文档

启动 API 服务后，访问 Swagger UI：`http://localhost:8000/docs`

### 主要 API 端点

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/v1/tasks` | 提交新任务 |
| GET | `/api/v1/tasks` | 查询任务列表 |
| GET | `/api/v1/tasks/{task_id}` | 查询任务详情 |
| GET | `/api/v1/tasks/{task_id}/result` | 获取任务结果 |
| POST | `/api/v1/tasks/{task_id}/cancel` | 取消任务 |
| GET | `/api/v1/agents` | 查询 Agent 列表 |
| GET | `/api/v1/agents/{name}` | 查询 Agent 详情 |
| GET | `/api/v1/agents/health` | Agent 健康检查 |
| GET | `/metrics` | Prometheus 指标 |
| GET | `/health` | 服务健康检查 |

### SDK 使用

```python
from agentforge.sdk import AgentForgeClient, AgentBuilder

# 使用 SDK 客户端
client = AgentForgeClient(base_url="http://localhost:8000", api_key="...")
task = await client.submit_task(
    workflow_name="code-review-pipeline",
    input_data={"code_content": "def add(a, b): return a + b"},
)

# 使用 Agent 构建器
from agentforge.tools import CodeReviewTool, SecurityScanTool
from agentforge.llm import VLLMGateway

agent = (
    AgentBuilder()
    .with_llm(VLLMGateway(endpoint="http://localhost:8000/v1"))
    .with_tool(CodeReviewTool())
    .with_tool(SecurityScanTool())
    .with_prompt("code_review")
    .with_name("my-reviewer")
    .build()
)
```

### CLI 使用

```bash
# 提交任务
agentforge submit code-review-pipeline --input '{"code_content": "print(1)"}'

# 查看任务状态
agentforge status <task_id>

# 查看 Agent 列表
agentforge agents

# 启动 API 服务
agentforge serve --host 0.0.0.0 --port 8000
```

## 部署

### Docker 部署

```bash
# 构建镜像
docker build -t agentforge:latest .

# 启动完整服务（app + redis + mysql + kafka）
docker-compose up -d

# 查看服务状态
docker-compose ps

# 停止服务
docker-compose down
```

### 手动部署

```bash
# 安装依赖
make install

# 启动 Redis
redis-server

# 启动 API 服务
make run

# 或使用 uvicorn 直接启动
uvicorn agentforge.api.app:app --host 0.0.0.0 --port 8000
```

### 监控配置（Prometheus + Grafana）

AgentForge 内置 `/metrics` 端点输出 Prometheus 格式指标。部署配置文件位于 `deploy/` 目录。

```bash
# 1. 启动 Prometheus（使用 deploy/prometheus.yml 配置）
prometheus --config.file=deploy/prometheus.yml

# 2. 导入 Grafana 仪表盘
#    在 Grafana 中导入 deploy/grafana/agentforge-dashboard.json
#    数据源选择 Prometheus
```

仪表盘包含以下面板：
- **任务吞吐量**（counter）— 每秒处理的任务数
- **活跃 Agent 数**（gauge）— 当前活跃的 Agent 实例
- **事件总线延迟**（histogram）— 事件从发布到消费的 p95 延迟
- **LLM 调用成功率** — LLM 请求的成功率百分比
- **AIMD 窗口大小** — 拥塞控制器的窗口变化趋势
- **错误率** — 任务失败率百分比

### 开发

```bash
# 安装开发依赖
pip install -r requirements-dev.txt
# 或使用 Makefile
make dev-install

# 安装 pre-commit 钩子（首次开发时执行一次）
pre-commit install

# 运行测试
make test

# 代码格式化
make format

# 代码检查
make lint

# 手动运行 pre-commit（检查所有文件）
pre-commit run --all-files
```

开发依赖包括：pytest、pytest-asyncio、pytest-cov、black、isort、flake8、mypy、fakeredis、httpx。
pre-commit 钩子会在每次 git commit 时自动运行代码格式化和检查，配置见 `.pre-commit-config.yaml`。

## 技术文章

本项目的架构演进过程在以下博客文章中有完整记录：

| 文章 | 主题 | 链接 |
|------|------|------|
| 架构演进实战 | V1→V2→V3 三版架构演进全记录 | [阅读](https://pengli-ctrl.github.io/blog/posts/04-agentforge-architecture-evolution) |
| 编排引擎演进 | 从规则引擎到 LLM 动态编排 | [阅读](https://pengli-ctrl.github.io/blog/posts/05-orchestration-engine-evolution) |
| 故障模式推演 | 四类典型风险的根因分析与容错设计 | [阅读](https://pengli-ctrl.github.io/blog/posts/06-production-failure-patterns) |
| RAG 工程化 | 幻觉率从 46% 降到 16.2% 的五层防护体系 | [阅读](https://pengli-ctrl.github.io/blog/posts/01-rag-engineering-hallucination-prevention) |

## 关于作者

**彭黎** — 8 年后端研发，3 年团队管理，专注 AI Agent 架构方向。

- 📝 博客：[https://pengli-ctrl.github.io/blog](https://pengli-ctrl.github.io/blog)
- 💻 GitHub：[github.com/pengli-ctrl](https://github.com/pengli-ctrl)
- 📧 邮箱：pl2847253@gmail.com
- 📖 掘金：[https://juejin.cn/user/4140096632135322](https://juejin.cn/user/4140096632135322)

## License

[MIT License](LICENSE) © 2024 彭黎
