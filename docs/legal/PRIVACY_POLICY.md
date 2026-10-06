# Privacy Policy — ReturnIQ Enterprise

**Effective Date:** 1 August 2025
**Last Updated:** 1 August 2025
**Version:** 1.0

---

## 1. Who We Are

ReturnIQ Enterprise ("ReturnIQ", "we", "us", "our") is a B2B SaaS platform that helps
e-commerce merchants and logistics operators manage, score, and route product returns
using machine learning and business-rule automation.

**Data Controller:** The organisation that registered a ReturnIQ account (the "Merchant")
acts as the primary data controller for the customer data it uploads or processes through
the platform. ReturnIQ acts as a **data processor** on behalf of Merchants for that data,
and as an independent **data controller** for account and usage data it collects about
Merchant users.

For questions about this policy, contact: **privacy@returniq.in**

---

## 2. What Data We Collect

### 2.1 Account & Identity Data
Data collected when a Merchant registers or manages their account:
- Full name, email address, password (bcrypt-hashed — never stored in plaintext)
- Organisation name, plan tier, billing contact
- Role and permission level within the organisation
- Profile photo URL (optional)

### 2.2 Return Request Data
Data submitted by Merchants when processing a customer return:
- Platform order ID, SKU, item category, item value
- Customer identifier (email or ID — provided by the Merchant)
- Origin and destination pincodes
- Weight, dimensions, courier name
- Return reason code, payment mode
- Condition description, customer notes
- Uploaded documents: damage photos, invoices, warranty cards, shipping labels

### 2.3 AI Prediction Records
Generated automatically when a return is submitted:
- Predicted return cost (XGBoost model output)
- Risk score, fraud score, damage probability (rule-based)
- Routing decision (accept / reject / manual_review / refund_and_keep)
- Feature snapshot used for the prediction
- Model version, inference latency
- Confidence score and explainability data

### 2.4 Customer Records
Merchant-provided records of their end-customers:
- Name, email, phone number, city
- Return history, risk level, blacklist status
- Notes added by Merchant staff

### 2.5 Authentication & Session Data
- Access tokens (JWT, in-memory only — never stored server-side)
- Refresh tokens (stored as HMAC-SHA256 hashes, not plaintext)
- Login timestamps and session activity
- Password reset tokens (single-use, expire in 1 hour)

### 2.6 Audit Logs
Every significant action in the platform generates an audit log entry:
- User ID, organisation ID, action type, timestamp
- Human-readable description of what was changed
- These logs are retained for compliance and cannot be deleted by users

### 2.7 Uploaded Files
- File name, MIME type, file size
- Storage key (S3 path or local path)
- Whether the file is a damage photo
- Uploaded by user ID, timestamp

### 2.8 Technical & Usage Data
- IP address (for rate limiting — not stored long-term)
- HTTP request logs (stored in server logs with a 30-day rolling window)
- API key usage (key hashes only, not plaintext keys)

---

## 3. Why We Collect This Data (Legal Basis)

