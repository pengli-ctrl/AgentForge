#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE_FILE="$ROOT/deploy/platform/docker-compose.lite.yml"
cd "$ROOT"

cleanup() {
  docker compose -f "$COMPOSE_FILE" down
}
trap cleanup EXIT

docker compose -f "$COMPOSE_FILE" up -d
python scripts/wait_for_infra.py

docker compose -f "$COMPOSE_FILE" exec -T postgres   psql -U agentforge -d postgres -c "DROP DATABASE IF EXISTS agentforge_test WITH (FORCE);"
docker compose -f "$COMPOSE_FILE" exec -T postgres   psql -U agentforge -d postgres -c "CREATE DATABASE agentforge_test;"

export AGENTFORGE_RUN_INFRA_TESTS=1
export AGENTFORGE_INFRA_DATABASE_URL="postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge_test"
export AGENTFORGE_TEMPORAL_ADDRESS="localhost:7233"
export AGENTFORGE_VALKEY_URL="redis://localhost:6379/0"
export AGENTFORGE_OBJECT_STORE_ENDPOINT="http://localhost:9000"
python -m pytest -q tests/infra

docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U agentforge -d postgres -c "DROP DATABASE IF EXISTS agentforge_test_drill WITH (FORCE);"
docker compose -f "$COMPOSE_FILE" exec -T postgres \
  psql -U agentforge -d postgres -c "CREATE DATABASE agentforge_test_drill;"
export AGENTFORGE_MIGRATION_DRILL_DATABASE_URL="postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge_test_drill"
export AGENTFORGE_MIGRATION_DRILL_CONFIRM="agentforge"
python scripts/migration_drill.py
