# AgentForge 3.1.0 Migration Guide

- Target revision: `20261021_0032`
- Previous commercial baseline: `20261020_0028`

## 1. New migrations

| Revision | Change |
|---|---|
| `20261021_0029` | Versioned tenant module config fields |
| `20261021_0030` | Demo Asset module table |
| `20261021_0031` | Outbox handler receipts |
| `20261021_0032` | Tenant accounts and usage records |

All migrations are additive except normal index/column additions. No destructive data transformation is required.

## 2. Pre-upgrade checklist

1. Take a PostgreSQL backup and MinIO/S3 snapshot.
2. Record `alembic current`.
3. Verify enough disk space for new indexes.
4. Stop Outbox Worker before schema upgrade.
5. Run in staging:

```bash
export AGENTFORGE_DATABASE_URL='postgresql+asyncpg://.../agentforge_test'
export AGENTFORGE_MIGRATION_DRILL_DATABASE_URL="$AGENTFORGE_DATABASE_URL"
export AGENTFORGE_MIGRATION_DRILL_CONFIRM=agentforge
python scripts/migration_drill.py
```

The drill executes:

```text
upgrade 20261020_0028
upgrade head
downgrade 20261020_0028
upgrade head
```

## 3. Upgrade

```bash
export AGENTFORGE_DATABASE_URL='postgresql+asyncpg://.../agentforge'
alembic upgrade head
alembic current
```

Kubernetes/Helm executes the migration Job as a pre-install/pre-upgrade hook. Roll out API, Worker, then Outbox Worker.

## 4. Post-upgrade smoke test

1. `/health/live` and `/health/ready` return 200.
2. Existing Support and Expense APIs still authorize tenants.
3. Tenant module config GET returns `source=deployment_default` for tenants without overrides.
4. `/v1/admin/plans` returns plan catalog.
5. Provision a test tenant and verify plan-driven module enablement.
6. Record usage twice with the same idempotency key and verify one record.
7. Check `/v1/outbox/events/count`; replay failed events when dependencies recover.

## 5. Rollback

Application rollback:

```bash
helm rollback agentforge <REVISION> -n agentforge
```

Database rollback to previous baseline:

```bash
alembic downgrade 20261020_0028
```

Rollback caveats:

- `tenant_accounts` and `usage_records` data is removed by downgrade 0032.
- Outbox handler receipts are removed by downgrade 0031.
- Tenant module override configuration fields are removed by downgrade 0029.
- For production, restoring the pre-upgrade backup is the preferred rollback if new commercial data must be retained.

## 6. Upgrade verification record

Record the following in the operational change ticket:

- migration drill JSON;
- `alembic current` output;
- automated verification summary;
- security scan artifact;
- image/package checksums.
