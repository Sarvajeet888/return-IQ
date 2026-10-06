# Production Deployment Runbook — ReturnIQ Enterprise

**Phase 8.15 deliverable.** Follow this end-to-end for a first-time production deploy.

---

## Prerequisites

- A server: Ubuntu 22.04 LTS, 4 vCPU, 8GB RAM, 50GB SSD minimum
- A domain name with DNS access
- SSH access to the server as root or a sudo user
- SMTP credentials (AWS SES, SendGrid, or Postmark)

---

## Part 1 — Server Preparation (~15 minutes)

### 1.1 Point your domain at the server

In your DNS provider, create these records:

| Type | Name | Value |
|---|---|---|
| A | `app` (or `@`) | `<your-server-IP>` |
| A | `www` | `<your-server-IP>` |

Wait for DNS to propagate (usually 5–30 minutes). Verify:
```bash
dig +short app.yourdomain.com
# Should return your server IP
```

### 1.2 Run the server setup script

SSH into the server and run:
```bash
ssh root@your-server-ip

# Download and run setup
curl -fsSL https://raw.githubusercontent.com/YOUR_ORG/returniq/main/infra/scripts/server_setup.sh -o setup.sh
bash setup.sh
```

This installs Docker, configures the firewall, creates swap, and sets up cron jobs.

### 1.3 Clone the repository

```bash
cd /opt
git clone https://github.com/YOUR_ORG/returniq.git returniq
cd returniq
```

---

## Part 2 — Configuration (~10 minutes)

### 2.1 Create the production .env

```bash
cp infra/deployment/env.prod.example .env
nano .env
```

Generate the two required secrets:
```bash
python3 -c "import secrets; print(secrets.token_hex(64))"   # → SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(64))"   # → API_KEY_HASH_PEPPER
```

Fill in at minimum:
```env
SECRET_KEY=<generated>
API_KEY_HASH_PEPPER=<generated>
POSTGRES_PASSWORD=<strong password>
ENVIRONMENT=production
DEMO_MODE=false
COOKIE_SECURE=true
CORS_ORIGINS=https://app.yourdomain.com
SMTP_HOST=<your smtp host>
SMTP_USER=<your smtp user>
SMTP_PASS=<your smtp password>
SMTP_FROM=noreply@yourdomain.com
```

Lock down permissions:
```bash
chmod 600 .env
```

### 2.2 Update the nginx config with your domain

```bash
sed -i 's/YOUR_DOMAIN/app.yourdomain.com/g' infra/nginx/default.conf
```

---

## Part 3 — SSL Certificate (~5 minutes)

```bash
bash infra/scripts/setup_ssl.sh app.yourdomain.com admin@yourdomain.com
```

This issues a free Let's Encrypt certificate and configures auto-renewal.

Verify:
```bash
ls /etc/letsencrypt/live/app.yourdomain.com/
# Should show: fullchain.pem, privkey.pem, cert.pem, chain.pem
```

---

## Part 4 — First Deploy (~10 minutes)

```bash
bash infra/scripts/deploy.sh --skip-backup
```

(Skip backup on the very first deploy — there's no database to back up yet.)

Watch the output. The script will:
1. Build both containers
2. Run all database migrations
3. Start all services
4. Wait for the backend health check
5. Run smoke tests
6. Tag the release

### Verify

```bash
# All containers healthy?
docker compose -f docker-compose.prod.yml ps

# Health endpoint responding?
curl https://app.yourdomain.com/health
# Expected: {"status":"ok","version":"3.0.0"}

# HTTPS working with valid cert?
curl -sI https://app.yourdomain.com | head -1
# Expected: HTTP/2 200

# Security headers present?
curl -sI https://app.yourdomain.com | grep -i "strict-transport"
# Expected: strict-transport-security: max-age=63072000; includeSubDomains; preload
```

---

## Part 5 — Create the First Admin Account

Open `https://app.yourdomain.com/register` in a browser and register.

Then promote yourself to super_admin:
```bash
docker compose -f docker-compose.prod.yml exec postgres \
  psql -U returniq returniq \
  -c "UPDATE users SET role = 'super_admin' WHERE email = 'your@email.com';"
```

---

## Part 6 — Enable Monitoring (~5 minutes)

```bash
docker compose \
  -f docker-compose.prod.yml \
  -f infra/monitoring/docker-compose.monitoring.yml \
  -f infra/logging/docker-compose.logging.yml \
  up -d
```

Access Grafana at `http://your-server-ip:3001`
Default login: `admin` / whatever you set as `GRAFANA_PASSWORD`

**Change the Grafana password immediately.**

Add data sources in Grafana:
- Prometheus: `http://prometheus:9090`
- Loki: `http://loki:3100`

---

## Part 7 — Verify Backups

```bash
# Run a manual backup
bash infra/backups/backup_db.sh

# Confirm it was created
ls -lh /opt/returniq/backups/

# Verify cron is scheduled
crontab -l | grep backup
```

**Test the restore procedure on a staging server before you need it in an emergency.**

---

## Part 8 — Production Smoke Test

Run through this manually in a browser:

- [ ] Register a new account → succeeds
- [ ] Log in → succeeds, lands on dashboard
- [ ] Submit a new return → prediction returns in < 2 seconds
- [ ] View the return in the Returns list → appears
- [ ] Open AI Platform → Prediction History → Explain → shows feature importances
- [ ] Create a workflow rule → saves
- [ ] Submit another return → rule fires (check the `workflow_rules_applied` field)
- [ ] Generate a Summary report → loads
- [ ] Export CSV → downloads
- [ ] Forgot password → email received (confirms SMTP works)
- [ ] Log out → session cleared

---

## Ongoing Operations

### Deploy an update
```bash
cd /opt/returniq
bash infra/scripts/deploy.sh
```

### View logs
```bash
docker compose -f docker-compose.prod.yml logs -f backend
docker compose -f docker-compose.prod.yml logs --tail=100 backend | jq   # JSON logs
```

### Restart a service
```bash
docker compose -f docker-compose.prod.yml restart backend
```

### Manual backup
```bash
bash infra/backups/backup_db.sh
```

### Restore from backup
```bash
bash infra/backups/restore_db.sh /opt/returniq/backups/returniq_db_20250801_020000.sql.gz
```

### Rollback a bad deploy
See `docs/release/ROLLBACK_PLAN.md`.

---

## Troubleshooting

**Certbot fails: "Challenge failed"**
DNS hasn't propagated yet, or port 80 is blocked. Check `dig +short yourdomain.com` and `ufw status`.

**Backend won't start: "SECRET_KEY is required"**
The `.env` file is missing or has placeholder values. Check `cat .env | grep SECRET_KEY`.

**502 Bad Gateway from nginx**
The backend isn't healthy yet. Check `docker compose -f docker-compose.prod.yml logs backend`.

**Migrations fail on deploy**
Check `docker compose -f docker-compose.prod.yml logs backend | grep alembic`. Restore from the pre-deploy backup if the DB is in a broken state.

**Out of disk space**
```bash
docker system prune -a --volumes -f    # careful: removes unused volumes
find /opt/returniq/backups -mtime +7 -delete
```
