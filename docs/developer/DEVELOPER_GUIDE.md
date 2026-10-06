# Developer Guide — ReturnIQ Enterprise

**For engineers joining Kalman Consultancy Services**
Version 3.0.0 · August 2026

If you are new here, read this end to end once. It should take 30 minutes and
save you a week.

---

## 1. Get It Running

```bash
git clone <repo> returniq && cd returniq
cp .env.example .env

# Generate the two required secrets
python3 -c "import secrets; print(secrets.token_hex(64))"   # → SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(64))"   # → API_KEY_HASH_PEPPER

docker compose up --build
```

Open http://localhost:3000 and register. You're the org_admin of a new org.

**Local development without Docker:**

```bash
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
export SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(64))")
export API_KEY_HASH_PEPPER=$(python3 -c "import secrets; print(secrets.token_hex(64))")
export DATABASE_URL=sqlite:///./dev.db
alembic upgrade head
uvicorn app.main:app --reload

# separate terminal
cd frontend && npm install && npm run dev
```

---

## 2. Folder Structure

```
backend/
├── app/
│   ├── main.py                 App factory, middleware registration
│   ├── api/v1/
│   │   ├── deps.py             Auth + org dependencies (get_current_user, require_role)
│   │   └── routes/             13 route modules — one per domain
│   ├── core/
│   │   ├── config.py           Settings (pydantic-settings)
│   │   ├── security.py         Hashing, JWT, API keys
│   │   ├── rate_limit.py       slowapi setup
│   │   ├── cache.py            Redis layer
│   │   ├── metrics.py          Prometheus
│   │   └── logging_config.py   JSON logs + correlation IDs
│   ├── db/
│   │   ├── models.py           SQLAlchemy models — 21 tables
│   │   ├── store.py            All database access
│   │   └── database.py         Engine, SessionLocal
│   ├── schemas/schemas.py      Pydantic request/response models
│   ├── services/               Business logic
│   └── models/enums.py
├── ml/
│   ├── predict.py              Model loading and inference
│   ├── preprocessor.py
│   ├── model_registry.py       Versioned artifacts, rollback
│   └── artifacts/              model.joblib, preprocessor.joblib, metadata
├── alembic/versions/           4 migrations
└── tests/
    ├── unit/                   Pure logic, no I/O
    ├── integration/            Real app, real DB, multi-step
    └── security/               Executable penetration tests

frontend/src/
├── pages/                      14 pages, one folder per domain
├── components/                 Shared UI + layout
├── store/AuthContext.jsx       Auth state
└── utils/api.js                All API calls

infra/                          Docker, nginx, monitoring, logging, terraform, scripts
docs/                           This documentation tree
qa/                             Test strategy, coverage matrix, reports
```

**Rule: routes are thin.** A route handler validates input, calls a service or
store function, and shapes the response. Business logic belongs in `services/`,
database access in `store.py`. If a route function exceeds ~40 lines, something
belongs elsewhere.

---

## 3. Coding Standards

### Python

- **Formatting:** ruff. `ruff check app/ ml/` must pass on `F` and `E9` codes.
  Config in `backend/ruff.toml` — read the comments, the ignores are deliberate.
- **Type hints on every function signature.** `from __future__ import annotations`
  at the top of every module.
- **Docstrings on anything non-obvious.** Explain *why*, not *what*. The code
  already says what it does.

```python
# Bad — restates the code
def check_unmapped_features(data: dict) -> list[str]:
    """Check for unmapped features."""

# Good — explains the consequence
def check_unmapped_features(data: dict) -> list[str]:
    """
    Report which categorical inputs fell outside the model's training
    vocabulary.

    _normalise() returns "" for anything unrecognised, and the OneHotEncoder
    turns "" into an all-zeros row. The model still returns a number, so
    nothing looks broken — but that prediction was made with a missing
    feature. The caller needs to know.
    """
```

### Naming

| Thing | Convention | Example |
|---|---|---|
| Functions, variables | `snake_case` | `build_feature_dict` |
| Classes | `PascalCase` | `WorkflowRule` |
| Constants | `UPPER_SNAKE` | `MAX_FILE_SIZE` |
| Private helpers | `_leading_underscore` | `_get_owned_return_or_404` |
| Route handlers | verb_noun | `create_return`, `list_customers` |
| Store functions | `get_` / `store_` / `update_` / `delete_` | `get_returns_for_org` |
| DB tables | plural snake_case | `return_requests` |
| React components | `PascalCase.jsx` | `AdminPanel.jsx` |

