# Test Strategy — ReturnIQ Enterprise

**Phase 9.1 deliverable** · Version 1.0 · 1 August 2025

---

## Purpose

Define what we test, how, and what "good enough to ship" means. This document
is the reference for anyone adding tests or reviewing a PR.

---

## Testing Pyramid

```
                    ▲
                   ╱ ╲        E2E (Playwright)          — few, slow, high confidence
                  ╱   ╲       Real browser, real flows
                 ╱─────╲
                ╱       ╲     Integration (pytest)      — 58 tests
               ╱         ╲    Full API, real DB, multi-step workflows
              ╱───────────╲
             ╱             ╲  Unit (pytest / Vitest)    — 135 tests
            ╱_______________╲ Pure logic, mocked dependencies
```

**Rationale for the shape:** the expensive bugs in this codebase have all been
in the seams — a migration that added a column the ORM didn't know about, a
middleware rename that broke an import, a cache key that could cross tenants.
Unit tests alone would have missed every one. So integration coverage is
weighted heavier here than a textbook pyramid would suggest.

---

## Test Categories

### 1. Unit Tests — `backend/tests/unit/`
Pure functions and isolated classes. No database, no HTTP, no network.

| File | What it protects |
|---|---|
| `test_workflow_engine.py` | Rule evaluator — boundaries, unknown keys, malformed input |
| `test_cache.py` | Graceful degradation, **cross-tenant key isolation** |
| `test_ml_validation.py` | Feature mapping ↔ model vocabulary alignment |
| `test_ml_preprocessor.py` | Preprocessor shape, determinism, unknown categories |
| `test_model_registry.py` | Versioning, atomic writes, rollback |

**Rule:** a unit test must run in under 50ms and must not touch I/O.

### 2. Integration Tests — `backend/tests/integration/`
Real FastAPI app, real SQLite database, real ML model. Multi-step flows.

| File | What it protects |
|---|---|
| `test_workflows_e2e.py` | Full return lifecycle, rule firing, bulk import, password reset |
| `test_api_contract.py` | OpenAPI spec, auth enforcement, pagination bounds, error codes |

### 3. Security Tests — `backend/tests/security/`
Executable penetration tests. Each one is a real attack attempt.

| Category | Coverage |
|---|---|
| SQL injection | 6 payloads across login and search |
| XSS | 4 payloads on stored fields |
| JWT tampering | `alg=none`, signature flip, payload edit (privilege escalation) |
| IDOR / multi-tenancy | Cross-org read, write, list-leak |
| Privilege escalation | Admin endpoints, mass-assignment on profile |
| Crypto | Hashing, salting, no plaintext leakage |
| Password policy | 5 weak-password variants |
| Misconfiguration | Security headers, user enumeration, stack-trace leakage |

**A failure in this suite is a release blocker, not a bug ticket.**

### 4. Frontend Tests — `frontend/src/**/*.test.jsx`
Vitest + React Testing Library. Components, hooks, context, protected routes.

### 5. E2E Tests — `qa/e2e/`
Playwright. Real browser, real user journeys.

### 6. Performance — `infra/scripts/load_test.js`
k6. Load, stress, and spike scenarios against a deployed instance.

---

## Coverage Targets

| Layer | Target | Current | Status |
|---|---|---|---|
| Backend overall | ≥ 85% | **75%** | 🟡 Below target |
| Backend — services | ≥ 90% | 89% (workflow), 94% (auth), 78% (ml) | 🟡 Close |
| Backend — core | ≥ 90% | 91% (security), 96% (config), 98% (logging) | ✅ |
| Backend — models/schemas | ≥ 95% | 100% / 94% | ✅ |
| Frontend | ≥ 80% | Not yet measured | ❌ Not started |
| Security suite | 100% pass | 36/36 | ✅ |

**Coverage is a floor, not a goal.** A line executed by a test that asserts
nothing is worse than uncovered — it produces false confidence. Every test in
this suite makes a meaningful assertion about behaviour.

---

## What We Deliberately Do NOT Test

Being explicit about this prevents wasted effort and false expectations:

| Not tested | Why |
|---|---|
| Third-party library internals | SQLAlchemy, FastAPI, XGBoost have their own suites |
| Alembic migration SQL correctness | Verified by running `alembic upgrade head` in CI, not unit tests |
| Terraform plans | Requires a real AWS account; verified manually before apply |
| Docker image builds | Verified in CI build stage, not in pytest |
| Actual email delivery | SMTP not yet wired (Known Issue KI-001) |
| Model prediction *accuracy* | Requires labelled ground-truth data we don't have yet (Phase 4 finding). We test the pipeline, not the model's correctness. |

That last one matters and is worth stating plainly: **these tests prove the ML
pipeline runs correctly, not that its predictions are right.** Prediction
quality can only be measured once real outcome labels accumulate via
`PATCH /returns/{id}/outcome`.

---

## Test Data Strategy

- **Isolation:** every test creates its own organisation with a UUID-suffixed
  email. Tests never share fixtures that mutate state.
- **Database:** a fresh temp SQLite file per session (`pytest_configure`).
- **Rate limits:** disabled suite-wide via env vars set at conftest import
  time. Rate limiting is tested explicitly in the security suite, not
  incidentally by every other test.

### A hard-won lesson, documented

Environment variables **must** be set at `conftest.py` import time, not in a
fixture. Pytest imports all test modules during collection, which happens
before any fixture runs. Several app modules do `settings = get_settings()` at
module level, and slowapi evaluates `@limiter.limit(settings.RATE_LIMIT_REGISTER)`
at decoration time — so the values freeze on first import. Setting them in a
session fixture silently did nothing once test files began importing app code
at module level, and 57 tests started failing with HTTP 429.

---

## Quality Gates (enforced in CI)

A pull request cannot merge unless:

| Gate | Threshold |
|---|---|
| All tests pass | 100% |
| Security suite | 100% pass — no exceptions |
| Ruff correctness codes (F, E9) | Zero |
| Bandit high/medium severity | Zero |
| Backend coverage | ≥ 75% (raise to 85% once frontend tests land) |
| No new `# type: ignore` without a comment | Manual review |

---

## Running the Tests

```bash
cd backend

# Everything
pytest -v

# By category
pytest tests/unit/ -v
pytest tests/integration/ -v
pytest tests/security/ -v          # release blocker if any fail

# With coverage
pytest --cov=app --cov-report=term --cov-report=html
open htmlcov/index.html

# Static analysis
ruff check app/ ml/
bandit -r app/ ml/ -ll -ii

# Frontend
cd ../frontend && npm test

# Load test (needs a running instance)
k6 run --env BASE_URL=http://localhost infra/scripts/load_test.js
```

---

## Adding a New Test

1. **Pick the right layer.** Pure logic → unit. Crosses a boundary → integration.
2. **Assert behaviour, not implementation.** `assert response.status_code == 404`
   is good; `assert mock_store.get_return.call_count == 1` is brittle.
3. **Name the test after the behaviour it protects**, not the function it calls:
   `test_idor_cannot_read_another_orgs_return`, not `test_get_return`.
4. **Write a failure message that explains the consequence:**
   `assert r.status_code == 404, "CROSS-TENANT DATA LEAK: org B read org A's return"`
5. **If you found a bug, write the test first**, watch it fail, then fix.
