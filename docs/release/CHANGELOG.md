# CHANGELOG — ReturnIQ Enterprise

All notable changes to this project are documented in this file.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning follows [Semantic Versioning](https://semver.org/).

---

## [3.0.0] — 2025-08-01 — Phase 7: Legal, Compliance & Documentation

### Added
- `docs/legal/PRIVACY_POLICY.md` — full privacy policy covering all data types, DPDP Act rights, retention periods
- `docs/legal/TERMS_OF_SERVICE.md` — ToS covering acceptable use, AI limitations, liability limits, governing law
- `docs/legal/COOKIE_POLICY.md` — cookie inventory (1 essential cookie only)
- `docs/legal/AI_TRANSPARENCY.md` — honest breakdown of what is real ML vs rule-based
- `docs/legal/DATA_RETENTION.md` — full retention schedule and deletion process
- `docs/compliance/DPDP_CHECKLIST.md` — India DPDP Act 2023 compliance self-assessment with open action items
- `docs/compliance/LICENSE_AUDIT.md` — open source license audit for all backend and frontend dependencies
- `docs/compliance/THIRD_PARTY_NOTICES.md` — required third-party attribution
- `docs/compliance/ACCESSIBILITY_AUDIT.md` — WCAG 2.1 AA code review with remediation priorities
- `docs/guides/INSTALLATION.md` — Docker, local dev, and standalone install options
- `docs/guides/DEPLOYMENT.md` — production deployment, scaling, backup, and disaster recovery
- `docs/guides/USER_GUIDE.md` — end-user guide for all platform features
- `docs/guides/ADMIN_GUIDE.md` — admin guide: team management, API keys, workflow rules, monitoring
- `docs/guides/API_GUIDE.md` — full API reference with request/response examples for all 60+ endpoints
- `docs/guides/TROUBLESHOOTING.md` — common issues and fixes for backend, DB, frontend, Docker, and ML
- `docs/release/PRODUCTION_CHECKLIST.md` — go-live sign-off checklist
- `docs/release/CHANGELOG.md` (this file)
- `docs/release/RELEASE_NOTES.md`
- `docs/release/KNOWN_ISSUES.md`
- `docs/release/ROLLBACK_PLAN.md`

---

## [2.6.0] — 2025-08-01 — Phase 6: Security Hardening

### Security Fixes (Critical)
- **Fixed: `demo_token` exposed in production** — forgot-password endpoint now gates the
  demo token behind `DEMO_MODE=true AND ENVIRONMENT != production`. In production, the
  token is never returned in the API response.
- **Fixed: JWT `alg=none` attack vector** — all token verification calls now pass an
  explicit `algorithms=[settings.ALGORITHM]` allowlist to `python-jose`
- **Fixed: API key timing attack** — switched from `==` to `hmac.compare_digest()` for
  constant-time key comparison
- **Fixed: `python-jose` CVE** — upgraded from 3.3.0 to 3.4.0

### Added
- Security response headers middleware (ASGI): `X-Content-Type-Options`, `X-Frame-Options`,
  `Referrer-Policy`, `Permissions-Policy`, `Content-Security-Policy`, `HSTS`
- File upload MIME type validation using `python-magic` (magic bytes) — not just the
  `Content-Type` header, which clients can spoof
- Non-root Docker user (`appuser`) — containers no longer run as root
- `python-magic==0.4.27` added to `requirements.txt`
- `SECURITY_AUDIT_PHASE6.md` documenting full OWASP Top 10 assessment
- OWASP A10 (SSRF) note: webhook URL dispatch blocked until private IP range validation
  is implemented

### Changed
- Dockerfile: added `groupadd appuser && useradd appuser && USER appuser`
- `docker-compose.yml`: `SECRET_KEY` and `API_KEY_HASH_PEPPER` sourced from `.env` file

---

## [2.5.0] — 2025-08-01 — Phase 5: Enterprise Feature Development

### Added
**Backend — 9 new route modules:**
- `routes/users.py` — profile, forgot/reset password, account deletion, session management
- `routes/org_mgmt.py` — member invite/remove, role management, branding, feature flags
- `routes/return_mgmt.py` — return notes/timeline, document upload, delete, bulk import
- `routes/customers.py` — full CRUD, search, analytics, blacklist, CSV export
- `routes/notifications.py` — list, mark-read, mark-all-read, unread count
- `routes/reports.py` — summary/fraud/carbon/customer reports in JSON and CSV
- `routes/admin.py` — health, user management, audit logs, system settings, DB/ML stats
- `routes/workflows.py` — CRUD for workflow rules, SLA list and breach checking
- `routes/ai_ux.py` — prediction history, explainability, manual override, feedback, performance

**Backend — new services:**
- `services/workflow_service.py` — rule engine (AND conditions, first-match, SLA auto-creation)

**Backend — 8 new DB models:**
`PasswordResetToken`, `ReturnNote`, `ReturnDocument`, `WorkflowRule`, `FeatureFlag`,
`CustomerBlacklist`, `SystemSetting`, `SLATracking`

**Backend — 1 Alembic migration:**
`c7f91a3d2e55` — adds all 8 new tables plus `is_blacklisted` and `notes` columns on `customers`

**Backend — ~50 new store functions** across all new models

**Frontend — 5 new pages:**
`Profile.jsx`, `AdminPanel.jsx`, `Workflows.jsx`, `Reports.jsx`, `AIPlatform.jsx`

**Frontend — API client extended** with ~50 new API methods

**App.jsx** — 5 new routes; **Sidebar.jsx** — 3 new navigation sections

### Changed
- `returns.py` — now calls `apply_workflow_rules()` after every scored return
- `api.js` — extended with Phase 5 endpoints

---

## [2.0.0] — 2025-08-01 — Phase 4: AI & ML Enhancement

### Fixed (Bugs — previously mislabelled as "AI")
- **`top_cost_driver` was a hardcoded if/else guess**, not derived from the model —
  replaced with real XGBoost `feature_importances_` ranking
- **`get_model_stats()` hardcoded R² and RMSE literals** — now reads live from
  `model_metadata.json`
- **Carbon footprint had dead `courier == "FedEx"` branch** — FedEx was never in the
  courier vocabulary; replaced with accurate per-known-courier emission factors
- **Resale estimation ignored `category`** — a ₹50K laptop and ₹50K chair received
  identical depreciation; added category-based multipliers

### Added
- `ml/model_registry.py` — versioned artifact management with atomic writes and rollback
- `tests/test_ml_preprocessor.py` — 10 tests, all passing
- `tests/test_model_registry.py` — 8 tests, all passing
- `ML_PIPELINE.md` — full pipeline documentation with honest ML-vs-rule-based table
- `ML_EVALUATION_AUDIT.md` — model evaluation audit flagging missing cross-validation
- `db/models.py: PredictionOutcome` — label capture for future ML training
- `ml/train_fraud_model.py` — training scaffold (refuses to run until 200+ labels exist)
- Migration `8a3f21c9de44` — adds `prediction_outcomes` table

### Changed
- `ml/predict.py` — feature importances now exposed via `feature_importances_` property
- `ml/ml_service.py` — resale now uses category; carbon uses correct courier factors;
  explainability uses real model importances; model stats read from metadata file

---

## [1.3.0] — 2025-08-01 — Phase 3: Code Quality & Architecture

### Fixed
- `auth.py: register()` — was missing fields that `login()` and `/me` returned (DRY fix + real bug)
- Dead code removed: 5 unused imports, entire `middleware/` directory

### Added
- `_get_owned_return_or_404()` helper — eliminates duplicated ownership check
- `_user_summary()` helper — single source of truth for user response shape
- `_score_and_store()` split into 4 named steps for readability

### Changed
- `EmailStr` validation wired — email-validator added to requirements.txt
- `Register.jsx` — fixed to use `useAuth().register()` (was calling undefined function)
- `Dockerfile` — `CMD` fixed from invalid shell form to correct JSON array form

---

## [1.2.0] — 2025-08-01 — Phase 2: Core Bug Fixes

### Fixed
- **Critical: `sqlite3.OperationalError: no such table`** — backend booted before Alembic
  migrations ran; fixed boot order in `docker-compose.yml` health checks
- **Auth route duplicated user-summary logic** — fixed across login/register/me endpoints
- Rate limiting was in-memory only — documented; Redis rate limiting added in Phase 6

---

## [1.0.0] — 2025-08-01 — Phase 1: Initial Audit

### Discovered
- 5 components labelled as "AI models" — only 1 is a real ML model (cost prediction)
- `top_cost_driver` explainability was fake (hardcoded)
- Model stats were hardcoded literals
- No dataset in repo — retraining blocked
- Migration-before-boot race condition
- Dead FedEx courier branch in carbon footprint
