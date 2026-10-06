# System Architecture — ReturnIQ Enterprise

**Version 3.0.0 · August 2026 · Classification: Confidential**

---

## 1. High-Level Architecture

```
                          Internet
                             │
                        HTTPS (443)
                             │
                 ┌───────────▼───────────┐
                 │        Nginx          │  TLS termination
                 │   reverse proxy       │  Security headers
                 │                       │  Rate limiting (5r/m auth, 100r/m general)
                 │                       │  Static asset caching, gzip
                 └───────┬───────┬───────┘
                         │       │
              /api/*     │       │   /* (SPA)
                         │       │
          ┌──────────────▼──┐  ┌─▼──────────────┐
          │  FastAPI        │  │  React SPA     │
          │  backend        │  │  (static)      │
          │  4 workers      │  └────────────────┘
          └──┬───────┬───┬──┘
             │       │   │
    ┌────────▼──┐ ┌──▼───▼──┐ ┌──────────────┐
    │PostgreSQL │ │  Redis  │ │ ML artifacts │
    │    16     │ │    7    │ │ (read-only   │
    │           │ │         │ │  volume)     │
    │ 21 tables │ │ rate    │ │ model.joblib │
    │ 4 migr.   │ │ limits  │ │ preprocessor │
    └───────────┘ │ cache   │ └──────────────┘
                  └─────────┘
```

**Why this shape:** the backend is stateless — all state lives in Postgres and
Redis. That is what makes horizontal scaling possible without sticky sessions.
JWTs are stateless by design for the same reason.

---

## 2. Request Flow — Scoring a Return

This is the critical path. Everything else in the product is supporting
infrastructure.

```
POST /api/v1/returns
   │
   ├─ 1. Nginx: TLS, rate limit check, X-Request-ID assigned
   │
   ├─ 2. RequestIdMiddleware: correlation ID into log context
   │
   ├─ 3. SecurityHeadersMiddleware: HSTS, CSP, X-Frame-Options
   │
   ├─ 4. Auth dependency: JWT verified (explicit algorithm allowlist)
   │       └─ org_id extracted → every subsequent query is org-scoped
   │
   ├─ 5. Pydantic: schema validation (pincode format, enums, ranges)
   │
   ├─ 6. build_feature_dict()
   │       ├─ normalise courier / category / reason to model vocabulary
   │       ├─ derive chargeable_weight = max(actual, volumetric)
   │       ├─ derive pincode tiers and distance estimate
   │       └─ compute customer_return_rate, merchant_return_rate
   │
   ├─ 7. score_return()
   │       ├─ preprocessor.transform()  → one-hot + scaling
   │       ├─ model.predict()           → cost prediction (real ML)
   │       ├─ fraud rules               → 0–100 score  (NOT ML)
   │       ├─ damage rules              → probability  (NOT ML)
   │       ├─ resale formula            → estimate     (NOT ML)
   │       ├─ carbon formula            → kg CO₂e      (NOT ML)
   │       └─ _decide_routing()         → deterministic decision tree
   │
   ├─ 8. Persist: return_requests row + predictions row
   │
   ├─ 9. apply_workflow_rules()
   │       ├─ load active rules for org, priority ascending
   │       ├─ evaluate conditions (AND logic)
   │       ├─ first match wins → apply action, short-circuit
   │       └─ create SLA record (rule-specified or 48h default)
   │
   ├─ 10. check_unmapped_features() → data_quality_warnings if any
   │
   └─ 11. Response: return + prediction + rules applied + warnings
```

**Typical latency:** under 100ms. Inference itself is a few milliseconds; most
of the budget is database writes.

### Design decision: synchronous scoring

Scoring runs inline rather than on a queue. The reasoning: the user submitting
a return wants the decision immediately, and inference is fast enough that
queueing would add complexity and latency without benefit. If inference ever
exceeds ~500ms (a much larger model, or an external API call), this should move
to a background worker with a polling endpoint.

---

## 3. Data Model

21 tables. The core relationships:

```
orgs ─┬─< users ─────< refresh_tokens
      │              └< password_reset_tokens
      ├─< api_keys
      ├─< customers ──< customer_blacklist
      ├─< workflow_rules
      ├─< feature_flags
      ├─< notifications
      ├─< audit_logs
      └─< return_requests ─┬─< predictions ──< prediction_outcomes
                           ├─< return_notes
                           ├─< return_documents
                           └─── sla_tracking (1:1)
```

