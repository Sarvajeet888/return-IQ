# Test Coverage Matrix — ReturnIQ Enterprise

**Phase 9.1 deliverable** · Measured 1 August 2025 · `pytest --cov=app`

**Headline:** 193 tests · **74.8% backend coverage** (2,088 / 2,791 statements)

---

## Backend — By Module

| Module | Coverage | Tests | Assessment |
|---|---|---|---|
| `db/models.py` | **100%** | via all suites | ✅ |
| `models/enums.py` | **100%** | via all suites | ✅ |
| `services/feature_mapping.py` | **100%** | `test_ml_validation.py` | ✅ |
| `core/logging_config.py` | **98%** | `test_api_contract.py` | ✅ |
| `core/config.py` | **96%** | conftest + all | ✅ |
| `schemas/schemas.py` | **94%** | `test_api_contract.py` | ✅ |
| `services/auth_service.py` | **94%** | `test_auth.py`, security suite | ✅ |
| `main.py` | **93%** | all integration | ✅ |
| `core/rate_limit.py` | **92%** | `test_auth.py` | ✅ |
| `core/security.py` | **91%** | security suite | ✅ |
| `services/workflow_service.py` | **89%** | `test_workflow_engine.py` (27 tests) | ✅ |
| `api/v1/routes/auth.py` | **89%** | `test_auth.py`, security suite | ✅ |
| `api/v1/deps.py` | **86%** | all integration | ✅ |
| `api/v1/routes/users.py` | **80%** | password reset flow, profile | ✅ |
| `services/ml_service.py` | **78%** | `test_ml_validation.py` | 🟡 |
| `core/cache.py` | **78%** | `test_cache.py` (14 tests) | 🟡 |
| `api/v1/routes/returns.py` | **73%** | lifecycle + contract | 🟡 |
| `db/database.py` | **70%** | implicit | 🟡 |
| `api/v1/routes/return_mgmt.py` | **69%** | notes, timeline, bulk import | 🟡 |
| `db/store.py` | **67%** | all suites | 🟡 |
| `api/v1/routes/notifications.py` | **66%** | integration | 🟡 |
| `api/v1/routes/orgs.py` | **64%** | `test_rbac.py` | 🟡 |
| `api/v1/routes/misc.py` | **64%** | health probes, contract | 🟡 |
| `api/v1/routes/ai_ux.py` | **56%** | explain, override | 🟠 |
| `api/v1/routes/reports.py` | **49%** | summary, fraud, CSV | 🟠 |
| `api/v1/routes/org_mgmt.py` | **44%** | invite flow | 🟠 |
| `api/v1/routes/customers.py` | **44%** | create, blacklist | 🟠 |
| `api/v1/routes/workflows.py` | **41%** | rule CRUD via integration | 🟠 |
| `api/v1/routes/admin.py` | **40%** | auth-block tests only | 🟠 |
| `core/metrics.py` | **39%** | import-guarded paths untested | 🟠 |

---

## Why the Low-Coverage Modules Are Low

This is deliberate honesty, not hand-waving. Each has a specific reason:

| Module | Reason | Risk |
|---|---|---|
| `admin.py` (40%) | Every endpoint requires `super_admin`. Tests verify org_admin is *blocked* (the security-critical half) but don't exercise the happy path — that needs a super_admin fixture. | 🟡 Medium — admin endpoints are read-mostly |
| `metrics.py` (39%) | Half the file is behind `if _PROMETHEUS_AVAILABLE`. `prometheus_client` isn't installed in the test env, so those branches never execute. | 🟢 Low — failure mode is "no metrics", not "app breaks" |
| `workflows.py` (41%) | Rule CRUD is covered via integration tests; the SLA breach-check endpoint isn't. | 🟡 Medium |
| `customers.py` (44%) | Create/blacklist covered; search, filters, CSV export, analytics are not. | 🟡 Medium |
| `org_mgmt.py` (44%) | Invite flow covered; role change, member removal, branding, feature flags are not. | 🟠 **High — role change is a privilege-management path** |
| `reports.py` (49%) | Summary + fraud + CSV covered; carbon and customer reports, and date filtering, are not. | 🟢 Low — read-only |

