# What's fixed so far

## Verified working (tested live with pytest + manual TestClient runs)
1. **Real persistent DB** — SQLAlchemy models (`app/db/models.py`) + Postgres/SQLite
   engine (`app/db/database.py`). `store.py` fully rewritten to hit the DB while
   keeping the exact same function signatures the routes/services already used.
2. **Alembic migrations** — `alembic/` set up, initial migration generated and
   confirmed to create all 12 tables on a fresh DB.
   Run: `alembic upgrade head` (reads `DATABASE_URL` from env, defaults to
   `sqlite:///./returniq_dev.db` if unset).
3. **SECRET_KEY / API_KEY_HASH_PEPPER** — now required via env var in production
   (hard `RuntimeError` on startup if missing), and persisted to a local file in
   dev so restarts don't invalidate every token.
4. **Refresh token rotation + theft detection** — `refresh_tokens` table tracks
   jti, rotation, and revocation. Reusing an already-rotated refresh token now
   revokes every session for that user.
5. **httpOnly cookie for refresh token** — no longer sent in the JSON body or
   stored in localStorage. Access token still returned in the body; the
   frontend now keeps it in memory only (see #11 below).
6. **Exception handler no longer leaks internals** — generic message to the
   client, full traceback + request-ID goes to structured server-side logs
   (`app/core/logging_config.py`).
7. **Rate limiting actually enforced** — `slowapi`, stricter limits on
   `/auth/login` and `/auth/register`, Redis-backed storage available via
   `USE_REDIS_RATE_LIMIT=true`.
8. **Account lockout** — unchanged logic, now backed by a real DB table
   instead of an in-memory dict (still confirmed working: 5 bad logins → 429).
9. **Logout revocation** — access tokens can now actually be invalidated
   (`revoked_access_tokens` table), confirmed a token stops working immediately
   after logout.
10. **Tests** — `backend/tests/` — 15 tests covering auth, refresh rotation,
    lockout, RBAC/org isolation, and the returns scoring endpoint. All passing
    (unaffected by the docker-compose/frontend changes below — no backend
    Python files were touched to make them).
11. **`docker-compose.yml`** — now runs real Postgres (`postgres:16-alpine`,
    persistent `pgdata` volume, healthcheck) and Redis (`redis:7-alpine`,
    healthcheck) services. `backend` waits on both being healthy, gets
    `DATABASE_URL`/`REDIS_URL`/`USE_REDIS_RATE_LIMIT=true` wired in, and runs
    `alembic upgrade head` before `uvicorn` on every start. Secrets
    (`SECRET_KEY`, `API_KEY_HASH_PEPPER`, `POSTGRES_PASSWORD`) come from a
    root `.env` file (see `.env.example`) instead of being hardcoded.
12. **Frontend (`frontend/src/utils/api.js`, `AuthContext.jsx`)** — access
    token now lives in memory only (`setAccessToken`/`getAccessToken` in
    `api.js`), never in `localStorage`. `withCredentials: true` on every
    request so the httpOnly `rl_refresh_token` cookie is sent automatically.
    A response interceptor does a single-flight silent refresh on `401` and
    retries the original request once. `AuthContext` runs the same silent
    refresh on mount to rehydrate the session after a hard reload, exposing a
    `bootstrapping` flag that `App.jsx`'s route guards wait on so a reload
    doesn't flash the logged-out UI.

## Not yet done (tell me if you want this too)
- **"5 AI models" labeling** — fraud/damage/resale/carbon are still rule-based
  heuristics; only cost prediction is real XGBoost. Not relabeled yet in the
  API response or README.
- **`Register.jsx` pre-existing bug** — it calls `api.register()` and sets
  tokens/user directly instead of going through `AuthContext`'s `register()`,
  so the React `user` state doesn't update after registering and `RequireAuth`
  redirects back to `/login` even though the session is otherwise valid. This
  predates the docker-compose/frontend fixes above and wasn't in scope, but is
  worth fixing if `Register.jsx` is ever revisited.

## How to run

### Local (no Docker)
```
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```
Set `ENVIRONMENT=production`, `SECRET_KEY`, `API_KEY_HASH_PEPPER`, and
`DATABASE_URL` (postgresql://...) before deploying for real.

### Docker (Postgres + Redis + backend + frontend)
```
cp .env.example .env   # then fill in real SECRET_KEY / API_KEY_HASH_PEPPER / POSTGRES_PASSWORD
docker compose up --build
```
Backend: http://localhost:8000 (health check at `/health`). Frontend:
http://localhost:3000.

