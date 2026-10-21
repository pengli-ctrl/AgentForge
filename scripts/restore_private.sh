#!/usr/bin/env bash
set -euo pipefail

dump="${1:?usage: restore_private.sh <database.dump>}"
: "${AGENTFORGE_BACKUP_DATABASE_URL:?set AGENTFORGE_BACKUP_DATABASE_URL}"
if [[ "${AGENTFORGE_RESTORE_CONFIRM:-}" != "agentforge" ]]; then
  printf 'Refusing destructive restore. Set AGENTFORGE_RESTORE_CONFIRM=agentforge
' >&2
  exit 2
fi
if [[ -f "$dump.sha256" ]]; then
  sha256sum --check "$dump.sha256"
fi
pg_restore --clean --if-exists --no-owner --dbname="$AGENTFORGE_BACKUP_DATABASE_URL" "$dump"
alembic upgrade head
printf 'database restore completed: %s
' "$dump"
