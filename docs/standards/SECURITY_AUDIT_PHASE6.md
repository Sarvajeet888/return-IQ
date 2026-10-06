# Phase 6 — Security Audit: Deliverables

Covers the remaining named deliverables from the Phase 6 roadmap that
weren't produced as documents in the earlier pass: permission matrix,
OWASP Top 10 compliance matrix + risk register, centralized audit
strategy, and the deployment readiness checklist. Code-level fixes
referenced here were applied directly to the codebase and verified live
(33/33 backend tests passing, plus targeted exploit-attempt scripts run
against a live TestClient instance — not just read through).

---

## 6.2 — Permission Matrix

Roles: `super_admin` (platform-wide), `org_admin`, `analyst`, and the
implicit "any authenticated member" tier. Built directly from every
`require_role(...)` / `get_current_org` / `get_current_user` dependency in
the codebase, not from memory.

| Resource / Action | Any member | analyst | org_admin | super_admin |
|---|---|---|---|---|
| View own profile, sessions, activity | ✅ | ✅ | ✅ | ✅ |
| Create/view/list returns, notes, documents | ✅ | ✅ | ✅ | ✅ |
| Delete a return | ❌ | ❌ | ✅ | ✅ |
| Bulk import returns | ✅ | ✅ | ✅ | ✅ |
| Override an AI prediction | ❌ | ✅ | ✅ | ✅ |
| View/create customers | ✅ | ✅ | ✅ | ✅ |
| Delete / blacklist a customer | ❌ | ❌ | ✅ | ✅ |
| Update org settings, branding, feature flags | ❌ | ❌ | ✅ | ✅ |
| Invite / change role / remove org members | ❌ | ❌ | ✅ | ✅ |
| Create / delete org API keys | ❌ | ❌ | ✅ | ✅ |
| View org audit log | ❌ | ❌ | ✅ | ✅ |
| Create/edit/delete workflow rules | ❌ | ❌ | ✅ | ✅ |
| View reports (summary/fraud/carbon/customers) | ✅ | ✅ | ✅ | ✅ |
| Platform health dashboard | ❌ | ❌ | ✅ | ✅ |
| List **all** orgs / **all** users platform-wide | ❌ | ❌ | ❌ | ✅ |
| Change any user's account status | ❌ | ❌ | ❌ | ✅ |
| Platform system settings | ❌ | ❌ | ❌ | ✅ |
| Platform-wide audit log | ❌ | ❌ | ❌ | ✅ |
| Database statistics | ❌ | ❌ | ❌ | ✅ |

Notes:
- Every row that isn't a `super_admin`-only platform action is additionally
  **org-scoped** — verified during the audit that every object lookup
  (`{return_id}`, `{customer_id}`, `{doc_id}`, `{member_id}`) checks
  `org_id` ownership before returning data, not just role.
- `analyst` is the one role with a genuinely narrow grant (prediction
  override) beyond the "any member" baseline — everything else is a binary
  member vs. org_admin split. If you need finer-grained roles later
  (e.g. read-only vs. read-write analyst), this table is the place to
  extend.

---

## 6.8 — OWASP Top 10 (2021) Compliance Matrix

| # | Category | Status | Evidence |
|---|---|---|---|
| A01 | Broken Access Control | 🟢 Good | Live-tested IDOR (cross-org return access → 404), vertical privilege escalation (member hitting `/admin/orgs` → 403) — both blocked. Every nested resource verified org-scoped. |
| A02 | Cryptographic Failures | 🟢 Good | bcrypt cost 12, JWT HS256 with explicit algorithm allowlist, HMAC-SHA256 API key hashing with constant-time comparison. **Residual gap:** customer PII (email/phone) stored in plaintext DB columns — acceptable at this scale but worth column-level encryption before handling large-scale real customer data. |
| A03 | Injection | 🟢 Good | Zero raw SQL in the codebase — everything through SQLAlchemy's query builder. Live-tested a SQL-injection-shaped login payload; blocked upstream by Pydantic's `EmailStr` validation before it could reach the DB layer. |
| A04 | Insecure Design | 🟡 Partial | Refresh-token rotation + replay detection is a strong design choice. **Fixed this pass:** the forgot-password flow was a design-level account-takeover vector (see A07). |
| A05 | Security Misconfiguration | 🟢 Fixed this pass | Added security headers (was completely absent). Closed the `docker-compose` weak-secret-placeholder bypass. Backend no longer directly internet-exposed (was previously bypassable around nginx). Non-root container user. |
| A06 | Vulnerable Components | 🟢 Fixed this pass | `pip-audit` found 23 advisories across 6 packages; patched the security-critical one (`python-jose`, used for JWT, 3.3.0→3.4.0) plus 2 others. `starlette`/`pytest` advisories flagged but intentionally not force-bumped without a compatibility pass. |
| A07 | Identification & Auth Failures | 🟢 Fixed this pass | **Critical fix:** forgot-password endpoint unconditionally leaked the raw reset token — full account takeover with no inbox access needed, live in every environment since SMTP was never wired. Now gated behind `DEMO_MODE AND non-production`, verified live. JWT tampering and `alg=none` attacks both tested live and correctly rejected with 401. |
| A08 | Software & Data Integrity Failures | 🟡 Partial | No CI/CD pipeline signing or dependency pinning verification beyond `requirements.txt` exact pins (good). No SBOM generation. |
| A09 | Logging & Monitoring Failures | 🟡 Partial | Per-action audit log exists (login, logout, note/document actions, settings changes) and is queryable. No centralized aggregation/alerting layer — see 6.9 below. |
| A10 | SSRF | 🟢 No live vector, flagged for the future | `webhook_url` is accepted and stored in org settings but nothing in the codebase currently dispatches to it — the feature is a stub. **Not exploitable today**, but whoever implements webhook delivery must validate the URL (reject private/internal IP ranges, `localhost`, cloud metadata IPs like `169.254.169.254`) before ever fetching it, or this becomes a live SSRF vector immediately. |

