# Website Content & Sales Material — ReturnIQ Enterprise

**Draft copy · August 2026 · Classification: Internal**

> **Publishing gate:** do not publish until the Certificate of Incorporation is
> issued. Until then: no "Private Limited", no CIN, no live pricing page, no
> contract signing. All claims below are restricted to the verified feature list
> in `docs/product/PRODUCT_CLAIMS_AUDIT.md`.

---

# PART A — Website Content

## Home

### Hero

**Headline:** Know what a return costs before you accept it.

**Subhead:** ReturnIQ Enterprise scores every return in under 100 milliseconds —
predicted cost, fraud risk, and a routing recommendation you can act on or
override.

**Primary CTA:** Request a demo
**Secondary CTA:** Read the documentation

### The problem — three columns

**Returns cost more than you think.**
A ₹600 item returned from a tier-3 pincode can cost more to retrieve than it's
worth. Most teams find out in the monthly P&L, not at the point of decision.

**Manual review doesn't scale.**
Review every return and you burn staff time. Review none and you lose money.
Most teams settle on an arbitrary value threshold that's neither.

**Decisions aren't consistent.**
Two staff members handle the same return differently, and when a customer
disputes the outcome there's no record of why.

### How it works — four steps

1. **Submit** — through the dashboard, or the REST API from your existing system
2. **Score** — a trained model predicts processing cost; rules assess fraud and
   damage risk
3. **Decide** — accept, reject, manual review, or refund-and-keep, with the
   reasoning shown
4. **Automate** — your rules handle the clear cases; your team handles the rest

### Proof strip

`93 API endpoints` · `218 automated tests` · `36 security tests` ·
`Under 100ms scoring` · `Multi-tenant isolation verified`

### Honesty block — keep this on the page

**What's actually AI, and what isn't**

Cost prediction uses a gradient-boosted model trained on around 80,000
historical returns. Fraud scoring, damage assessment, resale value, and carbon
footprint are business rules — deterministic calculations we wrote, not learned
models.

We're specific about this because plenty of software calls if-statements "AI",
and you deserve to know which is which before you rely on it.

[Read the AI Transparency Statement →]

---

## Features

**Returns intelligence**
ML cost prediction · fraud risk scoring · damage probability · resale estimation ·
carbon footprint · routing recommendation · per-prediction explainability ·
manual override with audit trail

**Workflow automation**
Build rules from conditions your team already understands — risk score, item
value, payment mode, category, courier. Rules evaluate in priority order, the
first match wins, and every firing is logged.

```
Auto-approve low risk
  IF risk_score < 20 AND item_value < ₹500
  THEN approve, notify team

Escalate high-value COD
  IF item_value > ₹20,000 AND payment_mode = COD
  THEN manual review, 12-hour SLA
```

**Operations**
Full return timeline · notes · document upload (damage photos, invoices,
warranties) · bulk import · customer records with history and analytics ·
blacklisting · notifications

**Reporting**
Summary, fraud, carbon, and customer reports with date filtering and CSV export.

**Built for enterprise**
Multi-tenant isolation · four roles · REST API with key auth · OpenAPI 3.0 ·
audit logging on every action · self-hosted or your own cloud

---

## Solutions

**E-commerce brands** — highest return rates, thinnest margins per return
**Retail chains** — omnichannel returns that are hard to reconcile
**3PL providers** — multi-tenancy is built in; manage returns for many merchants
from one instance
**Manufacturers** — warranty and defect pattern analysis

**Best fit:** 500–50,000 returns a month, a small operations team, currently
reviewing manually or by a fixed value rule.

**Not a fit yet:** if you need a customer-facing return portal, repair workflow
management, or a pre-built WMS connector — those aren't built. We'd rather tell
you now than after you've signed.

---

## About Kalman

Kalman Consultancy Services builds software for industries expected to matter
over the next several decades — AI, enterprise platforms, semiconductor tooling,
accessibility, space systems, and financial infrastructure.

The name comes from the Kalman filter: the algorithm that estimates true state
from noisy measurements. It's the right namesake for a company whose products
turn imperfect data into decisions you can rely on.

*Precision Data. Optimized Intelligence.*

**Divisions:** Kalman Enterprise · Kalman AI · Kalman Cloud ·
Kalman Semiconductor · Kalman Space · Kalman Finance

ReturnIQ Enterprise is the first product from Kalman Enterprise.

---

## Copy rules for this site

- Every number must be defensible. If a reader asks "how do you know?", there
  must be an answer.
- **Never publish the R² of 0.9993** — see `PRODUCT_CLAIMS_AUDIT.md`
- **Never claim** route optimization, vendor management, a customer portal, or
  repair workflow. They don't exist.
- Banned words: revolutionary, game-changing, seamless, cutting-edge,
  world-class, leverage (as a verb), disrupt

---

# PART B — Sales Deck (14 slides)

> Read `PRODUCT_CLAIMS_AUDIT.md` before presenting. Four features in the company
> profile don't exist in the product. Claiming them in a room with a technical
> buyer costs you the deal and the relationship.

**Slide 1 — Title**
ReturnIQ Enterprise · Returns intelligence and workflow automation
Kalman Enterprise · Kalman Consultancy Services

> *If the company isn't incorporated yet: say "we're completing registration" if
> asked. Don't volunteer it, don't hide it.*

