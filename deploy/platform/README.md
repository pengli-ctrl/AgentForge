# AgentForge Platform Lite

Start local platform dependencies:

    docker compose -f deploy/platform/docker-compose.lite.yml up -d

Services:

- PostgreSQL: localhost:5432
- Valkey: localhost:6379
- Temporal: localhost:7233
- Temporal UI: http://localhost:8080
- MinIO API: http://localhost:9000
- MinIO Console: http://localhost:9001

This profile is intended for local development and the first Support Copilot walking skeleton. It is not a production deployment.
