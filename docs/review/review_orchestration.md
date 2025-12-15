# AgentForge 编排层 / 运行时层 代码评审报告

**评审范围**：`agentforge/core/`、`agentforge/orchestration/`、`agentforge/workflow/`、`agentforge/llm/`、`agentforge/agents/`
**评审维度**：代码合理性 + 注释专业性 + 与 README 设计意图一致性
**评审方式**：通读真实源码逐文件核对，非臆测。

---

## 一、代码不合理点（按严重程度）

### 🔴 严重

| 序号 | 文件:行 | 问题 | 说明 |
|---|---|---|---|
| S1 | `dag_engine.py`:260-285, 214-222 | **L3 早期终止与 success_rate 双机制失效（节点失败被算成成功）** | `_execute_node`（306-350）对所有 `asyncio.TimeoutError` 与 `Exception` 都做捕获，最终**必然返回一个 dict**（成功或 `{"result":None,"degraded":True}`），从不抛异常。因此 `_run_waves` 的 `isinstance(result, Exception)` 分支（279）实际上**永远不触发**，`rst:` `node_results[nid]` 总会写入（283-284）。结果是：①`_run_waves` 内 `failed = len(completed) - len(node_results)`（261）恒等于 0，L3 提前终止判断（263 `ratio>0.30`）形同虚设；②`success_rate = len(node_results)/total_nodes`（214）把「耗尽重试已降级」的节点计入成功，指标被系统性抬高；③`success=success_rate>0.7`（238）可能因全部节点降级仍返回 success=True。 |
| S2 | `orchestrator/request_guard.py`:50-217 + `dag_engine.py`:171,234 | **RequestGuard 三个维度中两个维度（并发信号量、LLM 调用计数）在编排链路中未被接线** | `dag_engine.set_dependencies` 虽注入 request_guard，但在 `execute()` 全流程中**只调用了 `check_dag_size`（171）和 `cleanup_request`（234）**。`acquire()`/`release()`/`check_llm_call_count()`/`increment_llm_calls()` 在 orchestration 与 workflow 层均无任何调用点（grep 验证仅 request_guard 自身定义）。即 README 声明 11 中的「并发 DAG≤10、LLM 调用≤100」两个维度**实际未生效**。且 `acquire()` 读私有属性 `self._semaphore._value` 作 peek（158）后再 `await acquire()`，存在 TOCTOU 竞态，虽单事件循环下偶发安全，但写法属反模式。 |
| S3 | `agents/*.py`（5 个）+ `core/agent.py`:321-459 | **「12 类 Agent 热插拔注册」与「统一 BaseAgent 基类」声明不符** | ① 仓库 `agents/` 下仅 5 个 Agent（code_review / deploy / doc_generator / security_scan / test_execution），与 README「12 类」明显不符；② 这 5 个实体 Agent 全部继承的是**兼容层 `Agent`（事件驱动，606 行 legacy）而非 `BaseAgent`**，`BaseAgent`（84-318，含 abc+5 接口）实际没有任何实体 Agent 继承使用——README 声称的统一基类与真正运行的 Agent 体系是两套代码。 |
| S4 | `agent.py`:245-252, 267-280 | **状态机形同虚设 + 失败状态被覆盖** | `_transition_to` 注释「State transitions are enforced」但在非法迁移时仅 `logger.warning` 后**照常赋值**（280），并非真正 enforce。更严重：`run()` 在异常分支（222-233）已把状态置 `TIMEOUT`/`ERROR` 分支，随后 248 行 `if degraded and status==OK` 为 False 时走 else 置为 `IDLE`（252），导致**刚置为 TIMEOUT 的状态立刻被覆盖回 IDLE**；`degraded=True` 且 `status!=OK`（如超时）时也落入 else 置 IDLE。FAILED/DEGRADED/TIMEOUT 状态基本无法持久反映实际结果。 |

### 🟠 中

