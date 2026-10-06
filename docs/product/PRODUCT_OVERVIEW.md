# ReturnIQ Enterprise — Product Overview

**Kalman Enterprise Division · Kalman Consultancy Services**
Version 3.0.0 · August 2026 · Classification: Public

> **Status note:** Kalman Consultancy Services is currently completing company
> registration in India. Until the Certificate of Incorporation is issued, this
> document is provided for evaluation purposes and does not constitute a
> commercial offer.

---

## Executive Summary

Every returned product costs money to process, and most of that cost is decided
in the first few minutes — before anyone has looked at the item. Accept a return
that costs more to ship back than the item is worth, and you lose twice. Reject a
legitimate one, and you lose the customer.

ReturnIQ Enterprise scores each return the moment it is submitted and recommends
what to do with it: accept, reject, send for manual review, or refund the
customer and let them keep the item. It combines a trained machine learning model
for cost prediction with configurable business rules for fraud and damage risk,
and returns a decision with an explanation in under 100 milliseconds.

Teams use it to stop reviewing every return by hand, and to stop guessing which
ones deserve attention.

---

## The Problem

Indian e-commerce return rates run between 15% and 30% depending on category —
among the highest globally, driven by cash-on-delivery, size uncertainty in
apparel, and a well-established culture of try-before-you-keep.

For a merchant processing meaningful volume, this creates four costs:

**1. Reverse logistics cost is often invisible until it's incurred.**
A ₹600 kurta returned from a tier-3 pincode to a Mumbai warehouse can cost more
in courier charges, handling, and quality inspection than the item is worth. Most
merchants discover this in the monthly P&L, not at the point of decision.

**2. Return fraud is real and hard to spot manually.**
Wardrobing, empty-box returns, and swap fraud are widespread. Detecting them
requires cross-referencing customer history, item value, reason code, and payment
mode — which nobody does consistently at volume.

**3. Manual review does not scale.**
Reviewing every return costs staff time. Reviewing none costs money. Most teams
land on an arbitrary value threshold that is neither.

**4. Decisions are inconsistent and undocumented.**
Two staff members handle the same return differently. When a customer disputes
an outcome, there is no record of why the decision was made.

---

## What ReturnIQ Does

### Scores every return automatically

A return is submitted through the UI or the API. Within 100ms, ReturnIQ returns:

| Output | What it is |
|---|---|
| **Predicted processing cost** | XGBoost model trained on ~80,000 historical returns |
| **Fraud risk score (0–100)** | Rule-based, weighted across customer history, reason code, payment mode, item value |
| **Damage probability** | Rule-based assessment from declared condition and item characteristics |
| **Resale value estimate** | Category-adjusted depreciation formula |
| **Carbon footprint estimate** | Per-courier emission factors × chargeable weight × distance |
| **Routing recommendation** | accept · reject · manual_review · refund_and_keep |
| **Explanation** | The feature that drove the cost prediction most, and why |

**Being precise about the AI:** cost prediction is a genuinely trained ML model.
Fraud scoring, damage assessment, resale, and carbon are business-rule engines —
deterministic calculations, not learned models. This is stated plainly in
`docs/ai/AI_TRANSPARENCY.md` and in the product UI. The infrastructure to train
real fraud and damage models exists and activates once enough confirmed outcomes
are collected.

### Automates the decisions that don't need a human

Rules are configured by the merchant, not hard-coded:

```
Rule: Auto-approve low risk
  Conditions: risk_score < 20 AND item_value < ₹500
  Action:     status → approved, notify team
  Priority:   1

Rule: Escalate high-value COD
  Conditions: item_value > ₹20,000 AND payment_mode = COD
  Action:     status → manual_review, SLA 12 hours
  Priority:   2
```

Rules evaluate in priority order; the first match wins. Every rule firing is
logged.

### Keeps a human in control

Any recommendation can be overridden by an analyst or admin. The override
requires a written reason and is permanently recorded in the return's timeline.
We recommend routing high-value returns to manual review by rule rather than
auto-deciding them — the platform is built to support that, not replace it.

### Tracks the whole lifecycle

Timeline view per return: creation, prediction, notes, document uploads, status
changes, SLA deadline, overrides. Damage photos, invoices, and warranty documents
attach directly to the return.

---

## Who It's For

| Segment | Why |
|---|---|
| **E-commerce brands** (D2C, marketplace sellers) | Highest return rates; thinnest margins per return |
| **Retail chains** with online channels | Omnichannel returns are hard to reconcile |
| **3PL / logistics providers** | Manage returns on behalf of multiple merchants — multi-tenancy is built in |
| **Manufacturers** taking direct returns | Warranty and defect analysis |

