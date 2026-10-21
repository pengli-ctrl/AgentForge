# Contributing to AgentForge

感谢你对 AgentForge 的关注！本文档说明开发、测试和提交贡献的流程。

## 开发环境

### 前置条件

- Python 3.10+
- Git
- Docker & Docker Compose（真实基础设施测试和完整平台 Compose 需要）
- 可选：PostgreSQL、Temporal、MinIO、Valkey（手工联调时使用）

### 搭建

```bash
git clone https://github.com/pengli-ctrl/AgentForge.git
cd AgentForge

python -m venv .venv
source .venv/bin/activate       # Linux/macOS
# .venv\Scripts\activate        # Windows

make dev-install
```

`make dev-install` 会安装运行时和开发依赖，并以 editable 模式安装项目。也可手工执行：

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -e .
```

验证：

```bash
python -c "import agentforge; print(agentforge.__version__)"
```

## 代码规范

| 工具 | 用途 | 命令 |
|---|---|---|
| black | 格式化 | `make format` |
| isort | import 排序 | `make format` |
| flake8 | 风格检查 | `make lint` |
| mypy | 类型检查 | `make type-check` |

提交前至少执行：

```bash
make format
make lint
make type-check
make test
```

规范：

1. 公共函数和关键业务逻辑必须有类型注解。
2. 模块、类、公共方法需有清晰 docstring。
3. IO 路径优先使用 async/await。
4. 行宽不超过 100 字符。
5. 类名 `PascalCase`，函数/变量 `snake_case`，常量 `UPPER_SNAKE_CASE`。
6. 不在日志、Audit、异常或测试 fixture 中写入真实 Secret 和 PII。

## 测试分层

| 目录 | 内容 | 命令 |
|---|---|---|
| `tests/unit` | 快速单元测试 | `make test-unit` |
| `tests/integration` | 编排层和服务集成测试 | `make test-integration` |
| `tests/platform` | 平台、模块、SaaS、安全和商业能力测试 | `python -m pytest tests/platform -q` |
| `tests/infra` | PostgreSQL、Temporal、MinIO、Valkey 真实测试 | `make test-infra` |

真实基础设施测试：

```bash
make test-infra
# Windows PowerShell
./scripts/run_infra_tests.ps1
```

普通 `pytest` 会跳过 `tests/infra`，除非设置：

```text
AGENTFORGE_RUN_INFRA_TESTS=1
```

测试要求：

- 单元测试放在 `tests/unit/`，命名 `test_*.py`。
- 平台和模块测试放在 `tests/platform/`。
- LLM 使用 Mock Gateway，工具使用 Stub，内存仓储用于快速测试。
- 每个测试验证清晰、单一的行为。
- 新模块必须补充租户隔离、Memory/SQLAlchemy 一致性和迁移测试。
- 修改 Outbox、Temporal、存储或迁移时，应运行基础设施测试。

## 新增 Agent

1. 在 `agentforge/agents/` 创建实现。
2. 继承统一 Agent 基类。
3. 实现上下文提取、下游上下文构建和初始消息构建。
4. 在 `agentforge/agents/__init__.py` 注册导出。
5. 更新工作流配置和测试。

## 新增 Tool

1. 在 `agentforge/tools/` 创建实现。
2. 继承 `BaseTool`。
3. 实现 `name`、`schema` 和 `execute`。
4. 在 `agentforge/tools/__init__.py` 注册导出。
5. 增加成功、失败和 schema 校验测试。

## 新增业务模块

1. 从 `templates/module-template` 复制模块。
2. 实现 `ModuleManifest` 和 `ModuleRuntime`。
3. 保持 Domain / Application / Infrastructure / API 边界。
4. 只依赖本模块 Port 和 `agentforge.platform.sdk`。
5. 显式处理 `tenant_id`、Audit、Outbox 和 Secret Reference。
6. 为 SQLAlchemy 仓储提供可执行 upgrade/downgrade。
7. 运行 `run_module_contract_suite` 和 tenant isolation probe。

详细规则见：

- `docs/modules/MODULE_INTEGRATION_GUIDE.md`
- `docs/modules/VERSIONING_AND_DEPRECATION.md`
- `templates/module-template/README.md`

## 架构约束

1. 平台 core 不导入具体业务模块。
2. 模块 Application 层不依赖平台 runtime、application、api 或 core 具体实现。
3. 所有租户数据查询显式包含 `tenant_id`。
4. 高风险动作必须经过 Policy/RBAC 和审批边界。
5. 外部副作用必须可审计、幂等和可重试。
6. Secret 只能使用 Secret Reference，不提交明文。
7. 事件和权限命名遵循模块契约。

## 提交规范

使用 Conventional Commits：

```text
<type>(<scope>): <subject>

<body>

<footer>
```

常用类型：

- `feat`
- `fix`
- `docs`
- `refactor`
- `test`
- `chore`

示例：

```text
feat(module): add asset retention workflow
fix(outbox): avoid replaying completed handlers
docs(architecture): align module boundaries with current code
```

## PR 流程

1. 创建特性分支。
2. 编写代码、测试和必要文档。
3. 执行：

```bash
make format
make lint
make type-check
make test
```

4. 涉及真实基础设施时执行 `make test-infra`。
5. 涉及发布元数据时执行 `make release-check`。
6. 提交 PR，说明变更、测试结果、迁移和回滚影响。
7. 等待 CI 和 Code Review。

PR 不应包含计划草稿、阶段报告、临时测试记录或与项目交付无关的 Markdown。

## 问题反馈

- Bug：GitHub Issues
- Feature：GitHub Issues / Discussions
- 安全漏洞：按 `SECURITY.md` 私下报告，不要创建公开 Issue

## License

贡献代码遵循 [MIT License](LICENSE)。
