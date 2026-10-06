# Troubleshooting Guide — ReturnIQ Enterprise

---

## Backend / API Issues

### "no such table" on startup
**Cause:** Alembic migrations haven't run.
**Fix:** `cd backend && alembic upgrade head`

### "RuntimeError: SECRET_KEY is required in production"
**Cause:** `ENVIRONMENT=production` without `SECRET_KEY` set.
**Fix:** Set `SECRET_KEY` in your `.env` file. Generate with:
`python3 -c "import secrets; print(secrets.token_hex(64))"`

### 401 Unauthorized on every request
**Causes:**
- Access token expired (15-minute TTL) — the frontend should auto-refresh; check if the refresh cookie is being sent
- Token signed with a different `SECRET_KEY` than the current one (happens after server restart if `SECRET_KEY` changes)
- `COOKIE_SECURE=true` set but serving over HTTP (refresh cookie won't be sent)

### 403 Forbidden on an admin endpoint
**Cause:** Your user's role is insufficient.
**Fix:** Check your role with `GET /api/v1/auth/me`. Role hierarchy: viewer < analyst < org_admin < super_admin.

### 429 Too Many Requests
**Cause:** Rate limit exceeded.
- Login: 5 requests/minute
- Other: 100 requests/minute
**Fix:** Wait for the window to reset. For bulk operations, implement request throttling.

### Predictions return identical cost for different items
**Cause:** The ML preprocessor is receiving unexpected input that collapses to the same feature vector.
**Debug:** Call `GET /api/v1/ai/predictions/{return_id}/explain` and check `feature_snapshot` — confirm the feature values are different.

### File upload returns 400 "File type not allowed"
**Cause:** The uploaded file's MIME type doesn't match what `python-magic` detects in the file's magic bytes.
**Common cases:** A `.jpg` file that was renamed from a `.png` — the magic bytes will still say `image/png`.
**Fix:** Ensure the file is actually the type it claims to be.

---

## Database Issues

### Connection refused to Postgres
**In Docker:** Check `docker compose ps` — is the postgres container healthy? If not, check `docker compose logs postgres`.
**Locally:** Ensure Postgres is running: `pg_isready -h localhost -p 5432`

### `alembic upgrade head` fails: "relation already exists"
**Cause:** The DB has tables from a prior partial migration.
**Fix (development only — destroys data):**
```bash
docker exec returniq-postgres psql -U returniq -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
alembic upgrade head
```

### Disk full (Postgres stopped writing)
**Cause:** The `pgdata` volume or the host volume ran out of space.
**Fix:**
```bash
df -h                          # check disk usage
docker system prune -f         # remove unused images/volumes
```
Long-term: Move `pgdata` to a larger disk or enable S3 backups and reduce local retention.

---

## Frontend Issues

### Blank screen after login (redirect loop to /login)
**Cause:** The `bootstrapping` state in `AuthContext` failed to resolve — usually because the `/auth/refresh` call failed on mount.
**Debug:** Open browser DevTools → Network tab → look for a failed `/auth/refresh` call.
**Fix:** Clear cookies (`rl_refresh_token`) and log in again.

### "Failed to fetch" / CORS error
**Cause:** The `CORS_ORIGINS` env var doesn't include the frontend's origin.
**Fix:** Set `CORS_ORIGINS=https://your-frontend-domain.com` and restart the backend.

### Charts show no data / empty dashboard
**Cause:** No returns have been submitted yet, or the org has no data.
**Fix:** Submit a test return via **New Return** in the UI.

---

## Docker Issues

### Container restarts in a loop
```bash
docker compose logs backend --tail=100   # check the actual error
```

Common causes:
- Missing env vars
- Postgres not ready yet (usually self-heals via health checks)
- Port conflict (another service on 8000 or 3000)

### `node_modules not found` in frontend container
**Cause:** Volume mount overwrites the container's `node_modules`.
**Fix:** The Dockerfile runs `npm install` at build time. Make sure you're doing `docker compose up --build`, not just `docker compose up` after changing `package.json`.

---

## ML / Prediction Issues

### All predictions route to "manual_review"
**Cause:** The risk threshold configured for your org may be very low, or the model is outputting high risk scores for all inputs.
**Debug:** Check `GET /api/v1/ai/performance` — look at the decision distribution.

### "Model file not found" error
**Cause:** The ML artifacts (model.joblib, preprocessor.joblib, feature_columns.json) are missing from `backend/ml/artifacts/`.
**Fix:** These files must be present. They are committed to the repo — if missing, restore from a previous commit or your last backup.

---

## Getting Help

1. Check the logs first: `docker compose logs backend --tail=200`
2. Check the audit log: `GET /api/v1/admin/audit-logs`
3. Check the health endpoint: `GET /api/v1/admin/health`
4. Open an issue at [your repo URL]
5. Contact support: support@returniq.in
