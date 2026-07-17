# Contributing to AgentForge

感谢你对 AgentForge 的关注！本文档描述了如何参与项目贡献。

## 开发环境搭建

### 前置条件

- Python 3.10+
- Git
- Redis（可选，开发环境可用内存后端）
- Docker & Docker Compose（可选，用于完整部署）

### 搭建步骤

```bash
# 1. 克隆仓库
git clone https://github.com/pengli-ctrl/AgentForge.git
cd AgentForge

# 2. 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate   # Windows

# 3. 安装依赖
make dev-install
# 或手动安装:
pip install -r requirements.txt
pip install pytest pytest-asyncio pytest-cov black isort flake8 mypy
pip install -e .

# 4. 验证安装
python -c "import agentforge; print(agentforge.__version__)"
```

## 代码规范

### 代码风格

项目使用以下工具保证代码风格一致性：

| 工具 | 用途 | 命令 |
|------|------|------|
| black | 代码格式化 | `make format` |
| isort | import 排序 | `make format` |
| flake8 | 风格检查 | `make lint` |
| mypy | 类型检查 | `make type-check` |

**提交前必须运行 `make format && make lint`。**

### 编码规范

1. **类型注解**：所有函数必须有完整的类型注解（Python 3.10+ 风格）
2. **Docstring**：所有模块、类、公共方法必须有 docstring
3. **async/await**：IO 操作必须使用异步
4. **dataclass**：数据模型使用 `@dataclass`
5. **行宽**：不超过 100 字符
6. **命名**：
   - 类名：`PascalCase`
   - 函数/变量：`snake_case`
   - 常量：`UPPER_SNAKE_CASE`
   - 私有成员：`_prefix`

### 提交规范

使用 [Conventional Commits](https://www.conventionalcommits.org/) 格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型：
- `feat`: 新功能
- `fix`: Bug 修复
- `docs`: 文档变更
- `refactor`: 代码重构
- `test`: 测试相关
- `chore`: 构建/工具变更

示例：
```
feat(api): add task cancellation endpoint

fix(safety): resolve AIMD controller window calculation error

docs(readme): update project structure tree
```

## 测试

### 运行测试

```bash
# 运行所有测试
make test

# 仅运行单元测试
make test-unit

# 仅运行集成测试
make test-integration
```

### 测试规范

1. **单元测试**：放在 `tests/unit/`，文件名 `test_*.py`
2. **集成测试**：放在 `tests/integration/`，文件名 `test_*.py`
3. **Mock 策略**：
   - LLM 用 `MockLLMGateway`（固定响应）
   - 工具用 Stub
   - EventBus 用内存后端
4. **测试命名**：`test_<被测方法>_<场景>`
5. **每个测试只验证一个行为**

### 添加新 Agent

1. 在 `agentforge/agents/` 创建 `xxx_agent.py`
2. 继承 `Agent` 基类
3. 实现 `_extract_context`、`_build_downstream_context`、`_build_initial_messages`
4. 在 `agentforge/agents/__init__.py` 注册导出
5. 在工作流 YAML 中添加路由配置
6. 编写单元测试和集成测试

### 添加新工具

1. 在 `agentforge/tools/` 创建 `xxx_tool.py`
2. 继承 `BaseTool` 抽象基类
3. 实现 `name`、`schema`、`execute` 方法
4. 在 `agentforge/tools/__init__.py` 注册导出
5. 编写单元测试

## 架构约束

1. **事件驱动**：Agent 间通过事件总线通信，不直接调用
2. **状态隔离**：Agent 只从 Context Snapshot 提取需要的上下文
3. **工具抽象**：所有工具调用通过 BaseTool 接口，不直接写在业务代码中
4. **确定性校验**：Agent 输出必须经过 Trust Boundary 校验
5. **不暴露敏感信息**：代码中不提及具体公司名、外部 API 名称

## PR 流程

1. Fork 仓库并创建特性分支
2. 编写代码和测试
3. 运行 `make format && make lint && make test`
4. 提交 PR，描述变更内容和测试结果
5. 等待 CI 通过和 Code Review

## 问题反馈

- Bug 报告：[GitHub Issues](https://github.com/pengli-ctrl/AgentForge/issues)
- 功能建议：[GitHub Discussions](https://github.com/pengli-ctrl/AgentForge/discussions)
- 邮件：pl2847253@gmail.com

## License

贡献的代码遵循 [MIT License](LICENSE)。
