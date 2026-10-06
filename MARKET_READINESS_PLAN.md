# Market Readiness Plan — ReturnIQ Enterprise

**Prepared for Om Pilaji & Sarvajeet Bajikar, Directors**
**4 August 2026 · Version 0.9.0-rc1**

---

## Status After This Build

| | |
|---|---|
| Automated tests | **250 passing** (up from 223) |
| Backend coverage | **78%** |
| Security tests | 36/36 |
| Ruff correctness | Zero errors |
| Bandit | 0 high, 0 medium |

**Four engineering blockers closed** in this build. Four remain, and two of
those aren't engineering work.

---

## ✅ Week 2 — Done (this build)

### 1. SMTP wired — KI-001 closed

`app/services/email_service.py`

- Password reset and team invitations now actually send email
- Runs as a FastAPI `BackgroundTask` — `smtplib` is blocking, and calling it
  inline would stall the event loop for the whole SMTP handshake
- Never raises. A dead SMTP server returns `False`; it does not turn a
  password-reset request into a 500
- Logs an **ERROR** if SMTP is unconfigured while `ENVIRONMENT=production`,
  because password reset is silently broken otherwise
- Plain HTML templates with no remote images — mail clients block those by
  default, and a broken layout in a security email erodes trust

**To activate:** set `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`,
`SMTP_FROM` in `.env`. AWS SES in `ap-south-1` is the cheapest option for India.

### 2. Consent capture — KI-003 closed

- `accepted_terms` is **required** at registration and must be `true`. Not a
  default, not optional
- A `consent_records` row is written with policy version, timestamp, IP, and
  user agent. The DPDP Act requires you to **demonstrate** consent, not assert
  it — a boolean on the user row can't do that because it's overwritten when
  policies change
- **Append-only.** Withdrawal writes a new row with `granted=false`; the
  original grant is never mutated
- Frontend checkbox added, unticked by default, with the submit button disabled
  until it's ticked — a pre-ticked box is not valid consent under the Act

### 3. PII encryption at rest — KI-002 closed

`app/core/encryption.py`

- Customer `name`, `email`, `phone` are Fernet-encrypted (AES-128-CBC +
  HMAC-SHA256) via a SQLAlchemy `TypeDecorator`, so application code is
  unchanged — `customer.email` is still a string
- A test reads the **raw database column** and asserts the plaintext isn't
  there. That's the test that actually proves this is closed
- Key derives from `SECRET_KEY` via HKDF, so there's no second secret to
  distribute

**The trade-off, stated plainly:** encrypted columns can't be searched with SQL
`LIKE`, because Fernet's random IV means identical plaintext produces different
ciphertext every time. `search_customers()` now decrypts and filters in Python —
O(n) per search. Fine at a few thousand customers per org; past ~50,000 it needs
a blind index. Logged in the architecture debt register rather than hidden.

**Migrating existing data:**
```bash
cd backend
alembic upgrade head
python3 scripts/encrypt_existing_pii.py --dry-run   # inspect
python3 scripts/encrypt_existing_pii.py             # apply
```
Tested end to end: 3 plaintext rows → encrypted → plaintext confirmed gone →
re-run skipped all 3 (idempotent).

### 4. S3 file storage — KI-011 closed

`app/services/storage_service.py`

**This one was worse than documented.** The upload endpoint recorded a
`storage_key` in the database but **never wrote the bytes anywhere at all.**
Every uploaded document was a database row pointing at nothing.

- S3 when `AWS_S3_BUCKET` is set, local disk otherwise — same interface either way
- Server-side encryption (`AES256`) on every S3 object
- Presigned download URLs with 15-minute expiry; the bucket stays private
- Keys are `uploads/{org_id}/{return_id}/{uuid}_{name}` — the org prefix lets a
  bucket policy enforce tenant isolation at the storage layer too
- Path-traversal tested: `../../../etc/passwd` can't escape its directory

---

## 🔨 Week 1 — Do These Yourself, Now

### 1. Fix the Company Profile PDF — today

It claims **route optimization, vendor management, customer return portal, and
repair workflow.** None exist in the codebase. This costs nothing to fix and is
the most damaging thing if a technical buyer or investor catches it.

Corrected wording is already written in `docs/product/PRODUCT_CLAIMS_AUDIT.md`.

### 2. Deploy the demo

₹500–800/month on Hetzner or DigitalOcean. A live URL beats any zip file.

```bash
bash infra/scripts/server_setup.sh
bash infra/scripts/setup_ssl.sh yourdomain.com you@email.com
docker compose -f docker-compose.prod.yml up -d --build
```

Full steps: `infra/deployment/DEPLOYMENT_RUNBOOK.md`

### 3. Push incorporation forward

You're stuck at Phase 2 — DSC issuance. Sarvajeet needs to download his
e-Aadhaar and e-PAN, then both of you apply on eMudhra. **This has a 2–3 week
clock you cannot compress, and nothing commercial can happen until the COI
exists.** Start it and do everything else in parallel.

---

## 🎯 Week 3 — Get One Real User

The part people skip, and the most important.

**Find one merchant.** A friend's family business, a Hyderabad D2C brand,
anyone selling on Instagram who handles returns by hand. Free for 3 months in
exchange for honest feedback and a case study.

**Run shadow mode for the first two weeks.** ReturnIQ scores every return,
humans still decide, you compare. This does two things:

- Zero risk to them, so it's an easy yes
- **Produces your first real accuracy number** — which you do not have and
  cannot get any other way

The reported R² of 0.9993 has never been validated. One pilot in shadow mode
tells you more about whether this model works than any amount of further
engineering.

Plan and templates: `phase11/beta/`

---

## 📋 Week 4+ — After the Above

| Task | Cost / Effort |
|---|---|
| Legal review of ToS and Privacy Policy | ₹15–30k, a CS or lawyer in Hyderabad |
| Frontend test suite | 2–3 days |
| Load test on 4 vCPU / PostgreSQL staging | 4 hours + a server |
| WCAG accessibility remediation | 6–10 hours |

---

## Remaining Blockers

| # | Blocker | Type | Effort |
|---|---|---|---|
| 1 | Company not incorporated | Legal | 2–3 weeks (in progress) |
| 2 | ToS/Privacy not legally reviewed | Legal | ₹15–30k |
| 3 | Company Profile claims 4 features that don't exist | Directors | **1 hour** |
| 4 | Frontend has zero tests | Engineering | 2–3 days |
| 5 | No load test on real hardware | Engineering | 4 hours + server |

Blockers 1–3 aren't code. **Blocker 3 is one hour of editing and it's the one
I'd do first.**

---

## What I'd Still Push Back On

**Don't build more features.** 93 endpoints, 250 tests, zero users. The
bottleneck isn't capability.

**Don't start the other eight Kalman products.** Your own Company Profile names
the right strategy: finish one, get users, use that to fund the next. ReturnIQ
is closest. Finishing it beats starting a tenth.

**Don't wait for perfect.** No frontend tests and no load test don't matter for
one pilot user processing 200 returns a month. They matter at 20 customers.

---

## The Honest Summary

You're **two external dependencies and about one hour of PDF editing** away from
being able to sell this.

The engineering is in better shape than most funded startups' first product:
250 tests, a security audit, executable penetration tests, full legal
documentation, infrastructure as code, and an honest AI transparency statement
that most competitors couldn't write.

What you're missing isn't engineering. It's a company that legally exists and
one person using the thing.
