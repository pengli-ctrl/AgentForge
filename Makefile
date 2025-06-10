# AgentForge Makefile — 常用命令

.PHONY: install dev-install test test-unit test-integration lint format type-check run docker-build docker-up docker-down clean help

# Python 虚拟环境
VENV = .venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip

# 默认目标
.DEFAULT_GOAL := help

help: ## 显示帮助信息
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## 安装生产依赖
	python -m pip install --upgrade pip
	pip install -r requirements.txt

dev-install: ## 安装开发依赖（含测试、lint 工具）
	python -m pip install --upgrade pip
	pip install -r requirements.txt
	pip install -r requirements-dev.txt
	pip install -e .

test: ## 运行所有测试
	python -m pytest tests/ -v --tb=short --cov=agentforge --cov-report=term-missing

test-unit: ## 运行单元测试
	python -m pytest tests/unit/ -v --tb=short

test-integration: ## 运行集成测试
	python -m pytest tests/integration/ -v --tb=short

lint: ## 代码风格检查
	flake8 --max-line-length=100 --extend-ignore=E203,W503 agentforge/ tests/
	isort --check-only --profile black agentforge/ tests/
	black --check --line-length 100 agentforge/ tests/

format: ## 格式化代码
	black --line-length 100 agentforge/ tests/
	isort --profile black agentforge/ tests/

type-check: ## 类型检查
	mypy --ignore-missing-imports --no-strict-optional agentforge/

syntax-check: ## 语法检查所有 Python 文件
	find . -name "*.py" -not -path "*__pycache__*" -exec python3 -m py_compile {} \;
	@echo "All Python files compiled successfully"

run: ## 启动 API 服务
	uvicorn agentforge.api.app:app --host 0.0.0.0 --port 8000 --reload

run-dev: ## 启动 API 服务（开发模式，DEBUG=True）
	AGENTFORGE_DEBUG=true uvicorn agentforge.api.app:app --host 0.0.0.0 --port 8000 --reload

docker-build: ## 构建 Docker 镜像
	docker build -t agentforge:latest .

docker-up: ## 启动完整服务（Docker Compose）
	docker-compose up -d

docker-down: ## 停止所有服务
	docker-compose down

clean: ## 清理缓存文件
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	rm -rf .pytest_cache .mypy_cache .coverage htmlcov
