# Admin Guide — ReturnIQ Enterprise

This guide is for `org_admin` and `super_admin` users.

---

## Team Management

### Inviting Team Members
1. Go to **My Profile** → (org settings) or use the API: `POST /api/v1/org/members/invite`
2. Enter email, full name, and role
3. The new user receives a temporary password (in demo mode: returned in the API response; in production: sent by email once SMTP is configured)
4. The user should change their password immediately on first login

### Roles

| Role | What They Can Do |
|---|---|
| `viewer` | Read returns, customers, reports — no write access |
| `analyst` | Everything a viewer can do + override AI decisions, submit feedback |
| `org_admin` | Full org management: invite/remove members, create workflow rules, manage feature flags, access admin reporting |
| `super_admin` | Platform-wide access: all orgs, all users, system settings |

### Removing a Member
`DELETE /api/v1/org/members/{member_id}` or use the Admin Panel → Users tab.
The member's sessions are immediately revoked.

### Changing a Role
`PATCH /api/v1/org/members/{member_id}/role`
You cannot change your own role.

---

## Organisation Settings

### Branding
`PATCH /api/v1/org/branding`
- Upload a logo URL (S3 link or public URL)
- Set a primary colour (hex code)
- Set your company website URL

### Feature Flags
Feature flags let you enable/disable specific platform features for your org:
`GET /api/v1/org/feature-flags` — see all flags
`PUT /api/v1/org/feature-flags/{flag_name}` — toggle a flag

---

## API Keys

For integrating your ERP, WMS, or custom tools with ReturnIQ:
1. Go to **Settings → API Setup** in the UI
2. Generate a new API key (shown only once — copy it immediately)
3. Use the `X-API-Key: <key>` header on all requests to `/api/v1/ext/` endpoints

To revoke a key: `DELETE /api/v1/org/api-keys/{prefix}`

**Security rules:**
- Never commit API keys to source code or Git repositories
- Never log API keys
- Use environment variables or secrets managers
- Rotate keys every 90 days (or immediately if exposed)

---

## Audit Logs

Every action in the platform is logged. To view:
- Your org's audit log: `GET /api/v1/admin/audit-logs` (org_admin)
- All-platform audit log: `GET /api/v1/admin/audit-logs` (super_admin)

Logs cannot be deleted — they are retained for 2 years.

Events logged include: login/logout, password changes, return creation, customer
blacklisting, document upload/delete, member invite/remove, role changes, AI overrides,
exports, setting changes.

---

## Workflow Rules

See the Workflow Automation section in the User Guide.

**Recommended starter rules:**

```
Rule 1: Auto-approve very low risk
  Type: auto_approve | Priority: 1
  Conditions: risk_score_lt=15, item_value_lt=300
  Action: status=approved, notify=true

Rule 2: Auto-reject known fraud patterns
  Type: auto_reject | Priority: 2
  Conditions: fraud_score_gt=85
  Action: status=rejected, notify=true, notify_severity=critical

Rule 3: Flag high-value for manual review
  Type: escalate | Priority: 3
  Conditions: item_value_gt=20000
  Action: status=manual_review, notify=true, set_sla_hours=12
```

---

## Admin Panel (super_admin only)

Access the Admin Panel from the sidebar.

### Health Dashboard
Shows:
- System status and timestamp
- Database row counts (orgs, users, returns, predictions, etc.)
- ML model status and label accumulation progress

### User Management
- View all users across all orgs
- Suspend or activate accounts
- Passwords are never shown

### System Settings
Key-value store for platform-wide settings.
Examples: `{ "key": "max_bulk_import_size", "value": 50 }`

### Database Statistics
Row counts for all major tables — useful for monitoring growth and planning.

---

## Monitoring & Alerts (Recommended Setup)

The platform does not include an alerting system yet (see Phase 5.12 roadmap).
Recommended manual monitoring until alerting is built:

1. **Failed logins:** Query `audit_logs` where `action = 'login_failed'` for the last hour
2. **Mass exports:** Query `audit_logs` where `action = 'export_customers'`
3. **SLA breaches:** `GET /api/v1/workflows/sla?breached_only=true`
4. **Health check:** `GET /api/v1/admin/health`

Set up a cron job to hit `/api/v1/workflows/sla/check-breaches` every 15–30 minutes
to auto-detect new SLA violations.
