# AgentForge 架构设计文档

## 概述

AgentForge 是一个事件驱动的多 Agent 编排框架，经历了三版架构演进：

1. **V1 PoC**（2022.11-2022.12）：单 Agent + 工具调用循环，验证核心假设
2. **V2 工程化**（2023.01-2023.06）：多 Agent 拆分 + Orchestrator 串行编排
3. **V3 事件驱动**（2023.07-2024.03）：事件总线 + Context Snapshot + 动态路由

## V3 架构

### 四层架构

| 层级 | 职责 | 核心组件 |
|------|------|---------|
| 接入层 | 请求认证、任务路由、结果聚合 | API Gateway, Task Router, Result Collector |
| Agent 运行时 | 独立的 Agent 执行环境，状态完全隔离 | CodeReview / Test / Doc / Deploy Agent |
| 事件总线 | 异步事件分发，Agent 间零直接依赖 | Event Bus (Publish/Subscribe) |
| 基础设施层 | 共享存储、工具执行、LLM 推理 | State Store(Redis), Tool Sandbox(Docker), LLM Gateway |

### 核心设计

#### 1. 事件总线

所有 Agent 通过事件总线通信，不直接调用其他 Agent。每个事件携带 `correlation_id`（同一工作流共享）和 `context_snapshot`（上下文快照）。

#### 2. Context Snapshot 隔离

读时快照——事件发送时冻结一份上下文副本，接收方基于这份冻结副本工作。每个 Agent 只从快照中提取自己需要的上下文，不接收全量数据。

#### 3. 动态路由引擎

基于事件路由的条件分支引擎，通过 YAML 配置实现动态分支。代码审查发现安全问题→先跑安全扫描，测试不通过→重新审查。

#### 4. 工具抽象层

`BaseTool` 统一接口从 V1 PoC 阶段就认真设计，后来直接被 V2/V3 继承。

### 四层容错防线

| 层级 | 机制 |
|------|------|
| Layer 1: Agent 内防护 | 并发限制、超时控制、熔断器、本地重试 |
| Layer 2: Agent 间防护 | Trust Boundary、异源验证、脉冲整形 |
| Layer 3: 全局保护 | 冲突仲裁、AIMD 拥塞控制、优先级队列 |
| Layer 4: 全链路可观测性 | OpenTelemetry 分布式 Trace、拥塞检测、异常检测 |

## 技术选型

| 类别 | 选型 | 原因 |
|------|------|------|
| 事件总线 | Redis Pub/Sub → Kafka | 初期 Redis 够用，规模增大后迁移 Kafka |
| 状态存储 | Redis | 团队熟悉、部署简单 |
| 向量检索 | FAISS | 开源、高性能 |
| 关键词检索 | BM25 (rank_bm25) | 精确匹配能力强 |
| 代码解析 | tree-sitter | 多语言 AST 解析 |
| 可观测性 | OpenTelemetry | 跨 Agent trace 链路追踪 |

## 为什么不用现有框架？

| 框架 | 没采用的原因 |
|------|------------|
| LangGraph | 与 LangChain 强绑定；Agent 增长后图结构难以维护 |
| CrewAI | 更适合"讨论协作"场景，对工具调用+沙箱执行支持有限 |
| AutoGen | 核心范式是 Agent 对话，不适合任务流水线 |
| Temporal | 运维依赖 Cassandra/MySQL/ES 集群，小团队性价比低 |

Build 的 14 人天 vs 二次开发的 7-10 人天（还得忍受框架约束），选 Build 是因为长期维护成本更低。

## 详细文档

完整的架构演进过程、故障模式推演和 RAG 工程化实践，请参阅以下技术博客：

- [架构演进实战](https://pengli-ctrl.github.io/blog/posts/04-agentforge-architecture-evolution)
- [编排引擎演进](https://pengli-ctrl.github.io/blog/posts/05-orchestration-engine-evolution)
- [故障模式推演](https://pengli-ctrl.github.io/blog/posts/06-production-failure-patterns)
- [RAG 工程化](https://pengli-ctrl.github.io/blog/posts/01-rag-engineering-hallucination-prevention)