### Frontend

- Functional components with hooks. No class components.
- Inline styles using CSS variables from the design system. No CSS-in-JS library.
- All API calls go through `utils/api.js`. Never call `fetch` or `axios`
  directly from a component.
- **Never use localStorage or sessionStorage.** The access token lives in memory
  deliberately.

---

## 4. Database Standards

**Every tenant-scoped table has `org_id`.** No exceptions. If you add a table
holding customer data, it gets an `org_id` column and an index on it.

**Every query filters by org.** Use the `get_current_org` dependency and scope
the query. Never trust an ID from the URL alone — use the
`_get_owned_return_or_404` pattern:

```python
def _get_owned_return_or_404(return_id: str, org: dict) -> dict:
    r = store.get_return_by_id(return_id)
    if not r or r.get("org_id") != org["id"]:
        raise HTTPException(status_code=404, detail="Return not found")
    return r
```

Return **404, not 403**, for another org's resource. A 403 confirms the resource
exists, which leaks information.

### Migrations — the rule that was learned the hard way

**A migration that adds a column MUST update the SQLAlchemy model in the same
commit.**

Migration `c7f91a3d2e55` added `is_blacklisted` to `customers` but did not update
the `Customer` model. `store.update_customer()` filters updates with `hasattr()`,
so setting `is_blacklisted=True` was silently dropped. The endpoint returned 200.
Nothing happened. It went unnoticed for two phases until a Phase 9 test read the
field back.

Checklist for any schema change:
1. Update `db/models.py`
2. Generate the migration
3. Read the generated migration — autogenerate misses things
4. Write both `upgrade()` and `downgrade()`
5. Run `alembic upgrade head` then `alembic downgrade -1` then `upgrade head`
6. Add or update a test that reads the new field back

---

## 5. Testing Standards

218 tests, 77% backend coverage. Read `qa/strategy/TEST_STRATEGY.md` before
adding tests.

```bash
cd backend
pytest -v                      # all
pytest tests/security/ -v      # release blocker if any fail
pytest --cov=app --cov-report=html
```

### Rules

**Assert behaviour, not implementation.**
```python
assert r.status_code == 404              # good
assert mock_store.get_return.called      # brittle
```

**Name the test after what it protects.**
```python
def test_idor_cannot_read_another_orgs_return():   # good
def test_get_return():                              # useless when it fails
```

**Write failure messages that state the consequence.**
```python
assert r.status_code == 404, "CROSS-TENANT DATA LEAK: org B read org A's return"
```

**Found a bug? Write the failing test first.** Watch it fail, then fix. A test
you never saw fail may not be testing anything.

### The conftest trap

Environment variables are set at `conftest.py` **import time**, not in a fixture.
Pytest imports all test modules during collection, before any fixture runs, and
several app modules do `settings = get_settings()` at module level with slowapi
evaluating `@limiter.limit(...)` at decoration time. Setting env vars in a
fixture silently stops working the moment a test file imports app code at module
level — 57 tests once failed with HTTP 429 because of exactly this.

---

## 6. Git Workflow

```
main       ← production. Protected. Deploys on merge.
  ↑
develop    ← integration. Deploys to staging.
  ↑
feature/*  ← your work
fix/*      ← bug fixes
```

**Branch naming:** `feature/workflow-rule-builder`, `fix/blacklist-not-persisting`

**Commit messages:**
```
<type>: <what changed>

<why it changed, if not obvious>

type: feat | fix | docs | test | refactor | chore | perf
```

Good:
```
fix: add is_blacklisted to Customer model

The Phase 5 migration added this column to the table but not the ORM
model. store.update_customer() filters with hasattr(), so blacklisting
was silently dropped before reaching the DB.
```

### Pull requests must

- Pass all 218 tests
- Pass `ruff check app/ ml/ --select F,E9` with zero errors
- Pass Bandit with zero high/medium findings
- Not reduce coverage below 75%
- **Pass the security suite — no exceptions.** A failure there is an exploitable
  vulnerability, not a flaky test
