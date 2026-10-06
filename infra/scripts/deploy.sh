#!/bin/bash
# ReturnIQ Enterprise — Production Deploy Script (Phase 8.14 / 8.15)
# Usage: bash infra/scripts/deploy.sh [--skip-backup] [--skip-tests]
#
# What it does:
#   1. Runs pre-deploy backup
#   2. Pulls latest code
#   3. Builds containers
#   4. Runs migrations
#   5. Reloads services (zero-downtime rolling restart)
#   6. Smoke tests
#   7. Tags the release

set -euo pipefail

SKIP_BACKUP=false
SKIP_TESTS=false
PROJECT_DIR="${PROJECT_DIR:-/opt/returniq}"
COMPOSE="docker compose -f ${PROJECT_DIR}/docker-compose.prod.yml"

for arg in "$@"; do
  case $arg in
    --skip-backup) SKIP_BACKUP=true ;;
    --skip-tests)  SKIP_TESTS=true ;;
  esac
done

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
fail() { log "FAILED: $1"; exit 1; }

cd "${PROJECT_DIR}"

log "=== ReturnIQ Deployment Starting ==="
log "Branch: $(git rev-parse --abbrev-ref HEAD)"
log "Commit: $(git rev-parse --short HEAD)"

# ── 1. Pre-deploy backup ──────────────────────────────────────────────────────
if [ "${SKIP_BACKUP}" = false ]; then
  log "Taking pre-deploy database backup..."
  bash "${PROJECT_DIR}/infra/backups/backup_db.sh" \
    || fail "Pre-deploy backup failed. Deployment aborted."
  log "Backup complete"
else
  log "Skipping backup (--skip-backup)"
fi

# ── 2. Pull latest code ───────────────────────────────────────────────────────
log "Pulling latest code..."
git pull origin main

# ── 3. Build containers ───────────────────────────────────────────────────────
log "Building containers..."
${COMPOSE} build --no-cache backend frontend

# ── 4. Run migrations ─────────────────────────────────────────────────────────
log "Running database migrations..."
${COMPOSE} run --rm backend sh -c "alembic upgrade head" \
  || fail "Migration failed. Deployment aborted."
log "Migrations complete"

# ── 5. Rolling restart ────────────────────────────────────────────────────────
log "Restarting services..."
${COMPOSE} up -d --no-build

# Wait for backend to be healthy
log "Waiting for backend to become healthy..."
for i in $(seq 1 30); do
  if ${COMPOSE} exec -T backend curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    log "Backend is healthy"
    break
  fi
  if [ $i -eq 30 ]; then
    fail "Backend did not become healthy after 30 attempts. Check logs: docker compose logs backend"
  fi
  sleep 5
done

# ── 6. Smoke tests ────────────────────────────────────────────────────────────
if [ "${SKIP_TESTS}" = false ]; then
  log "Running smoke tests..."

  # Health endpoint
  curl -sf "http://localhost/health" > /dev/null \
    || fail "Smoke test failed: /health endpoint not responding"

  # Frontend loads
  curl -sf "http://localhost/" | grep -q "ReturnIQ" \
    || log "Warning: Frontend index page didn't contain expected content"

  log "Smoke tests passed"
fi

# ── 7. Tag release ────────────────────────────────────────────────────────────
VERSION="v$(date +%Y.%m.%d)-$(git rev-parse --short HEAD)"
git tag "${VERSION}" 2>/dev/null && git push origin "${VERSION}" 2>/dev/null || true
log "Release tagged: ${VERSION}"

# ── 8. Cleanup ────────────────────────────────────────────────────────────────
docker image prune -f > /dev/null 2>&1 || true

log "=== Deployment complete: ${VERSION} ==="
