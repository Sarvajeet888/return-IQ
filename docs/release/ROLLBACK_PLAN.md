# Rollback Plan — ReturnIQ Enterprise

Last updated: 1 August 2025

---

## When to Roll Back

Roll back immediately if any of the following occur after a deployment:
- Health check `GET /health` returns non-200 for more than 2 minutes
- Error rate on `/api/v1/returns` exceeds 5% for more than 5 minutes
- Database migrations caused data corruption or data loss
- A critical security vulnerability is discovered in the deployed version
- Core prediction flow (`POST /returns`) is returning wrong results

---

## Pre-Deployment: Always Do These

1. Tag the current production Docker image before deploying:
   ```bash
   docker tag returniq-backend:latest returniq-backend:rollback-$(date +%Y%m%d)
   ```

2. Record the current Alembic revision:
   ```bash
   docker exec returniq-backend alembic current
   # Example output: c7f91a3d2e55 (head)
   ```

3. Create a database backup:
   ```bash
   docker exec returniq-postgres pg_dump -U returniq returniq | gzip > pre_deploy_backup_$(date +%Y%m%d_%H%M%S).sql.gz
   ```

---

## Rollback Procedure

### Step 1 — Restore Previous Container Image

```bash
# Stop current containers
docker compose down

# Restore previous image
docker tag returniq-backend:rollback-<date> returniq-backend:latest

# Restart
docker compose up -d
```

### Step 2 — Roll Back Database Migration (If Applicable)

Only needed if the new release added Alembic migrations. Check the CHANGELOG for the
migration revision ID.

```bash
# Roll back one migration step
docker exec returniq-backend alembic downgrade -1

# Or roll back to a specific revision
docker exec returniq-backend alembic downgrade c7f91a3d2e55

# Verify
docker exec returniq-backend alembic current
```

⚠️ **Downgrade removes tables/columns.** Any data written to those columns since the
deployment is permanently lost. Evaluate this trade-off before running downgrade.
If data was written to new columns that matter, restore from the pre-deployment backup
instead of running a downgrade.

### Step 3 — Restore from Pre-Deployment Backup (If Data Was Lost)

```bash
# Stop the application
docker compose stop backend

# Drop and recreate the DB
docker exec returniq-postgres psql -U returniq -c "DROP DATABASE returniq;"
docker exec returniq-postgres psql -U returniq -c "CREATE DATABASE returniq;"

# Restore
gunzip -c pre_deploy_backup_<timestamp>.sql.gz | \
  docker exec -i returniq-postgres psql -U returniq returniq

# Start backend with correct image
docker compose up -d backend

# Verify
curl http://localhost:8000/health
```

### Step 4 — Verify After Rollback

```bash
curl https://your-domain.com/health
# → {"status": "ok"}

# Quick smoke test — submit a test return and check the prediction comes back
curl -X POST https://your-domain.com/api/v1/returns \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"platform_order_id": "TEST-001", "sku": "TEST", ...}'
```

### Step 5 — Notify Stakeholders

- Notify affected Merchant users if any data was lost or predictions were incorrect
  during the window between deployment and rollback
- Document the incident: what went wrong, when detected, when resolved, impact assessment
- Open a post-mortem ticket before re-attempting the deployment

---

## Phase-Specific Rollback Notes

### Rolling Back Phase 7 (v3.0.0)
Phase 7 is documentation only — no database migrations, no backend code changes.
There is nothing to roll back technically. If a doc was published incorrectly, update
it directly.

### Rolling Back Phase 6 (v2.6.0)
No database migrations. Rollback means reverting the Python code changes and
re-deploying the previous image. The security hardening can be disabled by reverting
`app/main.py` (headers middleware) and `app/core/security.py`.
⚠️ Do not roll back Phase 6 security fixes unless absolutely necessary.

### Rolling Back Phase 5 (v2.5.0)
Migration: `c7f91a3d2e55` — adds 8 tables and 2 columns.
```bash
alembic downgrade 8a3f21c9de44  # rolls back to Phase 4 state
```
This drops: `password_reset_tokens`, `return_notes`, `return_documents`,
`workflow_rules`, `feature_flags`, `customer_blacklist`, `system_settings`,
`sla_tracking`, and the `is_blacklisted` / `notes` columns on `customers`.
Any data in these tables is permanently lost.

### Rolling Back Phase 4 (v2.0.0)
Migration: `8a3f21c9de44` — adds `prediction_outcomes` table.
```bash
alembic downgrade <phase3-revision>
```
This drops the `prediction_outcomes` table and any collected outcome labels.

---

## Rollback Decision Matrix

| Symptom | Likely Cause | Action |
|---|---|---|
| `/health` returns 500 | App crash — likely env var or import error | Check logs → fix config → restart |
| `/health` returns 200 but predictions wrong | Logic bug in scoring | Rollback backend image |
| DB connection refused | Postgres down or wrong URL | Check Postgres container; check `DATABASE_URL` |
| 401 on all endpoints after deploy | `SECRET_KEY` changed | Restore old `SECRET_KEY` in `.env` and restart |
| Migration failed partway | DB in inconsistent state | Restore from pre-deploy backup |
| High error rate but `/health` OK | New endpoint bugs | Rollback backend image; no DB rollback needed |
