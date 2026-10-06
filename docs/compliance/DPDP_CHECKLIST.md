# DPDP Act 2023 Compliance Checklist — ReturnIQ Enterprise

**India's Digital Personal Data Protection Act, 2023**
**Assessment Date:** 1 August 2025
**Assessor:** Engineering Team (self-assessment — independent legal review recommended before go-live)

---

## Summary

| Section | Status | Notes |
|---|---|---|
| Lawful basis for processing | 🟡 Partial | Contractual basis documented; consent framework not yet built |
| Notice to data principals | 🟡 Partial | Privacy Policy exists; in-app notice not yet displayed at registration |
| Consent management | ❌ Not built | Required before handling non-essential personal data |
| Right of access | ✅ Done | API endpoint available |
| Right to correction | ✅ Done | Profile update endpoint available |
| Right to erasure | 🟡 Partial | Account deletion implemented; 90-day purge process documented |
| Right to grievance | 🟡 Partial | Email address defined; no formal tracking system |
| Data minimisation | 🟡 Partial | Most fields are necessary; customer phone is optional but still collected |
| Storage limitation | ✅ Done | Retention policy documented and scheduled |
| Security safeguards | ✅ Done | bcrypt, HMAC, httpOnly cookies, HSTS, rate limiting |
| Children's data | ✅ Done | B2B platform; under-18 use prohibited in ToS |
| Cross-border transfer | 🟡 Partial | AWS S3 region is configurable; not restricted to India by default |
| Data Fiduciary obligations | ❌ Not registered | Registration with the Data Protection Board not yet done |
| Processing agreement with processor | ❌ Not drafted | DPA with cloud providers not yet executed |

---

## Detailed Checklist

### Part A — Grounds for Processing (Section 4)

| Requirement | Status | Evidence |
|---|---|---|
| Processing only for lawful purpose | ✅ | Return management, fraud prevention, analytics |
| Consent obtained OR legitimate use case | 🟡 | Contract performance used; explicit consent flow not built |
| Consent is free, specific, informed, unambiguous | ❌ | No consent banner or consent record exists |
| Consent can be withdrawn | 🟡 | Account deletion acts as withdrawal; no granular consent withdrawal |

**Action required:** Build a consent collection step at registration for non-essential
processing. Store consent records with timestamp and version.

---

### Part B — Notice (Section 5)

| Requirement | Status | Evidence |
|---|---|---|
| Notice provided before or at time of collection | 🟡 | Privacy Policy exists but not displayed during registration flow |
| Notice in clear, plain language | ✅ | Privacy Policy written in plain English |
| Notice includes purpose, data types, rights | ✅ | All included in `PRIVACY_POLICY.md` |
| Notice includes grievance officer details | ✅ | privacy@returniq.in named |

**Action required:** Add a "By registering, you agree to our [Privacy Policy]" checkbox
with a link at registration. Store the timestamp and policy version accepted.

---

### Part C — Data Principal Rights (Sections 11–14)

| Right | Section | Status | Implementation |
|---|---|---|---|
| Right of access | 11 | ✅ | `GET /api/v1/users/profile` + `/users/activity` |
| Right to correction | 12 | ✅ | `PATCH /api/v1/users/profile` |
| Right to erasure | 13 | 🟡 | Account deletion implemented; full purge in 90 days |
| Right to grievance | 14 | 🟡 | Email defined; no SLA tracking system |
| Right to nominate | 14(4) | ❌ | Not applicable for B2B; may be required for individual user accounts |

---

### Part D — Security Safeguards (Section 8)

| Requirement | Status | Evidence |
|---|---|---|
| Appropriate technical safeguards | ✅ | bcrypt, HMAC, JWT with alg allowlist, HSTS |
| Breach notification obligation | 🟡 | No breach notification process documented |
| Data minimisation | 🟡 | Most fields necessary; phone number optional but routinely collected |

**Action required:** Document a data breach response plan (detect → contain → notify
Data Protection Board within 72 hours → notify affected data principals).

---

### Part E — Data Retention (Section 8(7))

| Requirement | Status | Evidence |
|---|---|---|
| Erase data when purpose is served | 🟡 | Retention schedule documented; automated purge not yet implemented |
| No retention beyond what is necessary | 🟡 | Return data retained indefinitely — justified for ML, but should be reviewed |

**Action required:** Implement a scheduled job to purge expired records per the
retention schedule in `DATA_RETENTION.md`.

---

### Part F — Children's Data (Section 9)

| Requirement | Status |
|---|---|
| Parental consent for under-18 processing | ✅ Platform is B2B only; under-18 use prohibited in ToS |
| No behavioural tracking of children | ✅ |

---

### Part G — Data Fiduciary Obligations (Chapter III)

| Requirement | Status | Notes |
|---|---|---|
| Register as Data Fiduciary (when mandated) | ❌ | Registration framework not yet notified; monitor for updates |
| Appoint Data Protection Officer | ❌ | Not yet appointed; required for Significant Data Fiduciaries |
| Conduct DPIA for high-risk processing | ❌ | Not conducted; recommended before handling large volumes of PII |
| Execute DPA with sub-processors | ❌ | Required before using AWS S3 for PII storage |

---

## Open Action Items (Prioritised)

| Priority | Action | Owner | Deadline |
|---|---|---|---|
| 🔴 | Add consent checkbox + policy version capture at registration | Frontend | Before go-live |
| 🔴 | Draft and execute DPA with AWS (or chosen S3 provider) | Legal | Before using S3 for PII |
| 🔴 | Document breach notification process | Engineering + Legal | Before go-live |
| 🟠 | Implement automated retention purge job | Engineering | Within 3 months of launch |
| 🟠 | Consider Data Protection Impact Assessment (DPIA) | Legal | Before scaling to >10K users |
| 🟡 | Monitor Data Protection Board for registration requirements | Legal | Ongoing |
| 🟡 | Consider column-level encryption for customer email/phone | Engineering | Before large-scale PII handling |

---

## Disclaimer

This is an internal self-assessment, not a legal opinion. ReturnIQ should engage a
qualified Indian data protection lawyer before launch to validate compliance with the
DPDP Act 2023 and its Rules (when notified).