**Every tenant-scoped table carries `org_id`.** Isolation is enforced at the
query layer through the `get_current_org` dependency, and verified by 8
dedicated cross-tenant tests in `tests/security/` and
`tests/integration/test_org_management.py`.

### Migrations

| Revision | Adds |
|---|---|
| initial | Core: orgs, users, returns, predictions, customers, notifications, audit |
| `8a3f21c9de44` | `prediction_outcomes` — ML label capture |
| `c7f91a3d2e55` | Phase 5: 8 tables (notes, documents, workflow rules, flags, blacklist, settings, SLA, reset tokens) |
| `d9e2f4a7b831` | Phase 8: 10 composite performance indexes |

**Lesson recorded:** migration `c7f91a3d2e55` added `is_blacklisted` and `notes`
to `customers` but the SQLAlchemy model was not updated. Since
`store.update_customer()` filters with `hasattr()`, blacklisting silently did
nothing for two phases. Caught in Phase 9. **Any migration that adds a column
must also update the ORM model in the same commit** — this is now in the
developer standards.

---

## 4. Authentication & Authorization

### Two authentication paths

**JWT (interactive users)**
- Access token: 15-minute TTL, stored in browser memory only — never
  localStorage, which is readable by any injected script
- Refresh token: 7-day TTL, httpOnly + Secure + SameSite=Lax cookie, stored
  server-side as an HMAC-SHA256 hash
- Refresh rotates on every use; replay of a used token revokes the whole family
- Algorithm allowlist passed explicitly to prevent the `alg=none` attack

**API key (server-to-server)**
- Format `rl_live_...`, only the HMAC-SHA256 hash with a pepper is stored
- Compared with `hmac.compare_digest()` — constant time, no timing oracle
- Scoped to `/api/v1/ext/*`

### Role hierarchy

```
super_admin   → all orgs, system settings, global audit
    │
org_admin     → full control of own org: members, rules, branding, deletion
    │
analyst       → read all org data, override AI decisions, submit feedback
    │
viewer        → read-only
```

Enforced by the `require_role()` dependency. Verified by tests including a
mass-assignment attempt to self-promote via profile update.

---

## 5. ML Pipeline

```
Return data
     │
     ▼
build_feature_dict()  ── 15 features
     │                   4 categorical, 11 numeric
     ▼
preprocessor.joblib  ── OneHotEncoder + scaling
     │                  handle_unknown → all-zeros
     ▼
model.joblib         ── XGBoost regressor
     │
     ▼
predicted_cost_inr + feature_importances_
```

### The known weakness, stated plainly

`handle_unknown` produces an all-zeros row for any categorical value outside the
training vocabulary. The model still returns a confident-looking number, computed
with a feature effectively missing. Before Phase 9 this was silent.

**Mitigation:** `check_unmapped_features()` now runs on every request and returns
`data_quality_warnings` naming the unrecognised value and listing valid ones. The
prediction is still returned — rejecting it would break integrations using
alternative courier spellings — but the caller is told it is degraded.

### Model vocabulary

| Feature | Known values |
|---|---|
| courier | BlueDart, DTDC, Delhivery, Ekart, Shadowfax, Xpressbees |
| category | Beauty, Books, Electronics, Fashion, Home, Sports |
| payment_mode | COD, Prepaid |
| return_reason | Changed Mind, Damaged, Quality Issue, Wrong Item, Wrong Size |

A test asserts every value the mapping layer can emit exists in this vocabulary
— a typo like `XpressBees` vs `Xpressbees` would otherwise silently zero the
feature for every affected return.

---

## 6. Caching

Redis, with three deliberate properties:

**Org-scoped keys.** Every key is `org:{org_id}:...`. The `@cached` decorator
refuses to cache at all if it cannot find an org context — a caching bug must
never become a cross-tenant leak.

**Graceful degradation.** Every cache function catches exceptions and returns a
miss. Redis dying makes the app slower, not broken. Redis is deliberately
excluded from the readiness probe for the same reason.