**The one I'd fix first:** `org_mgmt.py`. Role changes and member removal are
access-control operations. They deserve the same test rigour the auth module got.

---

## Feature Coverage Matrix

### Backend Features

| Feature | Unit | Integration | Security | Status |
|---|:---:|:---:|:---:|---|
| Registration | ✅ | ✅ | ✅ | Covered |
| Login / JWT | ✅ | ✅ | ✅ | Covered |
| Account lockout | — | ✅ | ✅ | Covered |
| Refresh token rotation | — | ✅ | ✅ | Covered |
| Password reset | — | ✅ | ✅ | Covered (incl. single-use replay test) |
| RBAC / role enforcement | — | ✅ | ✅ | Covered |
| Multi-tenant isolation | ✅ | ✅ | ✅ | **Covered — 4 IDOR tests** |
| Return creation + ML scoring | — | ✅ | — | Covered |
| Return notes & timeline | — | ✅ | ✅ | Covered |
| Document upload | — | — | — | ❌ **Gap** |
| Bulk import | — | ✅ | — | Covered |
| Workflow rule evaluation | ✅ | ✅ | — | Covered (27 unit + 4 integration) |
| SLA tracking | — | — | — | ❌ **Gap** |
| Customer CRUD | — | ✅ | — | Partial |
| Customer blacklist | — | ✅ | — | Covered |
| Notifications | — | ✅ | — | Partial |
| Reports (summary/fraud) | — | ✅ | — | Covered |
| Reports (carbon/customer) | — | — | — | ❌ **Gap** |
| CSV export | — | ✅ | — | Covered |
| Admin panel | — | — | ✅ | Auth-block only |
| AI explainability | — | ✅ | — | Covered |
| Manual override | — | ✅ | — | Covered |
| Org member invite | — | ✅ | — | Covered |
| Org role change | — | — | — | ❌ **Gap — access control** |
| Feature flags | — | — | — | ❌ **Gap** |
| Caching | ✅ | — | — | Covered |
| Structured logging | — | ✅ | — | Covered |
| Health probes | — | ✅ | — | Covered |

### Frontend Features

| Feature | Status |
|---|---|
| All components | ❌ **Not started** — 0% coverage |

### Infrastructure

| Component | Verification method | Status |
|---|---|---|
| Docker builds | CI build stage | 🟡 Not executed in this environment |
| Migrations | `alembic upgrade head` in CI | ✅ Runs in CI |
| Monitoring config | YAML syntax validated | ✅ |
| Logging config | YAML syntax validated | ✅ |
| Backup scripts | `bash -n` syntax check | 🟡 Not executed against a real DB |
| Terraform | Not validated | ❌ Needs `terraform validate` |

---

## Prioritised Gap List

| Priority | Gap | Effort |
|---|---|---|
| 🔴 1 | Frontend has zero tests | 2–3 days |
| 🔴 2 | `org_mgmt` role change / member removal untested (access control) | 2 hours |
| 🟠 3 | Document upload untested (file-type bypass is a real attack surface) | 2 hours |
| 🟠 4 | Admin endpoints happy-path untested (needs super_admin fixture) | 3 hours |
| 🟠 5 | E2E browser tests not written | 1–2 days |
| 🟡 6 | Load test never executed — no real SLO numbers | 4 hours + a server |
| 🟡 7 | SLA breach detection untested | 1 hour |
| 🟡 8 | Carbon / customer reports untested | 1 hour |

---

## Trajectory

| Milestone | Tests | Coverage |
|---|---|---|
| End of Phase 8 | 33 | 60% |
| **End of Phase 9 (current)** | **193** | **74.8%** |
| Target for launch | ~260 | 85% backend + 80% frontend |

Closing gaps 1–4 above would put backend coverage at roughly 85% and give the
frontend its first safety net.
