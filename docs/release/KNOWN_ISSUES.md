# Known Issues — ReturnIQ Enterprise v3.0.0

Last updated: 1 August 2025

---

## Critical (Must Fix Before High-Volume Production Use)

### KI-001 — SMTP Not Wired
**Impact:** Password reset emails are never sent in production. The forgot-password flow
returns a `demo_token` in development (`DEMO_MODE=true`) but is effectively broken for
real users when `DEMO_MODE=false`.
**Workaround:** Admins can manually reset a user's password by updating the `password_hash`
field in the database directly (using `bcrypt` to hash the new value).
**Fix:** Integrate an SMTP provider (AWS SES, SendGrid, Postmark). Set `SMTP_HOST`,
`SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` in `.env`. Wire the `send_email()`
call in `routes/users.py:forgot_password()`.

### KI-002 — Customer PII Stored in Plaintext
**Impact:** Customer email, phone number, and name are stored unencrypted in the
PostgreSQL `customers` table.
**Risk:** A database breach exposes customer PII directly.
**Workaround:** Ensure PostgreSQL is on an encrypted volume (OS-level or cloud provider
encryption at rest). Restrict DB access to the application server only.
**Fix:** Implement column-level encryption using `pgcrypto` or SQLAlchemy-level encryption
before handling large volumes of customer PII.

### KI-003 — No Consent Record at Registration (DPDP Act)
**Impact:** The DPDP Act 2023 requires that consent to data processing is recorded with
a timestamp and the policy version accepted. Currently, no consent checkbox or record
exists at registration.
**Workaround:** Until built, ensure your organisation's Terms of Service acceptance is
captured through a separate process (email confirmation, contract, etc.).
**Fix:** Add a consent checkbox to the registration form (`Register.jsx`) and store the
consent timestamp and policy version in the `users` table.

---

## High (Fix Before Scale-Up)

### KI-004 — Accessibility Not WCAG 2.1 AA Compliant
**Impact:** Icon-only buttons have no accessible labels, form labels are not linked to
inputs via `htmlFor`, and modals do not trap focus.
**Affected Users:** Screen reader users, keyboard-only users.
**Fix:** See `docs/compliance/ACCESSIBILITY_AUDIT.md` for the full remediation list
(estimated 6–10 hours of frontend work).

### KI-005 — Webhook Dispatch Not Implemented
**Impact:** The `webhook_url` field in org settings is stored but events are never
dispatched to it.
**Risk if implemented naively:** SSRF vulnerability — a malicious webhook URL could
target internal services.
**Fix:** Implement webhook dispatch with private IP range validation before enabling.
See `SECURITY_AUDIT_PHASE6.md` OWASP A10 note.

### KI-006 — No Automated Data Retention Purge
**Impact:** Records are not automatically deleted when their retention period expires.
The retention policy in `DATA_RETENTION.md` is documented but not enforced by code.
**Workaround:** Manual quarterly review and deletion.
**Fix:** Implement a scheduled background task (cron or Celery beat) that runs the
retention rules daily.

### KI-007 — Rate Limiting is Per-Instance (Not Distributed)
**Impact:** When running multiple backend replicas, rate limits are enforced per-instance
rather than globally. A user can bypass the limit by having requests load-balanced across
instances.
**Fix:** Set `USE_REDIS_RATE_LIMIT=true` and ensure Redis is configured. Already
supported in Phase 6 — just needs the env var set and Redis connected.

---

## Medium

### KI-008 — No CI/CD Pipeline
**Impact:** No automated test run on pull requests or deployments. Tests must be run
manually.
**Fix:** Add a GitHub Actions workflow: run `pytest` on every PR, build Docker image
on merge to main.

### KI-009 — R² Score of 0.9993 Is Unverified
**Impact:** The model metadata reports R²=0.9993. This was from a single training run
without confirmed cross-validation. The real generalization performance is unknown.
**Risk:** Overconfidence in model accuracy; users may not scrutinize high-confidence
predictions sufficiently.
**Fix:** Retain labeled outcome data via the `/outcome` endpoint. Once 500+ outcomes
exist, evaluate the model on this held-out production data for a real accuracy estimate.

### KI-010 — No Database Backup Monitoring
**Impact:** If the backup cron job fails silently, the last valid backup could be
days old without anyone knowing.
**Fix:** Add a backup health check — verify that a backup file was created in the last
25 hours and alert if not.

### KI-011 — S3 File Storage Not Integrated
**Impact:** Document uploads are stored locally. On Docker, the storage path is inside
the container — restarting or replacing the container loses uploaded files.
**Workaround:** Mount a persistent host volume for the upload path in `docker-compose.yml`.
**Fix:** Integrate AWS S3 using `boto3`. Storage key is already designed to be an S3
path — the upload/download functions just need to route to S3 instead of local disk.

---

## Low

### KI-012 — Model Confidence Score Is a Heuristic Proxy
**Impact:** The confidence score is not a statistically calibrated probability. It may
give false confidence on predictions near decision boundaries.
**Note:** This is documented in `AI_TRANSPARENCY.md`. No code fix is required until
a calibration method is implemented.

### KI-013 — SLA Breach Check Requires Manual Trigger or External Cron
**Impact:** SLA breaches are not automatically detected. The `GET /workflows/sla/check-breaches`
endpoint must be called by an external cron job or manual action.
**Fix:** Add a background thread or Celery task that calls this check every 15 minutes.