| 序号 | 文件:行 | 问题 | 说明 |
|---|---|---|---|
| M1 | `planner.py`:440-455 | **启发式 agent 名与注册名不匹配（下划线 vs 连字符）** | keyword map 使用 `"security_scan"`、`"code_review"`、`"doc_generator"`、`"test_execution"`、`"deploy"`（441-445），而实体 Agent 注册名是连字符形式（`security-scan`、`code-review`、`doc-generator`、`test-execution`，见各 agent `name=` 与 `__init__`）。因 `if agent_name in self._registry.list_agents()`（450）必为 False，`_guess_single_agent` 永远走兜底 `code_review`（454），同样不存在于注册表，最终返回一个不在注册表中的名字，后续 `registry.get()` 会抛 KeyError——LLM 规划失败的单 Agent 兜底路径基本失效。 |
| M2 | `loop_block.py`:136-146 | **嵌套 DAGEngine 硬编码 magic number，且注释与实现相悖** | 子引擎写死 `max_nodes=20, global_timeout=60.0, max_parallel=3`（140）。注释 139 行称「Inherits timeout and degradation from parent engine context」，但实际是**硬编码 60s，并未继承父级（默认 300s）**。`20/60/3` 均为无出处魔法数；且 loop 5 次 × 60s 与 DAG 全局 300s 的预算关系没有联动校验。 |
| M3 | `degradation.py`:107-114 | **L1 熔断判断与 docstring 不一致** | docstring/注释声称「>50% failure rate over last 10 calls → open 15min」，但实际条件是 `len(recent) >= 10 and len(recent)/max(1,time_window/60) > 3`，即「最近 10 次中每分钟失败数>3」，与「10 次中失败率>50%」完全是两个指标；魔法数 20/10/900/3 无命名常量。 |
| M4 | `workflow/` 与 `core/` 两份注册表重复 | **存在两个互相独立的 AgentRegistry** | `core/agent_registry.py`（异步、类/实例、agent_name→BaseAgent）与 `workflow/registry.py`（同步、实例）职责重叠但接口不一致（一个 `list_agents()` 返回字符串列表，一个返回 metadata 列表）。DAG/Planner 走前者，WorkflowEngine 走后者，两套注册体系并行，易造成同一 agent 名注册两处、状态不同步。 |
| M5 | `workflow/engine.py`:345-356 | **Compatibility Agent 结果解析丢信息 / 吞异常** | `_execute_agent` 若 agent 返回 `AGENT_FAILED` 事件（payload `result=""`），`json.loads("")` 抛异常被吞、静默返回 `{"output":""}`，失败信息（`error` 字段）被丢弃；若 result 是合法 JSON 字符串会被直接 `json.loads` 成 dict，丢失原始模型输出结构，行为对调用方不可预期。 |
| M6 | `context_store.py`:183-203 | **`_access_log` 无限增长 + `log_access`/`delete` 属死代码** | `_store` 和 `_input` 均在 initialize 时重建，但 `_access_log` 仅 `clear()` 时清空，而 `clear()` 在 dag_engine 流程里从未被调用（execute 未调用 ctx.clear）——多次执行累计泄漏。且 `log_access`、`delete` 在编排链路中无任何调用点。 |

### 🟡 低

| 序号 | 文件:行 | 问题 | 说明 |
|---|---|---|---|
| L1 | `dag_engine.py`:268, 274 | 每轮 wave 都新建 `asyncio.Semaphore(self._max_parallel)`，未复用；`_wave` 为空时静默 `break`，若因 bug 出现既未完成又无入度为 0 的节点会静默挂起而非报错。 | |
| L2 | `dag_engine.py`:22-38, 123 | `DAGNode.timeout` 默认 30s 与全局 300s 无约束关系；`max_nodes=50/global_timeout=300/max_parallel=5` 魔数未提为常量。 | |
| L3 | `dag_engine.py`:290-350 | 节点执行同时受 `node.timeout`（30s, wait_for）与 `BaseAgent.run` 内部 `agent_timeout`（30s）双重套壳，语义重叠、不易区分。 | |
| L4 | `gateway.py`:205-210 | httpx 缺失时静默返回空 `LLMResponse`（"降级"），掩盖了真实依赖缺失，故障定位困难；`chat()` 中 `body`/`headers` 每次请求重建，未复用连接。 | |
| L5 | `context_store.py`:113-130 | 用魔法数切片 `ref[5:]`/`ref[7:]` 解析 `$ctx.`/`$input.`，若前缀写错会静默返回空而仅 debug 日志，无严格校验。 | |
| L6 | `timeout.py` `TimeoutManager` | LLM 级 `execute_with_llm_timeout` 定义后**全程无调用**（grep 验证），TimeoutManager 实际只用了 agent 级一个方法。 | |
| L7 | `agent.py`（legacy `Agent.execute`） | `token_budget` 溢出用 `break` 而非标记失败；`_build_downstream_context` 丢弃 `original_snapshot`/`relevant_context` 参数返回固定结构（431）——死参数。 | |

---

## 二、注释专业性问题

