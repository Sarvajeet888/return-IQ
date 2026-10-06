# Product Claims Accuracy Audit

**Prepared for:** Om Pilaji, Sarvajeet Bajikar — Directors, Kalman Consultancy Services
**Date:** August 2026
**Status:** ⚠️ **Read this before publishing any marketing or sales material**

---

## Why this document exists

Phase 10 produces sales decks, brochures, and a website. Those documents make
claims to real customers. Before writing any of them, the claims already made
in the Kalman company documents were checked against the actual ReturnIQ
codebase.

**Four claimed features do not exist in the product.** Publishing them would be
inaccurate to customers, and — once the company is incorporated and selling —
could expose Kalman to a misrepresentation claim.

This is the same class of problem caught in Phase 1 ("5 AI models" when there
was one), and it is being handled the same way: state what is true, remove what
is not, and keep a roadmap for what is planned.

---

## Audit Results

The Kalman Company Profile lists these features under "Reverse Logistics
Platform (Kalman Enterprise)". Each was checked against the codebase.

| Claimed feature | In the code? | Evidence |
|---|---|---|
| Return management | ✅ **Yes** | `routes/returns.py`, `return_mgmt.py` — 93 endpoints |
| Analytics dashboards | ✅ **Yes** | `routes/reports.py`, frontend `Analytics.jsx`, `Dashboard.jsx` |
| Enterprise reporting | ✅ **Yes** | Summary / fraud / carbon / customer reports, CSV export |
| Inventory analytics | 🟡 **Partial** | Return-level analytics exist; no stock/inventory tracking |
| Warehouse tracking | 🟡 **Partial** | Warehouse entity and page exist; no live tracking or WMS integration |
| Vendor management | ❌ **No** | One passing mention. No vendor entity, endpoints, or UI |
| **AI-powered route optimization** | ❌ **No** | **Zero occurrences in the entire backend.** No routing algorithm, no distance optimization, no carrier selection logic |
| Customer return portal | ❌ **No** | No customer-facing UI exists. The app is merchant-facing only |
| Repairs | ❌ **No** | No repair workflow, entity, or endpoint |
| Recycling / refurbishment | ❌ **No** | Mentioned only as a routing decision label; no workflow behind it |

---

## The one that matters most

**"AI-powered route optimization" appears nowhere in the codebase.**

This is the claim most likely to be repeated in a sales conversation, because
it sounds impressive. It is also completely absent. There is no routing
algorithm, no carrier-selection optimizer, and no distance minimization.

What the product *does* have is a **distance estimate** used as one input
feature to the cost prediction model — and that estimate is itself a
heuristic based on pincode tiers, not real geographic routing. Describing that
as "AI-powered route optimization" would be a significant overstatement.

---

## What ReturnIQ Enterprise Actually Is

Stated accurately, for use in all Phase 10 documents:

> ReturnIQ Enterprise is a returns intelligence and workflow automation platform.
> It scores incoming return requests using a trained machine learning model for
> cost prediction, combined with configurable business rules for fraud risk and
> damage assessment, and recommends a routing decision — accept, reject, manual
> review, or refund-and-keep. It provides workflow automation, SLA tracking,
> customer management, reporting, and a REST API for ERP integration.

That is a genuinely useful product. It does not need embellishment.

---

## Corrected Feature List (approved for external use)

### ✅ Verified — safe to claim

**Returns Intelligence**
- ML-based return cost prediction (XGBoost, trained on ~80,000 historical returns)
- Rule-based fraud risk scoring
- Rule-based damage probability assessment
- Resale value estimation
- Carbon footprint estimation
- Automated routing recommendation with confidence score
- Per-prediction explainability (feature importance ranking)
- Manual override with mandatory reason and audit trail

**Workflow Automation**
- Configurable auto-approve / auto-reject / escalate rules
- Multi-condition rule builder
- Priority-ordered rule evaluation
- SLA deadline tracking and breach detection

**Operations**
- Return lifecycle management with full timeline
- Document upload (damage photos, invoices, warranties)
- Bulk import (up to 50 returns per request)
- Customer records, history, analytics, and blacklisting
- In-app notifications

**Reporting**
- Summary, fraud, carbon, and customer reports
- CSV export
- Date-range filtering

**Platform**
- Multi-tenant organisation isolation (verified by 8 dedicated tests)
- Role-based access control — viewer / analyst / org_admin / super_admin
- REST API with API-key authentication for ERP integration
- OpenAPI 3.0 specification
- Audit logging on every significant action

### 🗺️ Roadmap — describe as planned, never as available

| Feature | Honest status |
|---|---|
| Route optimization | Not started. No design work done |
| Vendor management | Not started |
| Customer-facing return portal | Not started |
| Repair workflow | Not started |
| Live warehouse / WMS integration | Not started |
| Inventory stock tracking | Not started |
| ML-based fraud model | Blocked — needs 200+ labelled outcomes (capture mechanism is built) |
| ML-based damage model | Blocked — same reason |

---

## Two further accuracy items

### 1. The company is not yet incorporated

Per the CA Brief, Kalman Consultancy Services Private Limited is at **Phase 2
of 11** in registration. The Certificate of Incorporation has not been issued.

**Therefore, until the COI is received:**
- Do not use "Private Limited" or "Pvt. Ltd." on customer-facing material
- Do not print a CIN (none exists yet)
- Do not sign contracts in the company's name — the entity does not legally exist
- Use "Kalman Consultancy Services" without the suffix, or mark material as
  internal/draft

All Phase 10 documents are written accordingly and carry a status line noting
this. They can be updated the moment the COI arrives.

### 2. The R² figure should not be quoted

The model metadata reports R² = 0.9993. As documented in
`docs/ai/ML_EVALUATION_AUDIT.md`, that number came from a single training run
with no confirmed train/test split or cross-validation, and the original
dataset is no longer in the repository, so it cannot be re-verified.

**Do not put 99.93% accuracy on a sales deck.** An unusually high R² invites
technical scrutiny, and it would not survive it. Describe the model
qualitatively until real production accuracy is measured from outcome labels.

---

## Recommendation to the Directors

Update the Company Profile PDF's "Reverse Logistics Platform" section to match
the verified list above before it goes to any external party — including the CA,
investors, or university evaluators.

The corrected description is still a strong product. A working multi-tenant
enterprise platform with a real trained model, 218 passing tests, and full legal
documentation is a genuinely impressive thing for a company at this stage. It
does not need features it doesn't have.
