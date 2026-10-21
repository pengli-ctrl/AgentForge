# AgentForge Platform 部署配置

本目录包含本地开发、演示和基础设施集成测试使用的 Docker Compose 配置，以及平台镜像相关文件。

## 配置一览

| 文件 | 用途 |
|---|---|
| `docker-compose.lite.yml` | 只启动 PostgreSQL、Valkey、Temporal、Temporal UI 和 MinIO |
| `docker-compose.platform.yml` | 启动基础设施、Kafka、OTel、Migration、API、Worker 和 Outbox Worker |
| `Dockerfile.platform` | 平台 API/Worker 镜像 |
| `otel-collector-config.yaml` | OTel Collector 配置 |

## Lite 依赖环境

```bash
docker compose -f deploy/platform/docker-compose.lite.yml up -d
```

或：

```bash
make platform-lite-up
```

服务：

| 服务 | 端口/入口 |
|---|---|
| PostgreSQL | `localhost:5432` |
| Valkey | `localhost:6379` |
| Temporal | `localhost:7233` |
| Temporal UI | `http://localhost:8080` |
| MinIO API | `http://localhost:9000` |
| MinIO Console | `http://localhost:9001` |

停止：

```bash
make platform-lite-down
```

Lite 适用于单元集成、真实基础设施测试和本地开发，不启动 API/Worker。

## 完整平台环境

```bash
docker compose -f deploy/platform/docker-compose.platform.yml up -d
```

或：

```bash
make platform-up
```

包含：

- `postgres`
- `valkey`
- `temporal`
- `temporal-ui`
- `minio`
- `kafka`
- `otel-collector`
- `migrate`
- `api`
- `worker`
- `outbox-worker`

平台 API：

```text
http://localhost:8000
```

健康检查：

```text
GET /health/live
GET /health/ready
```

`/health/live` 表示进程存活，`/health/ready` 表示应用已初始化；两者都不是数据库、Temporal、Valkey 或对象存储的深度健康检查。

停止：

```bash
make platform-down
```

## 鉴权与默认值

Compose 中提供的是本地演示默认值，生产不得直接使用。

平台默认 fail-closed：

- 生产环境必须配置 `AGENTFORGE_ADMIN_API_KEY` 或 `AGENTFORGE_API_KEYS`。
- Compose 的默认 Admin Key 仅用于本地启动。
- `AGENTFORGE_ALLOW_NO_AUTH=true` 仅限本地、受控环境。

建议：

```bash
export AGENTFORGE_ADMIN_API_KEY='<strong-local-key>'
export AGENTFORGE_API_KEYS='{"<tenant-key>":"tenant-a"}'
docker compose -f deploy/platform/docker-compose.platform.yml up -d
```

## 数据库迁移

完整 Compose 的 `migrate` 服务在 API/Worker 启动前执行：

```bash
alembic upgrade head
```

手工执行：

```bash
docker compose -f deploy/platform/docker-compose.platform.yml run --rm migrate
```

当前迁移头：

```text
20261021_0032
```

## 真实基础设施测试

Linux/macOS：

```bash
make test-infra
```

Windows PowerShell：

```powershell
./scripts/run_infra_tests.ps1
```

脚本会：

1. 启动 `docker-compose.lite.yml`；
2. 等待 PostgreSQL、Valkey、MinIO、Temporal；
3. 创建 `agentforge_test`；
4. 执行 `tests/infra`；
5. 创建 `agentforge_drill`；
6. 执行 `scripts/migration_drill.py`；
7. 停止 Compose。

普通 `pytest` 会跳过需要真实基础设施的用例。

## 数据与存储

Compose 使用命名卷：

- `agentforge-postgres`
- `agentforge-valkey`
- `agentforge-minio`

执行 `down` 不会删除卷；如需重建本地数据，必须显式删除卷并确认无保留数据。

## 互斥提醒

早期编排层 `docker-compose.yml` 与平台 Compose 使用相同的 `8000/6379/9092` 端口，不能在同一主机同时启动。先停止一套，再启动另一套。

## 部署边界

该目录不是生产高可用部署方案。私有化交付形态请参考：

- `deploy/helm/agentforge`；
- 外部 PostgreSQL、Temporal、MinIO/S3、Valkey 和 Kafka；
- 目标环境自行提供的监控、告警、备份和灾备体系。

交付拓扑、Secret 注入和安装入口见 [私有化交付基线](../../docs/security/PRIVATE_DELIVERY.md)。