### Risk Register (open items, ranked)

| Risk | Likelihood | Impact | Priority |
|---|---|---|---|
| Webhook delivery implemented later without SSRF-safe URL validation | Medium (when built) | High | Address at implementation time, not now |
| File upload MIME/content check bypassed via a crafted polyglot file | Low | Medium | Monitor; current magic-byte check handles the common case |
| PII stored unencrypted at rest | Low (needs DB compromise) | High (regulatory, per DPDP Act 2023) | Plan column-level encryption before scaling to real customer data |
| No centralized security alerting (failed-login spikes, mass exports) | Medium | Medium | Build per 6.9 plan below |
| `starlette`/`pytest` advisories unpatched | Low | Low-Medium | Bump after a dedicated compatibility test pass |

---

## 6.9 — Centralized Audit Strategy

**Current state:** `store.add_audit_log()` is already called consistently
across auth events, settings changes, note/document actions, exports, and
member management — this is solid per-action coverage, not a gap.

**What's missing is aggregation, not logging itself:**
1. No dashboard surfaces failed-login spikes, unusual export volume, or
   after-hours admin actions — an operator has to manually query the audit
   log table to notice anything.
2. No alerting hook (email/Slack/PagerDuty) tied to security-relevant
   events (repeated lockouts, a new org_admin being granted, bulk customer
   exports).
3. No log retention/rotation policy defined for the audit table itself.

**Recommended next step (not built this pass — needs a decision on where
alerts should go):** a lightweight scheduled job that queries
`audit_logs` for the last N minutes, flags patterns (>5 failed logins for
one email, >3 role changes in an hour, any `export_customers` action),
and pushes to whatever channel you choose (email via the SMTP integration
that also needs wiring for password reset, or a Slack webhook).

---

## 6.13 — Performance Baseline

Measured live against the full return-scoring path (`POST
/api/v1/returns`, includes ML inference + DB writes), 50 sequential
requests via `TestClient` against SQLite:

```
p50 = 26.4ms   p95 = 68.7ms   max = 110.4ms
```

**Honest caveat:** this is a sequential, single-connection baseline
against SQLite — useful as a sanity check that nothing is pathologically
slow, but **not** a substitute for a real concurrent load test against
Postgres in the actual deployment environment (needs a running server +
a tool like `locust` or `k6`, which requires the deployed target, not
static analysis). `DB_POOL_SIZE=20` with `--workers 2` gives headroom for
moderate concurrency; validate against your Postgres `max_connections`
before scaling workers further.

---

## 6.15 — Deployment Readiness Checklist

| Item | Status |
|---|---|
| Security review complete | 🟡 Substantive pass done (6.1-6.12 covered); load testing and formal pentest still need a live deployed target |
| `SECRET_KEY` / `API_KEY_HASH_PEPPER` set to real values, not placeholders | ✅ Enforced at startup — verified live that the compose-file placeholder bypass is closed |
| `DEMO_MODE=false` in production | ⚠️ Must be set explicitly — defaults to `true` |
| `ENVIRONMENT=production` set | ⚠️ Must be set explicitly — defaults to `development` |
| `COOKIE_SECURE=true` if served over HTTPS | ⚠️ Must be set explicitly |
| `CORS_ORIGINS` set to real frontend domain(s) | ⚠️ Defaults to localhost only — must override |
| HTTPS enforced | ❌ Not configured in this repo — needs a reverse proxy/LB with TLS termination in front of nginx |
| Legal documents present (Privacy Policy, ToS, etc.) | ❌ Still not present anywhere in the repo — flagged since Phase 1, unresolved |
| Backend not directly internet-exposed | ✅ Fixed this pass |
| Non-root container | ✅ Fixed this pass |
| Dependency CVEs addressed | 🟡 Critical one (`python-jose`) fixed; a few low-priority ones remain |
| Monitoring/alerting configured | ❌ Not built (see 6.9) |
| Backups configured | ❌ Not configured — `pgdata` is a local Docker volume only, no automated backup/restore tested |
| Disaster recovery documented | ❌ Not written |
| SMTP wired (blocks password reset from working at all) | ❌ Still not implemented — flagged since Phase 1 |
| Fraud/damage ML models | ❌ Never completed (see Phase 4/5 gap flagged earlier) |
| All backend tests passing | ✅ 33/33 |
| CI/CD pipeline | ❌ None exists in this repo |

**Bottom line:** the app is meaningfully more secure than it was at the
start of this phase, and the fixes made were real and verified — but
"deployment ready" also depends on several non-security items (SMTP,
legal docs, backups, CI/CD, monitoring) that are still open. Security
hardening alone doesn't make something launch-ready.
