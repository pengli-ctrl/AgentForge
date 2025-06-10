# AgentForge Dockerfile — 多阶段构建
# Stage 1: Builder — 安装依赖
# Stage 2: Runtime — 精简运行时镜像

# ===== Stage 1: Builder =====
FROM python:3.10-slim AS builder

WORKDIR /build

# 安装系统依赖（编译 tree-sitter, faiss 等需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装 Python 依赖到虚拟环境
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ===== Stage 2: Runtime =====
FROM python:3.10-slim AS runtime

WORKDIR /app

# 安装运行时系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

# 从 builder 复制虚拟环境
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# 复制项目文件
COPY . .

# 设置 Python 环境变量
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV AGENTFORGE_HOME=/app

# 暴露 API 端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:8000/health'); exit(0 if r.status_code == 200 else 1)" || exit 1

# 启动命令
CMD ["uvicorn", "agentforge.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
