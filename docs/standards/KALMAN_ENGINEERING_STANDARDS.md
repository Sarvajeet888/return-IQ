# Kalman Engineering Standards

**Applies to every Kalman Consultancy Services product**
Version 1.0 · August 2026 · Classification: Internal

These standards were derived from building ReturnIQ Enterprise through ten
phases. Several exist because something broke first — those are marked, because
a standard with a story attached gets followed.

---

## 1. Product Portfolio Standard

Every Kalman product uses the same skeleton. A developer moving between
Kalman Semiconductor and Kalman Space should find the same layout.

```
<product-name>/
├── backend/            or the equivalent primary codebase
├── frontend/           if applicable
├── infra/
│   ├── docker/
│   ├── nginx/
│   ├── monitoring/
│   ├── logging/
│   ├── backups/
│   ├── scripts/
│   ├── terraform/
│   └── deployment/
├── qa/
│   ├── strategy/
│   ├── reports/
│   └── evidence/
├── docs/
│   ├── product/        What it is, for whom, limitations
│   ├── architecture/   Diagrams and design decisions
│   ├── api/            Endpoint reference
│   ├── ai/             Model cards (if ML is used)
│   ├── business/       Pricing, ROI, SoW templates
│   ├── client/         Admin, user, troubleshooting guides
│   ├── developer/      Onboarding, standards, contribution
│   ├── operations/     Install, deploy, runbooks
│   ├── marketing/      Website copy, sales material
│   ├── standards/      Security audits
│   ├── training/
│   ├── release/        Changelog, known issues, rollback
│   ├── legal/          Privacy, ToS, cookies
│   └── compliance/     DPDP, licences, accessibility
├── .github/workflows/
├── README.md
├── LICENSE
└── .env.example
```

### Minimum viable documentation

No Kalman product ships externally without:

| Document | Why |
|---|---|
| Product overview with an explicit limitations section | Buyers find limits anyway; better from us |
| Architecture with design-decision rationale | Enterprise buyers ask first |
| API reference | Integration is the whole value for B2B |
| Model card (if ML) | Honest AI is a Kalman differentiator |
| Privacy policy + Terms of Service | Legal requirement |
| Known issues register | Nothing ships without known issues |
| Installation and deployment guides | Support cost reduction |

### Product maturity levels

| Level | Meaning | Requirements |
|---|---|---|
| **Prototype** | Internal only | Runs; README exists |
| **Alpha** | Friendly testers | Tests exist; core docs written |
| **Beta** | Pilot customers | Security audit; legal docs; ≥70% coverage; known issues published |
| **GA** | General sale | ≥85% coverage; load tested; SLAs; support process; accessibility reviewed |

**ReturnIQ Enterprise is currently Beta**, held there by: no frontend tests,
no executed load test, SMTP not wired, PII unencrypted, and legal review pending.

---

## 2. Architecture Standards

- **Stateless application tier.** All state in a database or cache. This is what
  makes horizontal scaling possible.
- **Multi-tenant from day one** for B2B products. Retrofitting tenant isolation
  is far harder than building it in.
- **Every tenant-scoped table has `org_id`.** Every query filters by it.
- **Return 404, not 403,** for another tenant's resource. 403 confirms existence.
- **Layer separation:** routes are thin (validate, delegate, shape). Business
  logic in services. Database access in one store layer.
- **Document the reasoning, not just the result.** A decision table explaining
  *why* is more useful than a diagram of *what*.

### Liveness and readiness must differ

```
/health/live   → is the process alive? Does NOT check dependencies.
/health/ready  → can this instance serve traffic? Checks DB and critical deps.
```

> **Why:** if liveness checks the database, a DB outage triggers a container
> restart loop. Restarting doesn't fix a dead database, and the churn makes
> recovery harder.

### Observability degrades, never crashes

Caching, metrics, and logging failures must be caught and swallowed. If Redis
dies the app gets slower — it does not go down.

---

## 3. Security Standards

Non-negotiable for every Kalman product:

| Control | Standard |
|---|---|
| Password hashing | bcrypt, cost ≥ 12 |
| JWT verification | Explicit algorithm allowlist — never library defaults |
| API keys | Store the HMAC hash with a pepper; compare with `compare_digest()` |
| Tokens in browser | Memory only. **Never localStorage or sessionStorage** |
| Refresh tokens | httpOnly + Secure + SameSite cookie; rotate on use; detect replay |
| File uploads | Validate MIME by magic bytes, not the client-supplied header |
| Secrets | Environment variables. Never in git, never in image layers |
| Containers | Non-root user, resource limits, no privileged mode |
| Transport | TLS 1.2+ with HSTS |
| Headers | CSP, X-Frame-Options DENY, X-Content-Type-Options, Referrer-Policy |
| Audit | Every significant action logged and not user-deletable |
| Errors | Never leak stack traces, file paths, or SQL |
| Enumeration | Auth responses must not reveal whether an account exists |

### Security testing is a release gate

Every product ships with executable penetration tests covering SQL injection,
XSS, JWT tampering, IDOR/cross-tenant access, privilege escalation, and password
policy. **A failure in that suite blocks the build.** Not a ticket — a blocker.

Bandit (or the language equivalent) must report zero high or medium findings.

---

## 4. Documentation Standards

- **Explain why, not what.** The code already says what it does.
- **Every product doc has a limitations section.** If it doesn't, it isn't
  finished.
- **Never overstate capability.** If it's rules, call it rules. This is the
  single most important Kalman documentation rule.
- **Date and version every document.**
- **Classify every document:** Public / Confidential / Internal.
- **Record design decisions with trade-offs**, in a table: decision, rationale,
  trade-off accepted.

### The AI honesty standard

