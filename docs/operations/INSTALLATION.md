# Installation Guide — ReturnIQ Enterprise

## Prerequisites

| Tool | Minimum Version | Purpose |
|---|---|---|
| Docker | 24.0 | Container runtime |
| Docker Compose | 2.20 | Multi-container orchestration |
| Python | 3.11 | Local development (optional) |
| Node.js | 18.0 | Frontend development (optional) |
| PostgreSQL | 15 | Database (via Docker or standalone) |
| Redis | 7 | Rate limiting (via Docker or standalone) |

---

## Option A — Docker Compose (Recommended for Production)

### 1. Clone and configure

```bash
git clone <repo-url> returniq
cd returniq
cp .env.example .env
```

Edit `.env` and fill in required values:

```bash
# REQUIRED — generate with: python3 -c "import secrets; print(secrets.token_hex(64))"
SECRET_KEY=<64-char-hex-string>
API_KEY_HASH_PEPPER=<another-64-char-hex-string>
POSTGRES_PASSWORD=<strong-db-password>

# OPTIONAL — defaults are fine for local dev
DEMO_MODE=true          # Set to false in production
ENVIRONMENT=development # Set to production in production
CORS_ORIGINS=http://localhost:3000
```

⚠️ **Never commit `.env` to version control.** It is in `.gitignore` by default.

### 2. Build and start

```bash
docker compose up --build
```

First boot will:
1. Start PostgreSQL and Redis
2. Wait for both to pass health checks
3. Run `alembic upgrade head` to create all tables
4. Start the backend API on port 8000
5. Build and start the frontend on port 3000

### 3. Verify

```bash
curl http://localhost:8000/health
# → {"status": "ok", "version": "3.0.0"}
```

Open http://localhost:3000 in your browser.

### 4. Create your first account

Open http://localhost:3000/register and create your organisation.

---

## Option B — Local Development (No Docker)

### Backend

```bash
cd backend

# Create virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Set environment variables (or create a .env file in backend/)
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(64))")
export API_KEY_HASH_PEPPER=$(python3 -c "import secrets; print(secrets.token_hex(64))")
export DATABASE_URL=sqlite:///./returniq_dev.db   # SQLite for local dev
export DEMO_MODE=true

# Run migrations
alembic upgrade head

# Start the server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

API available at http://localhost:8000
Swagger UI at http://localhost:8000/docs

### Frontend

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

Frontend available at http://localhost:5173

---

## Option C — Standalone Backend with Existing Postgres

If you already have a Postgres server:

```bash
export DATABASE_URL=postgresql+psycopg2://user:password@host:5432/returniq
export SECRET_KEY=<64-char-hex>
export API_KEY_HASH_PEPPER=<64-char-hex>

cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| `SECRET_KEY` | ✅ Yes | Error on startup | JWT signing key — 64-char hex minimum |
| `API_KEY_HASH_PEPPER` | ✅ Yes | Error on startup | API key hashing pepper |
| `DATABASE_URL` | Yes | `sqlite:///./returniq_dev.db` | SQLAlchemy connection string |
| `REDIS_URL` | No | `redis://localhost:6379` | Redis connection string |
| `USE_REDIS_RATE_LIMIT` | No | `false` | Use Redis for rate limiting (vs. in-memory) |
| `DEMO_MODE` | No | `true` | Returns `demo_token` in forgot-password — **set false in production** |
| `ENVIRONMENT` | No | `development` | Set to `production` to enable security hardening |
| `CORS_ORIGINS` | No | `["http://localhost:3000"]` | Comma-separated allowed origins |
| `COOKIE_SECURE` | No | `false` | Set `true` in production (requires HTTPS) |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | `15` | JWT access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | No | `7` | Refresh token TTL |
| `MAX_FAILED_LOGIN_ATTEMPTS` | No | `5` | Lockout threshold |
| `LOCKOUT_MINUTES` | No | `15` | Account lockout duration |

---

## Troubleshooting Installation

**`alembic upgrade head` fails: "no such table"**
The SQLite dev DB doesn't exist yet. Run `alembic upgrade head` first — it creates the file.

**`RuntimeError: SECRET_KEY is required in production`**
You set `ENVIRONMENT=production` without setting `SECRET_KEY`. Either set the key or
remove the environment override.

**Docker: `backend exited with code 1` immediately**
Check logs: `docker compose logs backend`. Usually a missing `.env` value or
Postgres not ready yet (health checks usually handle this, but the first cold boot
can sometimes need a `docker compose restart backend`).

**Frontend: `vite: not found`**
Run `npm install` in the `frontend/` directory first.

**Port 5432 already in use**
Change the Docker Compose postgres port mapping from `"5432:5432"` to `"5433:5432"`
and update `DATABASE_URL` accordingly.
