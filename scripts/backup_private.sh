#!/usr/bin/env bash
set -euo pipefail

: "${AGENTFORGE_BACKUP_DATABASE_URL:?set AGENTFORGE_BACKUP_DATABASE_URL}"
: "${AGENTFORGE_BACKUP_DIR:?set AGENTFORGE_BACKUP_DIR}"
mkdir -p "$AGENTFORGE_BACKUP_DIR"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
dump="$AGENTFORGE_BACKUP_DIR/agentforge-$timestamp.dump"
pg_dump --format=custom --no-owner --file="$dump" "$AGENTFORGE_BACKUP_DATABASE_URL"
sha256sum "$dump" > "$dump.sha256"

if [[ -n "${AGENTFORGE_OBJECT_STORE_ALIAS:-}" && -n "${AGENTFORGE_BACKUP_BUCKET:-}" ]]; then
  mc mirror --overwrite "$AGENTFORGE_OBJECT_STORE_ALIAS/$AGENTFORGE_BACKUP_BUCKET"     "$AGENTFORGE_BACKUP_DIR/objects-$timestamp"
fi

printf 'backup created: %s
' "$dump"
printf 'checksum: %s
' "$dump.sha256"
