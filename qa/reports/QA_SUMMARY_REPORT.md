# QA Summary Report — ReturnIQ Enterprise v3.0.0

**Phase 9.12 deliverable** · 1 August 2025
**Verification method:** all tests were **executed**, not just authored.

---

## Executive Summary

| Metric | Before Phase 9 | After Phase 9 | Change |
|---|---|---|---|
| Automated tests | 33 | **218** | +185 |
| Backend coverage | 60% | **77%** | +17pp |
| Security tests | 0 | **36** | +36 |
| Ruff correctness errors | 252 | **0** | −252 |
| Bandit high/medium findings | — | **0** | clean |
| Real bugs found & fixed | — | **7** | — |

**Result: 218/218 tests passing. Zero correctness lint errors. Zero
high/medium security findings across 4,969 lines.**

---

## Bugs Found by Testing

Phase 9's value is not the test count — it's these. Every one was found by a
test, not by reading code.

### 🔴 BUG-01 — Application would not boot
**Severity:** Critical · **Introduced:** Phase 8 · **Found by:** first test run

Phase 8 overwrote `app/core/logging_config.py`, deleting the `RequestIdMiddleware`
class that `main.py` imports. Every request would have failed at startup with
`ImportError`. Also left a duplicate `add_middleware` registration.

**Fix:** Added `RequestIdMiddleware = RequestIDMiddleware` alias, removed the
duplicate registration.

---

### 🔴 BUG-02 — Cache module crashed on import
**Severity:** Critical · **Introduced:** Phase 8 · **Found by:** `test_cache.py`

`app/core/cache.py` did `from app.core.config import settings`, but `config.py`
only exports `get_settings()`. Any import of the cache module raised
`ImportError`.

**Fix:** Changed to `get_settings()` and assigned the module-level singleton.

---

### 🔴 BUG-03 — Blacklist feature did nothing
**Severity:** High · **Introduced:** Phase 5 · **Found by:** `test_workflows_e2e.py`

The Phase 5 migration added `is_blacklisted` and `notes` columns to the
`customers` table, but the `Customer` SQLAlchemy model was never updated.
Since `store.update_customer()` filters updates with `hasattr()`, setting
`is_blacklisted=True` was **silently dropped before reaching the database**.
The endpoint returned 200. Nothing happened.

**Fix:** Added both columns to the `Customer` model. Schema drift between a
migration and its ORM model is invisible until something reads the field back.

---

### 🟠 BUG-04 — Phase 5 customer endpoints were unreachable
**Severity:** High · **Introduced:** Phase 5 · **Found by:** FastAPI duplicate-operation-id warning during a test run

`misc.py` defined `GET /api/v1/customers` and `/api/v1/customers/{id}`.
Phase 5 added a full customers router on the same paths — but `misc.router` is
registered **first** in `main.py`, so FastAPI matched the older, simpler
handlers. The Phase 5 endpoints (pagination, search, risk/blacklist filters,
per-customer analytics) were dead code for two phases. It also corrupted the
generated OpenAPI spec.

**Fix:** Removed the legacy routes from `misc.py`. Added
`test_no_duplicate_route_paths_registered` so this can't recur.

---

### 🟠 BUG-05 — ML predictions silently degraded
**Severity:** Medium-High · **Pre-existing** · **Found by:** `test_api_contract.py`

`feature_mapping._normalise()` returns `""` for any value outside the model's
training vocabulary, which one-hot encodes to all zeros. So a request with
`courier: "FedEx"` (not one of the six couriers the model knows) returned a
**confident-looking prediction made with a missing feature**. The caller had
no way to know.

**Fix:** Added `check_unmapped_features()`. The API now returns a
`data_quality_warnings` array naming the unrecognised value, explaining the
prediction was degraded, and listing the valid alternatives.

---

### 🟡 BUG-06 — Duplicate registration returned the wrong status code
**Severity:** Low · **Found by:** `test_api_contract.py`

Returned `400 Bad Request`; `API_GUIDE.md` documents `409 Conflict`, and
`/org/members/invite` already used 409 for the identical condition.

**Fix:** Changed to 409. Both duplicate-email paths are now consistent.

---

### 🟡 BUG-07 — Duplicate `get_users_for_org` in store.py
**Severity:** Low · **Introduced:** Phase 5 · **Found by:** `ruff F811`

Identical function defined twice. Harmless but dead code.

**Fix:** Removed the duplicate.

---

### Bonus: test-infrastructure bug

`conftest.py` set environment variables in a session fixture. Pytest imports
all test modules during **collection**, before any fixture runs — and several
app modules do `settings = get_settings()` at module level, with slowapi
evaluating `@limiter.limit(...)` at decoration time. Once test files began
importing app code at module level, the rate-limit overrides silently stopped
applying and **57 tests failed with HTTP 429**.

**Fix:** Moved env setup to conftest import time. Documented in
`TEST_STRATEGY.md` because it is a trap anyone extending the suite could hit.

