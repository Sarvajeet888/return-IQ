#!/bin/bash
# ReturnIQ Enterprise — Let's Encrypt SSL Setup (Phase 8.4)
# Run once on your production server after DNS is pointing to it.
# Usage: bash infra/scripts/setup_ssl.sh your-domain.com your@email.com

set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"

if [ -z "$DOMAIN" ] || [ -z "$EMAIL" ]; then
  echo "Usage: $0 <domain> <email>"
  echo "Example: $0 app.returniq.in admin@returniq.in"
  exit 1
fi

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }

log "Setting up SSL for ${DOMAIN}"

# Step 1: Temporarily serve HTTP for ACME challenge
# Update nginx config to point to your domain first
sed -i "s/YOUR_DOMAIN/${DOMAIN}/g" /opt/returniq/infra/nginx/default.conf
log "Updated nginx config with domain: ${DOMAIN}"

# Step 2: Restart nginx to apply domain
docker compose -f /opt/returniq/docker-compose.prod.yml restart frontend
sleep 5

# Step 3: Issue certificate
docker compose -f /opt/returniq/docker-compose.prod.yml run --rm certbot \
  certonly \
  --webroot \
  -w /var/www/certbot \
  -d "${DOMAIN}" \
  -d "www.${DOMAIN}" \
  --email "${EMAIL}" \
  --agree-tos \
  --non-interactive

log "Certificate issued for ${DOMAIN}"

# Step 4: Restart frontend to load HTTPS config
docker compose -f /opt/returniq/docker-compose.prod.yml restart frontend

log "SSL setup complete. Verify at: https://${DOMAIN}/health"
