# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

ARG APP_VERSION=3.1.0
WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends     build-essential     git     && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements-dev.txt ./
COPY requirements ./requirements
RUN python -m venv /opt/venv     && /opt/venv/bin/pip install --no-cache-dir --upgrade pip     && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt -r requirements/platform.txt

FROM python:3.12-slim AS runtime

ARG APP_VERSION=3.1.0
LABEL org.opencontainers.image.title="AgentForge"       org.opencontainers.image.version="${APP_VERSION}"       org.opencontainers.image.licenses="MIT"

RUN apt-get update && apt-get install -y --no-install-recommends     curl     libgomp1     && rm -rf /var/lib/apt/lists/*     && useradd --system --uid 10001 --create-home --home-dir /home/agentforge agentforge

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=agentforge:agentforge . /app

ENV PATH="/opt/venv/bin:$PATH"     PYTHONUNBUFFERED=1     PYTHONDONTWRITEBYTECODE=1     AGENTFORGE_HOME=/app

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=5     CMD curl -fsS http://localhost:8000/health/live || exit 1

CMD ["uvicorn", "agentforge.platform.api.app:create_platform_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