**Slide 2 — The number that starts the conversation**
Indian e-commerce return rates: 15–30% by category. Among the highest globally.

> *Pause here. Ask what theirs is. Their number is more persuasive than yours,
> and now you're having a conversation instead of presenting.*

**Slide 3 — Where the money goes**
Four costs: reverse logistics you can't see until it's incurred · fraud that's
hard to spot manually · manual review that doesn't scale · inconsistent,
undocumented decisions.

> *Ask which one hurts most. Let them pick your narrative.*

**Slide 4 — What ReturnIQ does**
Scores every return at intake, under 100ms. Returns predicted cost, fraud risk,
damage probability, resale value, carbon footprint, and a routing recommendation
with an explanation.

**Slide 5 — Live demo**

> *This slide is a placeholder — actually demo. Five minutes of working software
> beats twenty slides. Have a seeded instance ready and a fallback video.*

**Slide 6 — What's AI, what isn't**
Cost prediction: trained XGBoost model, ~80,000 records.
Fraud, damage, resale, carbon: business rules, not learned models.

> *This slide wins technical buyers. Everyone else in their evaluation is
> claiming everything is AI. Being the one vendor who separates them is a
> differentiator — and it makes every other claim you make more credible.*
>
> *If asked "why isn't fraud ML?" — because supervised fraud detection needs
> confirmed fraud outcomes, and nobody has those until the system has run long
> enough to collect them. We built the collection mechanism. When you have 200
> confirmed cases, we train on your data.*

**Slide 7 — Workflow automation**
Show a rule. Conditions their ops lead would write. Priority ordering. Audit log.

**Slide 8 — Human stays in control**
Every recommendation can be overridden. Reason is mandatory. Permanently logged.
We recommend routing high-value returns to human review by rule.

**Slide 9 — Enterprise readiness**
Multi-tenant isolation (verified by dedicated tests) · four roles · REST API ·
OpenAPI 3.0 · audit logging · 218 automated tests · 36 security penetration tests ·
0 high/medium static analysis findings

**Slide 10 — Deployment**
Self-hosted on your server, or your AWS account via our Terraform. Your data
never leaves your infrastructure — relevant for DPDP Act compliance.

**Slide 11 — What we haven't built**
No customer-facing portal. No repair workflow. No pre-built ERP connectors.
No route optimization. Fraud and damage are rules, not models.

> *Yes, put this in the deck. Every buyer discovers limitations eventually.
> Discovering them from you builds trust; discovering them after signing
> destroys it.*

**Slide 12 — Pricing**
Starter ₹15,000 · Professional ₹45,000 · Enterprise from ₹1,20,000/month.
Implementation from ₹75,000.

> *Under ~2,000 returns/month the labour-savings case is weak. Lead with
> decision consistency and fraud visibility instead. Don't force an ROI story
> the numbers don't support.*

**Slide 13 — Pilot proposal**
Four weeks. Your historical data. We measure how many returns would have been
auto-decided, and how many were uneconomic to accept. You keep the analysis
either way.

> *This is the actual ask. The pilot produces the ROI number — you don't have to
> assert one.*

**Slide 14 — Next steps**
Technical deep-dive with their engineering team · pilot scoping · security review

---

## Objection Handling

**"How accurate is the model?"**
Honestly: we have a training-run metric we don't consider verified, because the
original dataset isn't available to re-check it and the number is high enough to
warrant suspicion. We'd rather measure it on your data during the pilot than
quote you something we can't defend.

*(This answer builds more trust than a number would. It also happens to be true.)*

**"Your competitor says they have AI fraud detection."**
Ask them what it's trained on, and how they obtained labelled fraud outcomes.
Most "AI fraud detection" in this category is rules. We just say so.

**"You're a new company."**
True. We're completing registration. What we can show you is the engineering:
218 tests, documented architecture, a security audit, full legal documentation.
Judge the work.

**"What if you shut down?"**
Self-hosted deployment on your infrastructure, perpetual licence available, your
data sits in your own Postgres.

**"Can it integrate with our ERP?"**
Via REST API — 93 documented endpoints with an OpenAPI spec. No pre-built
connector exists; integration development is a scoped service.

---

# PART C — One-Pager

**ReturnIQ Enterprise**
*Returns intelligence and workflow automation*

**The problem:** Indian e-commerce return rates run 15–30%. Processing cost often
exceeds item value, fraud is hard to spot manually, and manual review doesn't scale.

**What it does:** Scores every return at intake in under 100ms — predicted cost
(trained ML model), fraud and damage risk (business rules), resale value, carbon
footprint, and a routing recommendation with an explanation.

**Automation:** Configurable rules auto-approve, auto-reject, or escalate. SLA
tracking with breach detection. Every decision logged and overridable.

**Enterprise:** Multi-tenant · 4 roles · REST API · OpenAPI 3.0 · audit logging ·
self-hosted or your cloud.

**Verified:** 218 automated tests · 36 security penetration tests · 0 high/medium
static analysis findings · 93 documented endpoints.

**Honest about limits:** Fraud and damage scoring are rules, not trained models.
No customer portal, repair workflow, or pre-built ERP connectors yet.

**Pricing:** From ₹15,000/month. Implementation from ₹75,000.

**Contact:** Om Pilaji · Director · Kalman Consultancy Services