- Include tests for new behaviour
- Update docs if behaviour changed

---

## 7. Adding a New Endpoint — Worked Example

Adding `GET /api/v1/returns/{id}/history`:

**1. Schema** (`schemas/schemas.py`) if you need a new request/response shape.

**2. Store function** (`db/store.py`):
```python
def get_return_history(return_request_id: str) -> list[dict]:
    with SessionLocal() as db:
        rows = db.execute(
            select(models.ReturnHistory)
            .where(models.ReturnHistory.return_request_id == return_request_id)
            .order_by(models.ReturnHistory.created_at.asc())
        ).scalars().all()
        return [_to_dict(r) for r in rows]
```

**3. Route** (`api/v1/routes/return_mgmt.py`):
```python
@router.get("/api/v1/returns/{return_id}/history")
async def get_history(
    return_id: str,
    org: dict = Depends(get_current_org),
) -> list:
    _get_owned_return_or_404(return_id, org)   # ownership guard first
    return store.get_return_history(return_id)
```

**4. Tests** — minimum three:
```python
def test_history_returns_events(app_client): ...
def test_history_requires_auth(app_client): ...
def test_history_blocked_for_other_org(app_client): ...   # non-negotiable
```

**5. Frontend** (`utils/api.js`):
```javascript
getReturnHistory: (id) => client.get(`${BASE}/returns/${id}/history`).then(r => r.data),
```

**6. Docs** — update `docs/api/API_GUIDE.md`.

### Do not register a route path twice

`misc.py` once defined `GET /api/v1/customers`, and Phase 5 added a full
customers router on the same path. Because `misc.router` is included first,
FastAPI matched the older handler and the entire Phase 5 customers router was
unreachable dead code for two phases — with no startup error.

`test_no_duplicate_route_paths_registered` now catches this. Don't remove it.

---

## 8. Release Process

```
feature branch → PR → review → merge to develop → staging deploy
                                                        │
                                                   verify
                                                        │
                                    PR develop → main → manual approval
                                                        │
                                              production deploy
```

Production deploys run `infra/scripts/deploy.sh`, which:
1. Takes a database backup **before** anything else
2. Pulls, builds, runs migrations
3. Waits for the health check
4. Runs smoke tests
5. Tags the release

Rollback: `docs/release/ROLLBACK_PLAN.md`.

**Versioning:** semantic. MAJOR for breaking API changes, MINOR for features,
PATCH for fixes. The API is versioned in the path (`/api/v1/`) — breaking
changes get `/api/v2/`, they do not modify `/api/v1/`.

---

## 9. Things That Will Bite You

| Gotcha | What happens | Avoid by |
|---|---|---|
| Adding a migration without updating the model | Field silently ignored on write | Update both in one commit |
| Registering a duplicate route path | Later router becomes dead code, no error | The duplicate-path test |
| Setting test env vars in a fixture | Rate limits fire, 429s everywhere | Set them at conftest import time |
| Forgetting the org scope on a query | Cross-tenant data leak | Always use `get_current_org` + the ownership guard |
| Using `KEYS` in Redis | Blocks the server on large datasets | Use `SCAN` |
| Returning 403 for another org's resource | Confirms the resource exists | Return 404 |
| Claiming rule-based logic is "AI" | Damages credibility; contradicts AI_TRANSPARENCY.md | Say what it is |
| Quoting the R² of 0.9993 | Unverified, invites scrutiny it won't survive | Describe the model qualitatively |

---

## 10. Where to Look

| Question | Document |
|---|---|
| How does the system fit together? | `docs/architecture/SYSTEM_ARCHITECTURE.md` |
| What does this endpoint do? | `docs/api/API_GUIDE.md` |
| What is real ML vs rules? | `docs/ai/AI_TRANSPARENCY.md` |
| How do I deploy? | `docs/operations/DEPLOYMENT.md` |
| What's broken / known issues? | `docs/release/KNOWN_ISSUES.md` |
| How do I test? | `qa/strategy/TEST_STRATEGY.md` |
| What's the security posture? | `docs/standards/SECURITY_AUDIT_PHASE6.md` |
| Can we claim this feature? | `docs/product/PRODUCT_CLAIMS_AUDIT.md` |