**做得好的**：
- `dag_engine.py` 模块头（1-7）、`DAGNode` docstring（22-30）、`LoopBlock` 模块头（1-26，含成本分析、5 次上限理由）解释「为什么」而非只写「做什么」，质量高。
- `timeout.py` 模块头（1-41）对三级超时数值来源（P50/P95/P99）、为何用 `asyncio.wait_for` 而非 signal、取消语义都做了扎实的 rationale。
- `loop_block.py`、`degradation.py` 头部的设计篇幅专业、有价值。
- `planner.py` 的 prompt 注释说明了「LLM只规划不执行」「fallback」等理念。

**不规范/误导的问题**：
1. **注释与实际不一致（误导榜首）**：`loop_block.py:139` 声称子引擎「inherits timeout...from parent」实则硬编码；`degradation.py:88` 声称「>50% failure rate over last 10 calls」实际是每分钟频率阈值（M3）；`memory.py:162-187` LongTermMemory docstring 通篇写「Persistent...FAISS+BM25」但实现是**纯内存 `_vectors` dict + 手写余弦**，注释自己也在行 170 坦白「Current implementation uses in-memory」——同一注释自相矛盾。
2. **文档字符串口气与现实差距大**：`agent_registry.py:174`、`request_guard.py` 的类注释（如「Uses semaphore pattern」）与实际未接线状态不符（S2）。README 大量「703 测试通过」「97% 准确率」等宣传性数字，而实际代码未见到测试/标注支撑。
3. **类型标注不完整**：许多关键方法对 `dag`/`context`/`registry` 仅写注释或裸参数无类型——如 `dag_engine.execute`（148-154）`dag: Optional[DAGGraph]` ok，但 `_run_waves`（248）全部 `dag, in_degree, ...` 无类型；`loop_block.execute`（101）`context/agent_registry/tracer` 无类型；`agents/*` 的 `_execute_agent`（`workflow/engine.py:311`）`agent: Any`。README 声称「mypy 全程」与这些无标注形成反差。
4. **中文注释占比失衡**：workflow/llm 层（engine.py、llm_router.py、gateway.py、base_tool.py、agents/*）以中文注释为主，而 orchestration/core 层以英文为主，混用无统一风格；部分中文注释（如 `llm_router.py:16`）夹杂个人化叙述。
5. **`_transition_to`**（agent.py:267-270）注释称状态机 enforced，实际仅告警不拦截（S4），注释有误导。

---

## 三、README 一致性核对表

> 核对依据：README.md 相关声明（行 42-96 及目录树、3xx 性能表）+ 实际源码。

| # | README 声明 | 核对 | 结论 |
|---|---|---|---|
| 1 | 三层架构：编排层/运行时层/网关层 | `orchestration/`（编排）、`core/`（运行时：agent/memory/tool）、`llm/gateway.py`（网关）结构清晰、确实分层。 | ✅ 一致 |
| 2 | DAG≤50 节点、Kahn O(V+E)、无依赖节点并行 | `dag_engine.topological_sort`（88-112）确为 Kahn O(V+E)；`execute` 校验 `len>max_nodes`(165)；`_run_waves` 用 wave 并行。但**节点失败被计为成功（S1）**侵蚀 success_rate 语义，机制存在但指标失真。 | ⚠️ 部分一致 |
| 3 | 三种编排模式（静态/动态Planner/运行时重编排） | 静态=DAGGraph 手动构建、动态=`PlannerAgent.plan/build_dag` 均存在。**但「运行时重编排」：`dag_engine.replan()`（352）与 `planner.replan()`（193）已实现却在整个编排链路中零调用**（`_run_waves`/`execute` 从不触发 replan），且 `set_dependencies` 也未见注入 replan 回调。故第三种模式是「只实现了 API，未接入执行流程」。 | ⚠️ 部分一致（第三种模式未接线） |
| 4 | ContextStore 节点间数据流转 + 读写锁保护并行节点 | `context_store.py` 存在，用单一 `asyncio.Lock` 包裹所有读写；`read_with_mapping` 正确解析 `$ctx/`$input`。但**是单把全局限流锁**（非每 key 锁），并行节点 I/O 完全串行化，且 `access_log`/`clear` 泄漏（M6）。机制存在但与「读写锁（区分读/写）」措辞有出入。 | ⚠️ 部分一致 |
| 5 | LoopBlock：DAG 内嵌子图+循环控制器，最大 5 次硬约束、退出条件可配置 | `LoopBlock.ABSOLUTE_MAX_ITERATIONS=5`（70-71）硬约束存在；`exit_condition` 可配置（98）；子 DAG 由 DAGEngine 执行。**但子引擎硬编码 20/60/3 且注释与实现矛盾（M2）**。 | ✅ 基本一致（含量化瑕疵 M2） |
| 6 | 统一 Agent 基类（abc+5 接口），12 类 Agent 热插拔注册 | **不一致**：`BaseAgent` 确为 abc+5 方法（get_tools/get_memory_config/validate_input/on_error/execute），但**实体 5 个 Agent 全部继承 legacy `Agent` 而非 `BaseAgent`，且总数仅 5≠12**（S3）。「12 类」「统一基类驱动」均名不副实。 | ❌ 不一致 |
| 7 | 三级 Memory（工作/短期/长期-硬盘 RAG） | 三级类（Working/ShortTerm/LongTerm）存在，`MemoryManager` 组装。**但 LongTermMemory 实为纯内存 dict+手写余弦，无 FAISS、无 BM25、无硬盘持久化**；且默认 `enable_long_term=False`，运行时 `BaseAgent.run` 只读写 short_term，长期内存从未在实际执行路径被写/查（grep 无调用）。「硬盘 RAG」并未落地。 | ❌ 不一致 |
| 8 | Tool 框架支持 Function Calling + MCP | `base_tool.py` 提供 Function Calling 风格的 schema+ToolRegistry，**证据充分**。但**整个被审目录内无任何 MCP 实现/引用**（搜索 `mcp/MCP` 全部为空），且目录树声明的 `tool_framework.py` 文件**不存在**（实际是 `base_tool.py`）。 | ❌ 不一致（MCP 缺失、文件名不符） |
| 9 | 三层超时：LLM 10s / Agent 30s / DAG 300s | `TimeoutConfig` 定义了 10/30/300（62-64）。**Agent 30s 实际生效**（`BaseAgent.run` 走 `execute_with_agent_timeout`）。但 **LLM 层 `execute_with_llm_timeout` 无任何调用**，实际 LLM 调用超时由 `LLMGateway` 默认 `timeout=30.0`（gateway.py:94）+ planner 的 `asyncio.wait_for(15s)` 决定——**LLM 层级并非 10s**。DAG 300s 由 `execute` 的 `wait_for` 生效。 | ⚠️ 部分一致（Agent/DAG 生效，LLM 10s 未落地） |
| 10 | 四级降级：L1 模型/ L2 节点重试+fallback / L3 失败>30%提前终止 / L4 系统 | L1/L2/L4 的 `DegradationManager` 方法存在且被触发路径调用。**L3 实际失效（S1）**：因节点失败被计成功，`failed = completed - node_results` 恒为 0，>30% 提前终止判断永不命中；L1 熔断条件实现与注释不符（M3）。 | ⚠️ 部分一致（L3 失效、L1 语义偏差） |
| 11 | 请求放大管控：DAG≤50、单请求 LLM≤100、并发 DAG≤10×5 | **DAG≤50 生效**（dag_engine 校验）。**LLM 调用计数维度与并发信号量维度完全未接线**（S2）：`check_llm_call_count`/`increment_llm_calls`/`acquire`/`release` 无调用点，即「≤100 次」「≤10 DAG×5」两项约束**实际不生效**。并发上限实际仅靠 DAG 内 `max_parallel=5` 的本地信号量。 | ❌ 不一致（仅 DAG 规模生效） |

---

## 结论

编排层与网关层的**顶层设计文档（模块头注释、架构分层、Kahn 排序、Loop 硬约束、四级降级理念）整体专业、有想法**，可作为学习范本；但 **README 存在明显「宣传 > 实现」的系统性偏差**：

- **未接线/死代码**：运行时重编排 replan、LLM 10s 超时、RequestGuard 并发与 LLM 计数维度、长期 RAG memory、MCP 工具、ContextStore cleanup——均为「定义了但未接入执行链路」。
- **关键语义 bug**：`dag_engine` 将降级节点计为成功导致 L3 降级与 success_rate 失真（建议：区分 `node_results` 与 `degraded_nodes`，失败统计单列）。
- **体系断裂**：实体 Agent 走 legacy `Agent` 类、DAG/Planner 走 `BaseAgent` 注册表，两套 Agent 体系并存；两份重复的 `AgentRegistry`。

建议优先修复 S1、S2、S4（影响正确性与声明可信度），重构 S3/M1 的 Agent 体系统一，再补齐「未接线」特性或修正 README 措辞。