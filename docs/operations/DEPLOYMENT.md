# Deployment Guide — ReturnIQ Enterprise

---

## Pre-Deployment Checklist

Before going live, complete every item in `docs/release/PRODUCTION_CHECKLIST.md`.

---

## Architecture

```
                        HTTPS
Internet ──────────────────────────────────►  Nginx (Port 443)
                                                    │
                                          ┌─────────┴─────────┐
                                          │                   │
                                     Frontend              Backend API
                                     (React/Vite)          (FastAPI)
                                     Port 3000             Port 8000
                                                                │
                                                    ┌───────────┼───────────┐
                                                    │           │           │
                                               PostgreSQL    Redis       S3 / Local
                                               Port 5432    Port 6379   (file store)
```

---

## Production Docker Compose Deployment

### Step 1: Server Requirements

| Resource | Minimum | Recommended |
|---|---|---|
| CPU | 2 vCPU | 4 vCPU |
| RAM | 4 GB | 8 GB |
| Storage | 20 GB SSD | 100 GB SSD |
| OS | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS |
| Docker | 24.0+ | 24.0+ |

### Step 2: Prepare .env

```bash
# Generate secrets
python3 -c "import secrets; print('SECRET_KEY=' + secrets.token_hex(64))"
python3 -c "import secrets; print('API_KEY_HASH_PEPPER=' + secrets.token_hex(64))"

# Copy and fill .env
cp .env.example .env
nano .env
```

Required production values:
```env
SECRET_KEY=<64-char-hex>
API_KEY_HASH_PEPPER=<64-char-hex>
POSTGRES_PASSWORD=<strong-password>
ENVIRONMENT=production
DEMO_MODE=false
COOKIE_SECURE=true
CORS_ORIGINS=https://your-domain.com
```

### Step 3: TLS/HTTPS Setup

ReturnIQ requires HTTPS in production. Add a reverse proxy in front of Nginx:

**Option A — Let's Encrypt with Certbot:**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

**Option B — Cloudflare Proxy:** Route DNS through Cloudflare with "Full (strict)"
SSL mode and enable HSTS in Cloudflare settings.

**Option C — Load Balancer:** Use an AWS ALB or GCP Load Balancer with ACM/managed cert.

### Step 4: Deploy

```bash
docker compose -f docker-compose.yml up -d --build
```

Verify:
```bash
docker compose ps                          # all containers running
curl https://your-domain.com/health       # → {"status": "ok"}
docker compose logs backend --tail=50     # check for errors
```

### Step 5: First Admin Account

Register via the web UI at `https://your-domain.com/register`. This creates the
first `org_admin`. For the `super_admin` role, update the role directly in the DB:

```sql
UPDATE users SET role = 'super_admin' WHERE email = 'your-admin@email.com';
```

---

## Scaling

### Horizontal Backend Scaling

```yaml
# In docker-compose.yml
backend:
  deploy:
    replicas: 3
```

Requires:
- Redis for rate limiting (`USE_REDIS_RATE_LIMIT=true`) — otherwise rate limits are
  per-instance, not global
- A shared file storage layer (S3, not local) — local file paths are not shared
  across replicas
- A load balancer with sticky sessions or JWT-stateless routing (JWT is already
  stateless — this is fine)

### Database Connection Pool

```env
DB_POOL_SIZE=20      # connections per backend worker
DB_MAX_OVERFLOW=10   # burst connections
```

For 2 backend containers × 2 uvicorn workers × 20 connections = 80 total connections.
Ensure your Postgres `max_connections` (default 100) is set higher:
```sql
ALTER SYSTEM SET max_connections = 200;
```

---

## Backup Strategy

### Database Backup (Run daily via cron)

```bash
#!/bin/bash
# /etc/cron.d/returniq-backup
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="/backups/returniq_${TIMESTAMP}.sql.gz"

docker exec returniq-postgres pg_dump -U returniq returniq | gzip > $BACKUP_FILE

# Upload to S3
aws s3 cp $BACKUP_FILE s3://your-backup-bucket/db/

# Delete local files older than 7 days
find /backups -name "*.sql.gz" -mtime +7 -delete
```

Retention policy:
- Local: 7 days (space-efficient)
- S3: 30 days (standard); 1-year (Glacier for compliance)

### Verify Backups Monthly

```bash
# Restore to a test DB and verify row counts
gunzip -c returniq_backup.sql.gz | docker exec -i returniq-postgres psql -U returniq returniq_test
docker exec returniq-postgres psql -U returniq -c "SELECT count(*) FROM return_requests;" returniq_test
```

---

## Disaster Recovery

### Recovery Time Objective (RTO): 2 hours
### Recovery Point Objective (RPO): 24 hours (daily backups)

### Recovery Procedure

1. **Provision new server** (same spec as original)
2. **Clone repo** and restore `.env` from secure secrets manager
3. **Restore latest database backup:**
   ```bash
   aws s3 cp s3://your-backup-bucket/db/returniq_latest.sql.gz .
   gunzip returniq_latest.sql.gz
   docker exec -i returniq-postgres psql -U returniq returniq < returniq_latest.sql
   ```
4. **Start services:** `docker compose up -d`
5. **Verify:** `curl https://your-domain.com/health`
6. **Update DNS** to point to new server IP

### Incident Response Contacts

| Role | Contact |
|---|---|
| Primary Engineer | [Fill before go-live] |
| Backup Engineer | [Fill before go-live] |
| Security Contact | security@returniq.in |
| Cloud Provider Support | [AWS/GCP support link] |

---

## Rollback Procedure

If a deployment introduces a regression:

```bash
# 1. Roll back to previous image
docker compose down
git checkout <previous-tag>
docker compose up -d --build

# 2. If migration needs rollback
docker exec returniq-backend alembic downgrade -1

# 3. Verify
curl https://your-domain.com/health
docker compose logs backend --tail=50
```

See also `docs/release/ROLLBACK_PLAN.md` for version-specific rollback notes.
