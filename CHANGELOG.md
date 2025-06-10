# Changelog

All notable changes to AgentForge are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.0] - 2024-03

### Added
- Event-driven architecture with EventBus (Publish/Subscribe pattern)
- Context Snapshot isolation — agents receive frozen context copies, eliminating shared mutable state
- YAML-based dynamic routing engine with conditional branching
- Four-layer fault tolerance: Trust Boundary, Conflict Arbiter, AIMD Controller, Pulse Shaper
- RAG pipeline with AST-aware chunking, hybrid retrieval (BM25 + FAISS), and hallucination guard
- Full observability stack: Prometheus metrics, OpenTelemetry tracing, structured JSON logging
- FastAPI REST API with API key authentication, token-bucket rate limiting, and standardized error handling
- Python SDK (`AgentForgeClient`) with async HTTP client
- CLI tool (`agentforge`) with subcommands: submit, status, result, cancel, agents, metrics, workflows, serve
- Docker Compose orchestration (app + Redis + MySQL + Kafka)
- Task state machine: PENDING → RUNNING → COMPLETED / FAILED / CANCELLED
- Trace store for full-chain observability

### Changed
- Migrated from V2 Orchestrator (god object) to event-driven architecture
- Agent communication changed from direct calls to event bus pub/sub
- State management changed from Redis shared dict to immutable Context Snapshots
- V2 → V3 migration via gradual rollout (8 weeks, 2 engineers)

### Deprecated
- `agentforge.core.orchestrator.Orchestrator` (V2 serial orchestrator) — replaced by EventBus + YAML routing

### Removed
- V2 shared state context dictionary pattern

### Fixed
- Context dictionary infinite growth causing Prompt explosion at step 4+
- Orchestrator god object reaching 2000+ lines
- Static pipeline unable to handle conditional branching

---

## [2.0.0] - 2023-06

### Added
- Multi-Agent architecture: CodeReview, TestExecution, DocGenerator, SecurityScan agents
- V2 serial Orchestrator for agent pipeline execution
- Redis-based shared state store for inter-agent context passing
- YAML workflow configuration for pipeline definitions
- Tool sandbox with Docker isolation for code execution
- Basic retry logic for LLM API calls

### Changed
- Split single V1 Agent into 4 specialized agents
- Each agent's Prompt reduced from 45K to ~12K tokens
- Task execution time reduced from 4.2 min to 2.8 min (P50)

### Known Issues
- Orchestrator became a god object (2000+ lines)
- Shared context dictionary grows unboundedly across pipeline steps
- Static pipeline cannot handle conditional branching (e.g., security issues → run security scan)
- Redis restart causes state loss

---

## [1.0.0] - 2022-12

### Added
- Single Agent PoC with ReAct loop (Think → Act → Observe → Re-think)
- `BaseTool` abstract class with JSON Schema, async execution, and standardized `ToolResult`
- `AgentEngine` with configurable max iterations and token budget
- `LLMGateway` abstraction for vLLM private deployment
- Basic code review tool integration
- Token usage tracking and iteration counting

### Performance
- Tool call success rate: 94%
- Code review suggestion adoption rate: 67%
- Daily active users: 200+

### Known Limitations
- Prompt exceeds 32K tokens after 3+ tool calls
- Serial execution: single task takes 3-5 minutes
- Cannot split into multiple agents — tool call logic tightly coupled