Any Kalman product using ML must publish a model card and an AI transparency
statement covering:
- Which components are trained models and which are rules
- What the model was trained on and what it was not validated for
- Known limitations and failure modes
- Whether explainability is real attribution (SHAP) or a heuristic
- How humans stay in control

> **Why this is a standard:** ReturnIQ was described as having "5 AI models". It
> had one, plus four rule engines. Nobody lied — it drifted, then got repeated.
> The correction is now a documented product asset, and it's a competitive
> advantage in sales.

---

## 5. Testing Standards

| Gate | Threshold |
|---|---|
| All tests pass | 100% |
| Security suite | 100% — no exceptions, blocks the build |
| Lint correctness codes | Zero |
| Static security analysis | Zero high/medium |
| Coverage — Beta | ≥ 70% |
| Coverage — GA | ≥ 85% backend, ≥ 80% frontend |

- **Assert behaviour, not implementation.**
- **Name tests after what they protect**, not the function they call.
- **Failure messages state the consequence**, not just the mismatch.
- **Found a bug? Write the failing test first.**
- **Every tenant-scoped endpoint gets a cross-tenant access test.**

### Test environment configuration goes at import time

> **Why:** in ReturnIQ, conftest set env vars in a fixture. Pytest imports test
> modules during collection — before fixtures run — and app modules read
> settings at module level. The overrides silently stopped applying and 57 tests
> failed with HTTP 429.

---

## 6. Database Standards

- **A migration that adds a column MUST update the ORM model in the same commit.**

> **Why:** ReturnIQ's Phase 5 migration added `is_blacklisted` to `customers`
> without updating the model. The store layer filters updates with `hasattr()`,
> so writes were silently dropped. The endpoint returned 200. Nothing happened.
> It went unnoticed for two phases.

- Write both `upgrade()` and `downgrade()`. Test the round trip.
- Read generated migrations — autogenerate misses things.
- Soft delete by default; retain the audit trail. Add a scheduled purge for
  retention compliance.
- Index for the queries you actually run, not speculatively.

---

## 7. API Standards

- **Version in the path** (`/api/v1/`). Breaking changes get `/api/v2/` — they
  never modify v1.
- **Consistent error shape.** Every error has a `detail` field.
- **Correct status codes.** 409 for conflicts, 404 for not-found *and* for
  another tenant's resource, 422 for validation, 429 for rate limits.
- **Pagination must be bounded.** An unbounded `page_size` is a DoS vector.
- **Never register a path twice.**

> **Why:** in ReturnIQ, `misc.py` and `customers.py` both registered
> `/api/v1/customers`. FastAPI matched the one included first, and the entire
> Phase 5 customers router was unreachable dead code for two phases — with no
> startup error. A test now asserts no duplicate route paths.

- **Publish an OpenAPI spec** and check it for duplicate operation IDs — they
  break generated client SDKs.
- **Surface degraded results.** If input falls outside what the system handles
  well, say so in the response rather than returning a confident-looking answer.

---

## 8. Release Standards

**Semantic versioning.** MAJOR = breaking, MINOR = feature, PATCH = fix.

**Branches:** `main` (production, protected) ← `develop` (staging) ← `feature/*`

**Every production deploy:**
1. Database backup **before** anything else
2. Build, migrate, health check, smoke test
3. Tag the release
4. Rollback plan documented and tested

**Every release ships:** changelog · release notes · known issues · rollback plan

---

## 9. Naming Conventions

| Thing | Convention |
|---|---|
| Divisions | `Kalman <Area>` — Kalman Enterprise, Kalman AI |
| Products | Standalone name, no Kalman prefix — ReturnIQ, Gaze Glide |
| Product tiers | ReturnIQ Enterprise, ReturnIQ Starter |
| Repositories | `kebab-case` — `returniq-enterprise` |
| API paths | `kebab-case`, plural nouns — `/api/v1/return-requests` |
| Database tables | plural `snake_case` |
| Environment variables | `UPPER_SNAKE_CASE` |
| Docker images | `ghcr.io/kalman/<product>-<component>` |

---

## 10. Code Review Checklist

- [ ] Tests added for new behaviour, and they fail without the change
- [ ] Cross-tenant access test added for any new tenant-scoped endpoint
- [ ] Migration and ORM model updated together
- [ ] No duplicate route paths introduced
- [ ] No secrets in the diff
- [ ] Errors don't leak internals
- [ ] Docs updated if behaviour changed
- [ ] No capability claimed that isn't implemented
- [ ] Security suite passes
- [ ] Coverage not reduced

---

## 11. Applying These to the Next Product

| Product | Division | Standards priority |
|---|---|---|
| Portfolio Builder | Kalman Cloud | Multi-tenant, security, API |
| Gaze Glide | Kalman AI | **Model card critical** — accessibility software making inferences about disabled users demands the highest transparency bar |
| Multi-Agent Simulation | Kalman AI | Model card, reproducibility, versioned scenarios |
| Chip Design Assistant | Kalman Semiconductor | Model card, IP handling — customer RTL is highly confidential |
| AI RTL Bug Finder | Kalman Semiconductor | Model card, false-positive rate disclosure |
| Space Software | Kalman Space | Correctness testing, versioning — errors are unrecoverable |
| Financial Infrastructure | Kalman Finance | **Highest security bar.** Regulatory compliance, audit, encryption |

**Do not start a new product until the existing one reaches at least Beta.** The
Company Profile lists nine products across six divisions with two directors.
That is a genuine execution risk, and the Profile itself already identifies the
right answer: *"building each product to a high-quality, demonstrable state,
gaining real users, and generating revenue — using the success of each product
to fund and inform the next."*

ReturnIQ is the one closest to that bar. Finishing it is worth more than
starting a tenth.
