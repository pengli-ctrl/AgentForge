$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$ComposeFile = Join-Path $Root "deploy/platform/docker-compose.lite.yml"
Set-Location $Root

try {
    docker compose -f $ComposeFile up -d
    python scripts/wait_for_infra.py
    docker compose -f $ComposeFile exec -T postgres psql -U agentforge -d postgres -c "DROP DATABASE IF EXISTS agentforge_test WITH (FORCE);"
    docker compose -f $ComposeFile exec -T postgres psql -U agentforge -d postgres -c "CREATE DATABASE agentforge_test;"
    $env:AGENTFORGE_RUN_INFRA_TESTS = "1"
    $env:AGENTFORGE_INFRA_DATABASE_URL = "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge_test"
    $env:AGENTFORGE_TEMPORAL_ADDRESS = "localhost:7233"
    $env:AGENTFORGE_VALKEY_URL = "redis://localhost:6379/0"
    $env:AGENTFORGE_OBJECT_STORE_ENDPOINT = "http://localhost:9000"
    python -m pytest -q tests/infra
    docker compose -f $ComposeFile exec -T postgres psql -U agentforge -d postgres -c "DROP DATABASE IF EXISTS agentforge_drill WITH (FORCE);"
    docker compose -f $ComposeFile exec -T postgres psql -U agentforge -d postgres -c "CREATE DATABASE agentforge_drill;"
    $env:AGENTFORGE_MIGRATION_DRILL_DATABASE_URL = "postgresql+asyncpg://agentforge:agentforge@localhost:5432/agentforge_drill"
    $env:AGENTFORGE_MIGRATION_DRILL_CONFIRM = "agentforge"
    python scripts/migration_drill.py
}
finally {
    docker compose -f $ComposeFile down
}