**Best fit:** an organisation processing 500–50,000 returns a month, with a small
operations team, that currently reviews returns manually or by a fixed value rule.

**Poor fit today:** organisations needing a customer-facing return portal, repair
workflow management, or WMS integration. Those are not built — see the roadmap.

---

## What's Included

### Returns intelligence
ML cost prediction · fraud risk scoring · damage assessment · resale estimation ·
carbon footprint · routing recommendation · per-prediction explainability ·
manual override with audit trail · prediction history

### Workflow automation
Rule builder with multi-condition logic · auto-approve / auto-reject / escalate ·
priority-ordered evaluation · SLA deadline tracking · breach detection

### Operations
Return lifecycle and timeline · notes · document upload (images, PDF, 10MB) ·
bulk import up to 50 per request · customer records with history and analytics ·
customer blacklisting · in-app notifications

### Reporting
Summary, fraud, carbon, and customer reports · date-range filtering · CSV export

### Platform
Multi-tenant isolation · four roles (viewer, analyst, org_admin, super_admin) ·
REST API with API-key auth · OpenAPI 3.0 spec · audit logging · admin panel

---

## Technical Profile

| | |
|---|---|
| Backend | Python 3.11, FastAPI, PostgreSQL 16, Redis 7 |
| Frontend | React 18, Vite |
| ML | XGBoost, scikit-learn preprocessing pipeline |
| Deployment | Docker Compose, or AWS via included Terraform |
| API | REST, 93 endpoints, OpenAPI 3.0 |
| Auth | JWT (15-min access, rotating refresh) + API keys for integrations |
| Prediction latency | Under 100ms typical |
| Test suite | 218 automated tests, 77% backend coverage |
| Security | 36 executable penetration tests; 0 high/medium Bandit findings |

**Minimum production server:** 4 vCPU, 8GB RAM, 50GB SSD, Ubuntu 22.04.

---

## Deployment Models

| Model | Description | Status |
|---|---|---|
| **Self-hosted (Docker)** | Runs on the client's own server or VPS. Full data residency. | ✅ Available |
| **Client cloud (AWS)** | Deployed into the client's AWS account via included Terraform | ✅ Available |
| **Kalman-managed** | Kalman hosts and operates the instance | 🗺️ Planned |
| **Multi-tenant SaaS** | Shared public instance | 🗺️ Planned |

Self-hosted deployment means customer data never leaves the client's
infrastructure — relevant for DPDP Act compliance and for enterprises with data
residency requirements.

---

## Honest Limitations

Stated openly because a customer will find these anyway, and finding them after
signing is worse for everyone.

| Limitation | Detail |
|---|---|
| Fraud and damage are rule-based | Not trained ML models. Real models require labelled outcome data the platform now collects but does not yet have |
| Model accuracy unverified in production | The training-run R² has not been validated against production data. Do not treat it as a guarantee |
| Email requires configuration | SMTP must be configured for password reset to work |
| No customer-facing portal | The application is merchant-facing only |
| No route optimization | Distance is a heuristic input to cost prediction, not a routing engine |
| No WMS/ERP connectors | Integration is via REST API; no pre-built connectors yet |
| Accessibility not certified | WCAG 2.1 AA gaps documented and being addressed |
| Trained on Indian logistics data | Pincode tiers, couriers, and cost patterns are India-specific. Other markets would need retraining |

---

## Roadmap

| Horizon | Items |
|---|---|
| **Next** | SMTP integration · consent capture at registration · PII encryption at rest · frontend test coverage |
| **Then** | S3 document storage · webhooks · ML fraud model (once 200+ labelled outcomes exist) · WCAG AA remediation |
| **Later** | Customer return portal · vendor management · repair workflow · pre-built ERP connectors · route optimization |

Roadmap items are commitments of intent, not delivery dates. Dates are agreed
per engagement.

---

## Why Kalman

Kalman Consultancy Services builds software for industries expected to matter
over the next several decades — AI, enterprise platforms, semiconductor tooling,
accessibility, space systems, and financial infrastructure.

ReturnIQ Enterprise is the first product from the Kalman Enterprise division and
the most mature in the portfolio. The engineering standards it was built to —
documented architecture, executable security tests, legal and compliance
documentation, infrastructure as code — are the standards every Kalman product
follows.

**Contact:** Om Pilaji · Director, Kalman Consultancy Services
