# Release Notes — ReturnIQ Enterprise v3.0.0

**Release Date:** 1 August 2025
**Release Type:** Major (Phases 1–7 complete)
**Status:** Release Candidate — pending go-live sign-off

---

## What Is ReturnIQ Enterprise?

ReturnIQ Enterprise is an AI-assisted reverse logistics platform for Indian e-commerce
merchants and 3PLs. It scores every return request using a combination of machine
learning (cost prediction) and business-rule heuristics (fraud, damage), and recommends
a routing decision in under 100ms — accept, reject, manual review, or refund-and-keep.

This release (v3.0.0) represents the completion of a 7-phase development programme:

| Phase | Focus | Status |
|---|---|---|
| 1 | Codebase audit | ✅ Complete |
| 2 | Core bug fixes | ✅ Complete |
| 3 | Code quality & architecture | ✅ Complete |
| 4 | AI & ML enhancement | ✅ Complete |
| 5 | Enterprise features | ✅ Complete |
| 6 | Security hardening | ✅ Complete |
| 7 | Legal, compliance & documentation | ✅ Complete |

---

## What's New in v3.0.0 (Phase 7)

This release adds all legal, compliance, and operational documentation required before
production go-live:

- **Privacy Policy** — DPDP Act 2023 compliant, covering all 9 data categories collected
- **Terms of Service** — AI limitation disclaimers, liability caps, governing law (India)
- **Cookie Policy** — documents the single essential session cookie
- **AI Transparency Statement** — honest disclosure that 1 component is ML and 4 are
  rule-based; includes R² caveat, confidence score methodology, override instructions
- **Data Retention Policy** — retention periods for all data types, deletion procedures
- **DPDP Compliance Checklist** — self-assessment with 5 open action items before launch
- **License Audit** — all 24 dependencies verified; no GPL conflicts; psycopg2 LGPL
  use confirmed compliant
- **Accessibility Audit** — WCAG 2.1 AA gap analysis with prioritised remediation list
- **Full API Reference** — all 60+ endpoints with request/response examples
- **Installation, Deployment, User, Admin, and Troubleshooting guides**
- **Production Checklist** — go/no-go sign-off document
- **Rollback Plan** and **Known Issues** register

---

## Highlights from Earlier Phases

### Real Bug Fixes (not just features)
- Fake explainability (`top_cost_driver` was a hardcoded guess, not model-derived)
- Hardcoded model stats that would lie after any retraining
- Dead FedEx carbon footprint branch (FedEx was never a valid courier)
- Resale estimation that ignored item category entirely
- Boot-time race condition: app started before migrations ran
- JWT `alg=none` attack vector
- API key timing attack (now constant-time)
- Forgot-password token returned in API response in production

### AI Honesty
The platform's 5 "AI models" turned out to be 1 real ML model and 4 rule-based
calculations. This is documented transparently in `AI_TRANSPARENCY.md` and the in-app
AI Platform page rather than being silently misrepresented.

---

## Deployment Requirements

- Docker 24.0+ and Docker Compose 2.20+
- PostgreSQL 15+
- Redis 7+
- 4GB RAM minimum (8GB recommended)
- HTTPS/TLS termination required in production
- SMTP server required for password reset to function in production

See `docs/guides/INSTALLATION.md` and `docs/release/PRODUCTION_CHECKLIST.md`.

---

## Known Issues

See `docs/release/KNOWN_ISSUES.md` for the full list.

Top 3 for this release:
1. **SMTP not wired** — password reset works in demo mode only
2. **PII stored in plaintext** — customer email/phone not encrypted at rest
3. **Accessibility not WCAG AA compliant** — icon-only buttons and form labels need fixes

---

## What Comes Next (Post-v3.0.0)

| Priority | Item |
|---|---|
| 🔴 | Wire SMTP for password reset |
| 🔴 | Consent checkbox at registration (DPDP Act) |
| 🔴 | Automated retention purge scheduled job |
| 🟠 | WCAG 2.1 AA accessibility fixes |
| 🟠 | Column-level encryption for customer PII |
| 🟠 | Webhook dispatch with SSRF protection |
| 🟠 | AWS S3 integration for file storage |
| 🟡 | CI/CD pipeline (GitHub Actions) |
| 🟡 | Real fraud ML model (requires 200+ labeled outcomes) |
