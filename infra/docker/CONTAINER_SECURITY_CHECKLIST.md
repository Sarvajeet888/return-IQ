# Container Security Checklist — ReturnIQ Enterprise

**Phase 8.1 deliverable.** Verify each item before deploying to production.

---

## Image Build Security

| Check | Status | Notes |
|---|---|---|
| Multi-stage builds used | ✅ Done | `Dockerfile.backend` and `Dockerfile.frontend` — build deps not shipped to runtime |
| Base images pinned to specific versions | ✅ Done | `python:3.11-slim`, `nginx:1.27-alpine`, `node:20-alpine` — not `:latest` |
| Minimal base images | ✅ Done | `slim` / `alpine` variants only |
| No secrets in Dockerfile or image layers | ✅ Done | All secrets come from env vars at runtime |
| `.dockerignore` excludes sensitive files | ⚠️ Verify | Ensure `.env`, `.git`, `node_modules`, `*.pem` are listed |
| `--no-install-recommends` on apt-get | ✅ Done | Reduces image size and attack surface |
| apt lists cleaned after install | ✅ Done | `rm -rf /var/lib/apt/lists/*` |
| `npm ci --frozen-lockfile` not `npm install` | ✅ Done | Reproducible builds from lockfile |
| Image labels for traceability | ✅ Done | OCI labels with title, description, version |

---

## Runtime Security

| Check | Status | Notes |
|---|---|---|
| Containers run as non-root | ✅ Done | Backend uses `appuser`; nginx runs as `nginx` |
| No `--privileged` flag | ✅ Done | Not used anywhere in compose files |
| Resource limits set (CPU + memory) | ✅ Done | All services have `deploy.resources.limits` |
| Health checks defined | ✅ Done | Backend, frontend, postgres, redis all have healthchecks |
| Restart policy set | ✅ Done | `restart: always` in prod compose |
| Read-only volume mounts where possible | ✅ Done | ML artifacts, nginx configs, certs all mounted `:ro` |
| No unnecessary port exposure | ✅ Done | Only 80/443 exposed; Postgres/Redis/backend internal only |
| Secrets from env file, not hardcoded | ✅ Done | `.env` file, gitignored |

---

## Network Security

| Check | Status | Notes |
|---|---|---|
| Backend not directly internet-accessible | ✅ Done | No host port mapping in prod compose |
| Postgres not internet-accessible | ✅ Done | Port mapping removed in `docker-compose.prod.yml` |
| Redis not internet-accessible | ✅ Done | No port mapping |
| Firewall rules configured | ✅ Script provided | `infra/scripts/server_setup.sh` configures ufw |
| TLS/HTTPS enforced | ✅ Config provided | `infra/nginx/default.conf` with HSTS and HTTP→HTTPS redirect |
| Security headers on all responses | ✅ Done | HSTS, CSP, X-Frame-Options, X-Content-Type-Options, Referrer-Policy |
| Rate limiting at nginx level | ✅ Done | 5r/m on auth endpoints, 100r/m general |
| Rate limiting at app level | ✅ Done | slowapi with Redis backend |

---

## Data Security

| Check | Status | Notes |
|---|---|---|
| Database encrypted at rest | ⚠️ Cloud-dependent | RDS: `storage_encrypted = true` in Terraform. Self-hosted: use encrypted volume |
| Backups encrypted | ⚠️ Verify | S3 SSE enabled in Terraform; verify for local backups |
| S3 bucket not public | ✅ Done | Terraform config has no public ACL |
| S3 versioning enabled | ✅ Done | `aws_s3_bucket_versioning` on uploads bucket |
| Backup retention policy | ✅ Done | 30 days local, S3 lifecycle to Glacier at 30d, delete at 365d |
| Customer PII encrypted at column level | ❌ Not done | Known issue KI-002 — planned |

---

## Image Scanning

Run these before every production deploy:

```bash
# Trivy — scan for CVEs in image layers
docker run --rm -v /var/run/docker.sock:/var/run/docker.sock \
  aquasec/trivy:latest image --severity HIGH,CRITICAL \
  ghcr.io/your-org/returniq-backend:latest

# Docker Scout (built into Docker Desktop)
docker scout cves ghcr.io/your-org/returniq-backend:latest

# Hadolint — Dockerfile linter
docker run --rm -i hadolint/hadolint < infra/docker/Dockerfile.backend
```

**CI integration:** Add Trivy to `.github/workflows/ci.yml` as a step after `docker-build`:

```yaml
- name: Scan image with Trivy
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}-backend:sha-${{ github.sha }}
    severity: 'CRITICAL,HIGH'
    exit-code: '1'
```

---

## Pre-Deploy Verification Commands

```bash
# 1. Confirm backend runs as non-root
docker compose -f docker-compose.prod.yml exec backend whoami
# Expected: appuser  (NOT root)

# 2. Confirm no secrets baked into image
docker history ghcr.io/your-org/returniq-backend:latest --no-trunc | grep -i "secret\|password\|key"
# Expected: no matches

# 3. Confirm ports
docker compose -f docker-compose.prod.yml ps
# Expected: only frontend has 0.0.0.0:80 and 0.0.0.0:443

# 4. Confirm health checks passing
docker compose -f docker-compose.prod.yml ps --format "table {{.Name}}\t{{.Status}}"
# Expected: all say "(healthy)"

# 5. Verify security headers
curl -sI https://your-domain.com | grep -i "strict-transport\|x-frame\|content-security"
# Expected: all three present
```