**Invalidation by namespace.** Writes invalidate the org's whole namespace via
`SCAN` rather than surgically patching keys. Simpler and safe. `SCAN` not `KEYS`
— `KEYS` blocks Redis on large datasets.

---

## 7. Observability

| Layer | Implementation |
|---|---|
| Metrics | Prometheus at `/metrics` — HTTP latency, ML inference histogram, business counters |
| Logs | Structured JSON to stdout with correlation IDs; Loki + Promtail aggregation |
| Traces | Not implemented — correlation IDs provide request-level tracing |
| Alerts | 13 Prometheus rules: API down, error rate, slow inference, DB connections, disk, login-failure spikes |

### Liveness vs readiness — a deliberate difference

```
GET /health/live   → 200 if the process is running. Does NOT check the DB.
GET /health/ready  → 200 if DB and ML model are available; 503 otherwise.
```

Liveness deliberately ignores the database. If it didn't, a database outage
would trigger a container restart loop — restarting a container does not fix a
dead database, and the churn makes recovery harder. Readiness pulls the instance
out of the load balancer without killing it.

---

## 8. Scaling

**Stateless backend.** Scale horizontally by adding replicas. Requires:
- `USE_REDIS_RATE_LIMIT=true` — otherwise limits are per-instance and bypassable
- S3 for document storage (currently local disk — not shared across replicas)
- No sticky sessions needed; JWT is stateless

**Database is the first bottleneck.** Every scored return writes two rows. At
high volume, consider read replicas for reporting queries and partitioning
`return_requests` and `predictions` by month.

**Known scaling gap:** document uploads write to a local volume. Until S3
integration lands, running multiple backend replicas will scatter uploads across
containers. Single replica only, or mount shared storage.

---

## 9. Security Architecture

| Layer | Control |
|---|---|
| Transport | TLS 1.2/1.3, HSTS with preload |
| Headers | CSP, X-Frame-Options DENY, X-Content-Type-Options, Referrer-Policy |
| Rate limiting | Nginx (5r/m auth, 100r/m general) + application-level slowapi |
| Authentication | bcrypt cost 12, JWT with algorithm allowlist, rotating refresh tokens |
| Authorization | Role dependency + org scoping on every query |
| Input validation | Pydantic schemas; SQLAlchemy parameterised queries |
| File upload | MIME validated by magic bytes (`python-magic`), not the client header |
| Secrets | Environment variables, never in image layers or git |
| Container | Non-root user, no privileged mode, resource limits |
| Audit | Every significant action logged, 2-year retention, not user-deletable |

Verified by 36 executable penetration tests and Bandit static analysis (0 high,
0 medium across 4,969 lines).

---

## 10. Key Design Decisions

| Decision | Rationale | Trade-off accepted |
|---|---|---|
| Access token in memory, not localStorage | localStorage is readable by injected scripts | Token lost on tab close; refresh cookie restores the session |
| Synchronous ML scoring | User wants the decision now; inference is fast | Would need re-architecting if the model gets much slower |
| Rule engine short-circuits on first match | Predictable, debuggable; one return can't get contradictory actions | Cannot compose multiple rules on one return |
| Unknown categoricals warn rather than reject | Merchants use varied naming; hard rejection breaks integrations | Prediction is degraded, so the warning must be surfaced |
| Soft delete everywhere | Audit trail and future ML training data | Storage grows; needs a retention purge job |
| Liveness excludes DB check | Prevents restart loops during DB outages | Container stays up while unable to serve — readiness handles routing |
| Single-class equity ML labelling deferred | Won't fabricate synthetic labels to claim "AI fraud detection" | Fraud stays rule-based until real data exists |

---

## 11. Architecture Debt

Honest register of what should be fixed:

| Item | Impact | Priority |
|---|---|---|
| Documents on local disk | Blocks horizontal scaling; uploads lost on container replacement | 🔴 High |
| Customer PII unencrypted at rest | Fails enterprise security review; DPDP exposure | 🔴 High |
| No background job runner | SLA checks need an external cron; retention purge unimplemented | 🟠 Medium |
| `store.py` is a single 1,000-line module | Hard to navigate; should split by domain | 🟠 Medium |
| No read replica support | Reporting queries compete with the write path | 🟡 Low until volume grows |
| No distributed tracing | Correlation IDs suffice at current scale | 🟡 Low |
