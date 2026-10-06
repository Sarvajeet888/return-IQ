#!/bin/bash
# ReturnIQ Enterprise — First-Time Server Setup (Phase 8.15)
# Run ONCE on a fresh Ubuntu 22.04 server.
# Usage: bash infra/scripts/server_setup.sh

set -euo pipefail

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "=== ReturnIQ Server Setup ==="
log "OS: $(lsb_release -d | cut -f2)"

# ── 1. System updates ─────────────────────────────────────────────────────────
log "Updating system..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Install Docker ─────────────────────────────────────────────────────────
log "Installing Docker..."
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Add current user to docker group
usermod -aG docker "${SUDO_USER:-$USER}" || true
log "Docker installed: $(docker --version)"

# ── 3. Install utilities ──────────────────────────────────────────────────────
apt-get install -y -qq git curl wget unzip awscli jq

# ── 4. Create project directory ───────────────────────────────────────────────
mkdir -p /opt/returniq
mkdir -p /opt/returniq/backups
mkdir -p /var/log/returniq

log "Project directory: /opt/returniq"

# ── 5. Set up cron jobs ───────────────────────────────────────────────────────
log "Setting up cron jobs..."

# Daily DB backup at 2am
(crontab -l 2>/dev/null; echo "0 2 * * * /opt/returniq/infra/backups/backup_db.sh >> /var/log/returniq/backup.log 2>&1") | crontab -

# SLA breach check every 15 minutes
(crontab -l 2>/dev/null; echo "*/15 * * * * curl -sf -H 'X-API-Key: \${RETURNIQ_INTERNAL_KEY}' http://localhost/api/v1/workflows/sla/check-breaches >> /var/log/returniq/sla.log 2>&1") | crontab -

log "Cron jobs configured"

# ── 6. Firewall ───────────────────────────────────────────────────────────────
log "Configuring firewall..."
ufw --force enable
ufw allow 22/tcp    # SSH
ufw allow 80/tcp    # HTTP (redirects to HTTPS)
ufw allow 443/tcp   # HTTPS
# Block direct access to backend (nginx proxy only)
ufw deny 8000/tcp
ufw deny 5432/tcp
log "Firewall configured"

# ── 7. Swap (for small servers) ───────────────────────────────────────────────
if [ ! -f /swapfile ]; then
  log "Creating 2GB swap file..."
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile
  swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
  log "Swap enabled"
fi

log ""
log "=== Server setup complete ==="
log "Next steps:"
log "  1. Clone the repo:  git clone <repo-url> /opt/returniq"
log "  2. Create .env:     cp /opt/returniq/.env.example /opt/returniq/.env && nano /opt/returniq/.env"
log "  3. Setup SSL:       bash /opt/returniq/infra/scripts/setup_ssl.sh your-domain.com your@email.com"
log "  4. Deploy:          bash /opt/returniq/infra/scripts/deploy.sh"
