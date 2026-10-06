# Production Checklist — ReturnIQ Enterprise

Complete every item before going live. Mark each with ✅ when done.

---

## 🔐 Security

- [ ] `SECRET_KEY` set to a unique 64-char hex string (not the .env.example placeholder)
- [ ] `API_KEY_HASH_PEPPER` set to a unique 64-char hex string
- [ ] `ENVIRONMENT=production` set
- [ ] `DEMO_MODE=false` set — confirms forgot-password no longer leaks tokens
- [ ] `COOKIE_SECURE=true` set — requires HTTPS
- [ ] `CORS_ORIGINS` set to exact frontend domain(s) only — not `*`
- [ ] HTTPS enforced via TLS certificate (Let's Encrypt, Cloudflare, or ACM)
- [ ] HSTS header confirmed active in browser DevTools (present by default in Phase 6)
- [ ] Backend NOT directly internet-accessible — behind nginx reverse proxy
- [ ] Docker containers running as non-root user (confirmed in Phase 6 Dockerfile)
- [ ] `.env` file has `chmod 600` permissions
- [ ] `.env` is in `.gitignore` and NOT committed to the repository
- [ ] API keys documented and stored in a secrets manager, not in source code

---

## 🗄️ Database

- [ ] PostgreSQL 15+ running with dedicated persistent volume
- [ ] `alembic upgrade head` completed successfully — all tables created
- [ ] Postgres `max_connections` set appropriately for your worker count
- [ ] Database password is strong (not the .env.example default)
- [ ] First super_admin user created and role set in DB
- [ ] Automated daily backup cron job configured and tested
- [ ] Backup restore procedure tested at least once on a test server
- [ ] S3 backup bucket configured with 30-day retention and Glacier for longer retention

---

## 📧 Email / SMTP (Required for password reset to work)

- [ ] SMTP credentials obtained (AWS SES, SendGrid, Postmark, etc.)
- [ ] `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASS`, `SMTP_FROM` set in `.env`
- [ ] Forgot-password flow tested end-to-end: request → email received → token consumed → new password works
- [ ] Email sending rate limits noted (avoid hitting SES limits on bulk invites)

---

## ⚖️ Legal & Compliance

- [ ] Privacy Policy published and linked from registration page
- [ ] Terms of Service published and linked from registration page
- [ ] Cookie Policy published
- [ ] AI Transparency Statement published
- [ ] Registration form has "By registering you agree to our [Terms] and [Privacy Policy]" checkbox
- [ ] Consent timestamp and policy version stored on registration
- [ ] Grievance Officer email confirmed active (privacy@returniq.in)
- [ ] DPA executed with AWS S3 (if used for document storage)
- [ ] DPDP Act breach notification process documented and owner assigned

---

## 📦 Infrastructure

- [ ] Redis running and `USE_REDIS_RATE_LIMIT=true` set for distributed rate limiting
- [ ] All Docker health checks passing: `docker compose ps`
- [ ] Frontend Nginx serving correct index.html and proxying API correctly
- [ ] Health endpoint returning 200: `curl https://your-domain.com/health`
- [ ] ML artifacts present: `backend/ml/artifacts/model.joblib`, `preprocessor.joblib`, `feature_columns.json`, `model_metadata.json`
- [ ] Disk space monitored — minimum 20GB free before launch
- [ ] Server time zone set correctly (UTC recommended)

---

## 🧪 Testing

- [ ] All 33 backend tests passing: `cd backend && pytest -v`
- [ ] End-to-end test: register → submit return → view prediction → logout → login
- [ ] Bulk import tested with 10+ returns
- [ ] File upload tested (JPEG and PDF)
- [ ] Forgot password flow tested (requires SMTP — see above)
- [ ] API key generation and external API access tested
- [ ] Workflow rule creation and auto-trigger tested

---

## 📊 Monitoring

- [ ] Health check endpoint monitored by uptime tool (UptimeRobot, Grafana, etc.)
- [ ] Postgres disk usage monitored
- [ ] SLA breach check cron job configured (every 15–30 min)
- [ ] Log rotation configured for Docker container logs
- [ ] Incident response contacts documented

---

## 📄 Documentation

- [ ] `docs/legal/PRIVACY_POLICY.md` — complete and reviewed by legal
- [ ] `docs/legal/TERMS_OF_SERVICE.md` — complete and reviewed by legal
- [ ] `docs/legal/AI_TRANSPARENCY.md` — complete
- [ ] API documentation accessible at `/docs` (or disabled in production and hosted separately)
- [ ] `CHANGELOG.md` up to date for this release

---

## 🚀 Go/No-Go Decision

Sign off required from:

| Role | Name | Date | Sign-off |
|---|---|---|---|
| Engineering Lead | | | ☐ Go ☐ No-Go |
| Product Owner | | | ☐ Go ☐ No-Go |
| Legal Reviewer | | | ☐ Go ☐ No-Go |

**All items above must be checked before Engineering Lead signs off.**