---

## Test Suite Breakdown

| Suite | Tests | Focus |
|---|---:|---|
| `tests/unit/` | 66 | Workflow engine, cache, ML mapping, preprocessor, model registry |
| `tests/integration/` | 83 | Full lifecycle, API contract, org management |
| `tests/security/` | 36 | OWASP Top 10 penetration tests |
| Legacy (`tests/*.py`) | 33 | Auth, RBAC, returns |
| **Total** | **218** | |

---

## Security Test Results — 36/36 Pass

| Attack | Tests | Result |
|---|---:|---|
| SQL injection (login + search) | 9 | ✅ All rejected; users table intact after `DROP TABLE` attempts |
| XSS payloads on stored fields | 4 | ✅ Returned as inert JSON strings |
| JWT `alg=none` | 1 | ✅ Rejected — Phase 6 allowlist holds |
| JWT signature tampering | 1 | ✅ Rejected |
| JWT payload tampering (→ super_admin) | 1 | ✅ Rejected |
| Garbage / missing tokens | 2 | ✅ Rejected |
| **IDOR — cross-org read** | 1 | ✅ 404, no data leak |
| **IDOR — cross-org write** | 1 | ✅ 404 |
| **IDOR — cross-org timeline** | 1 | ✅ 404 |
| **List endpoint tenant leak** | 1 | ✅ Scoped correctly |
| Privilege escalation — admin endpoints | 1 | ✅ 403 |
| Mass assignment — self-promote via profile | 1 | ✅ Blocked |
| Password hashing (bcrypt, salted) | 3 | ✅ Verified |
| Weak password policy | 5 | ✅ All 5 rejected |
| Security headers | 1 | ✅ Present |
| User enumeration on forgot-password | 1 | ✅ Prevented |
| Stack-trace leakage | 1 | ✅ None |

Plus 4 cross-tenant tests in `test_org_management.py` covering role changes,
member removal, and feature-flag isolation.

---

## Static Analysis

| Tool | Scope | Result |
|---|---|---|
| **Ruff** (F, E9 correctness) | `app/`, `ml/` | ✅ **All checks passed** |
| Ruff (full ruleset) | `app/`, `ml/` | 11 remaining, all documented as intentional in `ruff.toml` |
| **Bandit** | 4,969 lines | ✅ **0 high, 0 medium** |

Ruff went from **252 → 0** correctness errors. The 11 remaining full-ruleset
findings are deliberate: blind `except` in cache/metrics (observability must
never crash the app), `E402` in `main.py` (logging must be configured before
app imports), and `(str, Enum)` over `StrEnum` for serialisation consistency.

---

## What Was NOT Tested

Stated plainly so nobody mistakes this report for more than it is:

| Not verified | Why | Risk |
|---|---|---|
| Frontend — any of it | Vitest suite not written | 🔴 High — 0% coverage on 4,013 lines |
| E2E browser flows | Playwright not written | 🟠 Medium |
| Load / performance | k6 script exists but was never executed — **no real SLO numbers** | 🟠 Medium |
| Docker image builds | No Docker daemon available here | 🟡 Verified in CI instead |
| Terraform | No AWS account | 🟡 Needs `terraform validate` |
| Email delivery | SMTP not wired (KI-001) | 🔴 Blocks launch |
| **ML prediction accuracy** | Requires labelled ground truth that doesn't exist yet | 🟠 See below |
| Accessibility (screen readers) | Requires a real browser | 🟠 Audit exists, untested |

**On ML accuracy — worth being unambiguous:** these tests prove the pipeline
executes correctly. They say nothing about whether the predictions are *right*.
That can only be measured once real outcome labels accumulate via
`PATCH /returns/{id}/outcome`. The reported R² of 0.9993 remains unverified
(Known Issue KI-009).

---

## Release Recommendation

**Conditional pass for a controlled pilot. Not approved for public launch.**

### Approved
- Backend correctness, security posture, and multi-tenant isolation are
  verified by executed tests
- No high or medium severity static-analysis findings
- All 7 discovered bugs fixed and covered by regression tests

### Blocking public launch
| # | Blocker | Owner |
|---|---|---|
| 1 | Frontend has zero automated tests | Engineering |
| 2 | SMTP not wired — password reset is non-functional in production | Engineering |
| 3 | No consent capture at registration (DPDP Act) | Engineering + Legal |
| 4 | Customer PII stored in plaintext | Engineering |
| 5 | Load test never executed — SLOs are aspirational, not measured | Engineering |
| 6 | Legal review of Privacy Policy and ToS not performed | Legal |

### Sign-off

| Role | Name | Date | Decision |
|---|---|---|---|
| QA / Engineering | | | ☐ Pass ☐ Conditional ☐ Fail |
| Security | | | ☐ Pass ☐ Conditional ☐ Fail |
| Product | | | ☐ Go ☐ No-Go |