| Data Category | Purpose | Legal Basis |
|---|---|---|
| Account & identity | Authenticate users, deliver the service | Contract performance |
| Return request data | Core ML scoring and routing | Contract performance (Merchant's instruction) |
| AI prediction records | Provide routing decisions, explainability, retraining groundwork | Contract performance |
| Customer records | Enable customer management features | Contract performance (Merchant's instruction) |
| Audit logs | Security, fraud detection, compliance | Legitimate interest / Legal obligation |
| Session tokens | Maintain secure login sessions | Contract performance |
| Technical logs | Debugging, rate limiting, abuse prevention | Legitimate interest |

---

## 4. Who Can Access Your Data

### 4.1 Within Your Organisation
All data is scoped to your Organisation ID. Members of your organisation can access data
based on their assigned role (viewer / analyst / org_admin / super_admin). See the
Permission Matrix in `SECURITY_AUDIT_PHASE6.md` for the full access control table.

### 4.2 ReturnIQ Staff
ReturnIQ engineering and support staff may access organisation data:
- To resolve a support ticket (only with Merchant consent)
- To investigate a security incident
- To maintain and operate the platform

All staff access is logged in the system audit trail.

### 4.3 Sub-processors
ReturnIQ uses the following sub-processors:

| Sub-processor | Purpose | Location |
|---|---|---|
| PostgreSQL (self-hosted) | Primary database | Merchant-configured server |
| Redis (self-hosted) | Rate limiting, session cache | Merchant-configured server |
| AWS S3 (optional) | File/document storage | Configurable region |

ReturnIQ does **not** sell data to third parties. ReturnIQ does **not** use Merchant data
to train models for other customers.

### 4.4 Law Enforcement
We will disclose data to law enforcement or government authorities only when:
- Required by a valid court order or legal obligation
- Necessary to protect the safety of users or the public

---

## 5. Data Storage & Security

- **Database:** PostgreSQL with connection-level TLS. Stored on Merchant-configured
  infrastructure.
- **Passwords:** bcrypt with cost factor 12. Never stored in plaintext.
- **API Keys:** HMAC-SHA256 hashed with a pepper. Only the hash is stored.
- **Tokens:** Refresh tokens stored as HMAC-SHA256 hashes. Access tokens are
  short-lived JWTs (15 minutes) stored only in the browser's memory.
- **Files:** Stored at a configurable path (local or S3). Not encrypted at rest
  by default — **Merchants handling sensitive documents should enable S3 server-side
  encryption (SSE-S3 or SSE-KMS) at the bucket level.**
- **Customer PII (email, phone):** Currently stored in plaintext database columns.
  Column-level encryption is planned before general availability for large-scale
  production deployments.
- **Transmission:** All traffic should be served over HTTPS. The platform enforces
  `Strict-Transport-Security` headers (HSTS) in responses.

---

## 6. Data Retention

| Data Type | Default Retention | Notes |
|---|---|---|
| Return requests | Indefinite | Needed for ML training groundwork and audit |
| AI prediction records | Indefinite | Required for explainability and outcome tracking |
| Audit logs | 2 years | Regulatory compliance |
| Uploaded documents | 90 days after return closure | Configurable by org admin |
| Password reset tokens | 1 hour | Auto-expire; consumed on use |
| Refresh tokens | 7 days or until revoked | Rotated on each use |
| Server HTTP logs | 30 days rolling | Not linked to user accounts |
| Soft-deleted accounts | 90 days then purge | Retained for fraud investigation |

---

## 7. Your Rights (DPDP Act 2023 & General Principles)

As a data principal (individual user), you have the following rights:

| Right | How to Exercise |
|---|---|
| **Access** | `GET /api/v1/users/profile` returns your personal data. `GET /api/v1/users/activity` returns your audit history. |
| **Correction** | `PATCH /api/v1/users/profile` to update your name or avatar. Contact privacy@returniq.in for other corrections. |
| **Erasure** | `DELETE /api/v1/users/account` deactivates your account. Full deletion within 90 days upon written request. |
| **Portability** | Contact privacy@returniq.in. We will provide your data in JSON format within 30 days. |
| **Withdraw Consent** | Where processing is based on consent, you may withdraw it at any time. This does not affect processing already done. |
| **Grievance** | Email privacy@returniq.in. We will acknowledge within 72 hours and resolve within 30 days. |

**Note for Merchant end-customers:** If you are an end-customer of a business that uses
ReturnIQ, your data is controlled by that business (the Merchant). Please contact the
Merchant directly to exercise your rights over your return data.

---

## 8. Cookies

See `COOKIE_POLICY.md` for detailed cookie information. In summary:

- **`rl_refresh_token`** — httpOnly, Secure, SameSite=Lax. Used to maintain login
  sessions. Essential — cannot be disabled.
- No analytics cookies are currently set.
- No advertising cookies are set or planned.

---

## 9. Children's Data

ReturnIQ is a B2B platform intended for business users aged 18 and over. We do not
knowingly collect personal data from anyone under 18. If you believe a minor's data has
been submitted, contact privacy@returniq.in immediately.

---

## 10. Changes to This Policy

We will notify registered users by email and in-app notification at least 14 days before
any material changes to this policy take effect. Continued use after that date constitutes
acceptance of the revised policy.

---

## 11. Contact

**Privacy Officer:** privacy@returniq.in
**Registered Address:** [To be completed before go-live]
**Grievance Officer (DPDP Act):** privacy@returniq.in

*This policy is governed by the laws of India. Disputes shall be subject to the
exclusive jurisdiction of courts in [City], India.*
