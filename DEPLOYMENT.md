# ReturnIQ — Deployment Guide

**Version:** 0.9.0-rc1
**Backend:** 893 tests passing · **Frontend:** 75 tests passing · **0 failing**

---

## Before you deploy: what changed in this release

`DEMO_MODE` used to default to **`true`**. A deployment that forgot one
environment variable shipped a seeded organisation with a **publicly known
admin password** — `admin@sapnacollection.com` / `Demo@12345`, role
`org_admin` — plus demo API-key and password-reset-token endpoints, live and
reachable.

That default is now `false`, and the application **refuses to start** if
`DEMO_MODE=true` while `ENVIRONMENT=production`.

**Verified, not assumed** — booting with production config produces:

```
health/live    : 200
health/ready   : 200
demo api-key   : 404   (endpoint gone)
returns unauth : 401   (no anonymous access)
CSP present    : True
seeded orgs    : 0
seeded users   : 0
login with demo credentials : 401
```

---

## 1. Required environment variables

The application **will not start** in production without these. That is
deliberate — a missing secret should stop a deploy, not silently fall back to
a default someone can read on GitHub.

```bash
ENVIRONMENT=production
DEBUG=false
DEMO_MODE=false          # or omit entirely; false is the default

SECRET_KEY=<48+ random chars>
API_KEY_HASH_PEPPER=<48+ random chars, DIFFERENT from SECRET_KEY>

DATABASE_URL=postgresql://user:password@host:5432/returniq
CORS_ORIGINS=https://app.yourdomain.com
```

Generate secrets with:

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

**Do not reuse `SECRET_KEY` as `API_KEY_HASH_PEPPER`.** They protect
different things, and rotating one should not invalidate the other.

### Strongly recommended

```bash
REDIS_URL=redis://host:6379/0    # dashboard/analytics caching (Phase 39)
SMTP_HOST=...                    # password reset & invitations need this
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM=noreply@yourdomain.com
```

Without Redis the app runs fine and simply skips caching — it degrades to a
cache miss rather than failing. Without SMTP, **password reset and team
invitations do not work**; the app logs an error at startup rather than
failing silently.

---

## 2. Deploy

```bash
cp .env.example .env
# edit .env with the values above

docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

`docker-compose.prod.yml` already sets `ENVIRONMENT=production` and
`DEMO_MODE=false`.

### Create your first admin

There is no seeded account in production — that is the point. Register the
first user through the API:

```bash
curl -X POST https://api.yourdomain.com/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "full_name": "Your Name",
    "email": "you@yourdomain.com",
    "password": "<a real password>",
    "org_name": "Your Company",
    "platform_type": "shopify",
    "accepted_terms": true
  }'
```

The first user in an organisation becomes `org_admin`.

---

## 3. Post-deploy verification

Run these against the live deployment. Each one confirms a specific guard.

```bash
# 1. Alive and dependencies reachable
curl https://api.yourdomain.com/health/ready          # expect 200

# 2. No anonymous access to real data
curl https://api.yourdomain.com/api/v1/returns        # expect 401

# 3. Demo endpoints are gone
curl https://api.yourdomain.com/api/v1/org/demo-api-key  # expect 404

# 4. The known demo account does not exist
curl -X POST https://api.yourdomain.com/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@sapnacollection.com","password":"Demo@12345"}'
                                                       # expect 401

# 5. Security headers present
curl -I https://api.yourdomain.com/health/live | grep -i content-security-policy
```

**If check 4 returns 200, stop and fix your configuration before going
live.** It means `DEMO_MODE` was enabled at some point against this database
and the seeded admin account exists.

---

## 4. Backups

`infra/backups/backup_db.sh` and `restore_db.sh` are wired for the compose
setup. Schedule the backup:

```bash
0 2 * * * /path/to/infra/backups/backup_db.sh
```

**Test the restore before you need it.** The restore script now uses
`psql -v ON_ERROR_STOP=1` — without that flag, a statement failing partway
through a restore is printed and skipped, and the restore reports success
having lost data.

For full verification, `app/services/backup_integrity.py` compares row counts
**and content hashes** between a pre-backup manifest and a post-restore one.
Row counts alone are insufficient: a table can restore with exactly the right
number of rows and the wrong data in them.

---

## 5. What is deliberately not in this build

Stated plainly so nothing is a surprise in front of a customer.

| Area | Status |
|---|---|
| ML predictions | Rule-based and clearly labelled as such. The XGBoost cost model is trained on synthetic data and is functionally a distance calculator — see `PHASE_17_FEASIBILITY.md` |
| Billing / subscriptions | Not built. One permission string exists; no payment integration |
| SSO / SAML / SCIM | Not built |
| MFA / TOTP | Not built (the `mfa_enabled` column exists; the flow does not) |
| Shopify / WooCommerce connectors | Security layer built (Phase 33); the connectors themselves need vendor credentials |
| Damage detection (computer vision) | Image pipeline built; no model — needs labelled images |
| DPDP compliance sign-off | Engineering inputs delivered; **requires a qualified lawyer** |

**Every intelligence output in the product is labelled with what produced
it** — `ml_model`, `rule`, `derived`, or `observed` — and confidence bands
are honest about the synthetic-data limitation. Nothing claims to be a
trained model that isn't one.

---

## 6. First 30 days

The models cannot be trained until real returns flow. The portal (Phase 31)
is what starts that:

1. Point one merchant's return flow at the portal
2. Let returns accumulate — every one produces a labelled row
3. Record actual outcomes (cost, disposition, fraud confirmed) via
   `/returns/{id}/outcome`
4. At ~1,000 labelled outcomes, `build_dataset()` stops refusing and real
   model training becomes possible

Until then the rule-based scores are the product, and they are labelled
accordingly.
