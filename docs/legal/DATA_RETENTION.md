# Data Retention & Deletion Policy — ReturnIQ Enterprise

**Version:** 1.0 | **Effective Date:** 1 August 2025

---

## 1. Principles

- Retain data only as long as necessary for the stated purpose
- Delete data securely when retention periods expire
- Give users the tools to request deletion of their own data
- Document retention decisions so they can be audited

---

## 2. Retention Schedule

| Data Type | Retention Period | Deletion Method | Notes |
|---|---|---|---|
| Return requests | Indefinite while account active | Hard delete on org deletion + 90-day grace | Needed for ML outcome tracking |
| AI prediction records | Indefinite while account active | Cascade delete with return | Required for explainability and audit |
| Prediction outcome labels | Indefinite | Anonymised after 3 years | Future training data |
| Customer records | Until deleted by Merchant or org deletion | Soft delete then hard purge after 90 days | Merchant is the data controller |
| Uploaded documents | 90 days after return closure | Purge from storage + delete DB record | Configurable per org |
| Damage photos | 90 days after return closure | Same as above | |
| Audit logs | 2 years from creation | Hard delete after 2 years, cannot be manually deleted | Regulatory compliance |
| User accounts (active) | Until user deletes or org terminates | Soft delete → 90-day grace → hard purge | |
| User accounts (deleted) | 90 days after deletion request | Hard purge of PII; anonymised record retained | Fraud investigation window |
| Password reset tokens | 1 hour from creation | Auto-expire; consumed on first use | |
| Refresh tokens | 7 days or until revoked | Hard delete on logout, expiry, or rotation | |
| Revoked access tokens | 24 hours (matching JWT TTL) | Auto-purge after TTL | Kept only for revocation checks |
| HTTP server logs | 30 days rolling | Automated log rotation | Not linked to user IDs |
| API key hashes | Until revoked | Hard delete on revocation | Only hash stored, not plaintext key |
| Password reset tokens (used) | 24 hours after use | Auto-purge | |
| Notification records | 90 days | Auto-purge | |
| SLA tracking records | 1 year after resolution | Hard delete | |

---

## 3. Account Deletion Process

### 3.1 User Initiates Deletion
1. User calls `DELETE /api/v1/users/account` or submits request to privacy@returniq.in
2. Account status set to `deleted` immediately — user loses access
3. All active refresh tokens are revoked
4. A 90-day retention window begins
5. After 90 days: all PII fields are overwritten with anonymised values
   (`name → "[deleted]"`, `email → "deleted_{uuid}@anon.invalid"`)
6. Return records and predictions attributed to this user remain (for audit trail) but
   lose their user association after anonymisation

### 3.2 Organisation Terminates Account
1. `DELETE /api/v1/org/members/{member_id}` revokes tokens and marks user as `removed`
2. 90-day window, then PII anonymised as above

### 3.3 Merchant Requests Full Org Deletion
Submitted via email to privacy@returniq.in:
1. All users in the org are deactivated immediately
2. Data export provided within 7 days (if requested)
3. 90-day grace period (for dispute resolution)
4. All org data permanently deleted: returns, predictions, customers, documents, workflow
   rules, API keys, audit logs (except legally mandated 2-year logs)
5. Written confirmation sent within 30 days of completion

---

## 4. Uploaded Document Deletion

Uploaded documents (damage photos, invoices, etc.) are deleted:
- Automatically 90 days after the associated return's status changes to a closed state
  (approved / rejected / override_*)
- Immediately when explicitly deleted via `DELETE /api/v1/returns/{id}/documents/{doc_id}`
- As part of org deletion

When S3 is configured, deletion uses the AWS S3 `DeleteObject` API. The storage key is
removed from the `return_documents` table and the file is permanently deleted from S3.
S3 Versioning should be disabled or a lifecycle policy applied to prevent soft-deleted
versions persisting.

---

## 5. Secure Deletion

| Storage Location | Deletion Method |
|---|---|
| PostgreSQL records | `DELETE` or `UPDATE` with nullified PII fields |
| S3 files | `DeleteObject` API call; versioning must be off or lifecycle policy applied |
| Redis tokens | `DEL` command or key TTL expiry |
| Server logs | Log rotation with `shred`-equivalent on the filesystem |

Backup retention: database backups should be kept for a maximum of 30 days. Backups
older than 30 days should be securely deleted from backup storage. See
`docs/release/PRODUCTION_CHECKLIST.md` for backup configuration guidance.

---

## 6. Right to Erasure — Response Times

| Request Type | Response Time |
|---|---|
| Self-service account deletion | Immediate deactivation; 90-day full purge |
| Written erasure request (email) | Acknowledged within 72 hours; completed within 30 days |
| Data export request | Provided within 30 days |
| Org deletion request | Grace period 90 days; confirmed within 30 days of deletion |
