# Pricing Model & Service Catalog — ReturnIQ Enterprise

**Kalman Consultancy Services · August 2026 · Classification: Internal**

> **Directors' note:** these are proposed structures for discussion, not
> published prices. Kalman has no customers yet, so every number here is an
> estimate based on comparable Indian B2B SaaS, not on observed willingness to
> pay. Treat the first three engagements as price discovery — the goal is a
> reference customer and a case study, not margin.

---

## Pricing Philosophy

**Price on value delivered, not on cost to build.** The cost to run one more
tenant is near zero; the value is the operations headcount and the wrongly
approved returns avoided.

**Be transparent.** Published pricing builds trust with the mid-market buyers
this product fits. "Contact us for pricing" signals that the price depends on
how much they can pay.

**Don't price on returns volume alone.** A merchant's return count is outside
their control and rises in bad months. Charging more when their business is
struggling creates resentment. Tier on capability, with volume as a soft band.

---

## Proposed Tiers

### Starter — ₹15,000/month
For merchants processing up to 1,000 returns/month.

- Up to 1,000 scored returns/month
- 3 user seats
- ML cost prediction, fraud and damage scoring
- Up to 5 workflow rules
- Standard reports and CSV export
- Email support, 2 business day response
- Self-hosted or Kalman-deployed

### Professional — ₹45,000/month
For merchants processing up to 10,000 returns/month.

- Up to 10,000 scored returns/month
- 15 user seats
- Everything in Starter, plus:
- Unlimited workflow rules
- SLA tracking and breach alerts
- Full REST API access
- Customer analytics and blacklisting
- Priority email support, 1 business day response
- Quarterly review call

### Enterprise — from ₹1,20,000/month
For high-volume merchants, 3PLs, and multi-brand groups.

- Unlimited returns
- Unlimited seats
- Everything in Professional, plus:
- Multi-organisation management (3PL use case)
- Dedicated deployment in the client's cloud
- Custom workflow rule development
- Named technical contact
- 4-hour response for critical issues
- Annual model retraining on the client's own data (once outcome labels exist)
- Custom report development

### Perpetual Licence — ₹8,00,000 one-time + ₹1,60,000/year support
For organisations that cannot use subscription software (government, some
enterprises, air-gapped environments).

Source-available, deployed on client infrastructure, 20% annual support and
update fee.

---

## Implementation Services

Software alone rarely succeeds. These are the services that make it land.

| Package | Scope | Price | Duration |
|---|---|---|---|
| **Quick Start** | Deployment, config, admin training (2h), go-live support | ₹75,000 | 1 week |
| **Standard Implementation** | Quick Start + data migration, 5 workflow rules configured, API integration support, 8h training | ₹2,50,000 | 3–4 weeks |
| **Enterprise Implementation** | Standard + custom integration development, model evaluation on client data, phased rollout, 16h training, 30-day hypercare | ₹6,00,000+ | 6–10 weeks |

### Add-on services

| Service | Price |
|---|---|
| Additional training day (up to 12 attendees) | ₹25,000 |
| Custom report development | ₹40,000 per report |
| Custom workflow rule design workshop | ₹50,000 |
| ERP/WMS integration development | ₹1,50,000+ (scoped) |
| Model retraining on client data | ₹2,00,000 (requires 200+ labelled outcomes) |
| Annual security review | ₹75,000 |

---

## ROI Framework

**Do not present ROI as a promise.** Present it as a calculation the client
fills in with their own numbers. The credibility comes from them doing the
arithmetic, not from Kalman asserting a multiple.

### The three levers

**1. Reduced manual review time**

```
Returns/month × % currently reviewed manually × minutes per review
  ÷ 60 × loaded hourly cost = current monthly review cost

Automation typically removes review for low-risk returns.
The realistic reduction depends entirely on the client's risk
appetite — a conservative client may automate 20%, an aggressive
one 60%. Model both.
```

**2. Avoided uneconomic returns**

The refund-and-keep recommendation prevents shipping items back that cost more
to retrieve than they're worth.

```
Returns where predicted_cost > item_value × recovery_rate
  × average net loss per such return = avoidable monthly loss
```

ReturnIQ surfaces exactly this set. Run it on the client's historical data
during a pilot and count.

**3. Fraud caught earlier**

Be careful here. The fraud scoring is rule-based, and its real-world precision
is unmeasured. **Do not quantify fraud savings in a proposal.** Describe it as
a risk-flagging capability and let the pilot produce the number.

### Worked example — use as a template, not a claim

A merchant with 5,000 returns/month, reviewing 100% manually at 4 minutes each,
loaded cost ₹400/hour:

| | |
|---|---|
| Current review cost | 5,000 × 4 ÷ 60 × ₹400 = **₹1,33,000/month** |
| If 40% become auto-decided | Saving ≈ **₹53,000/month** |
| Professional tier | −₹45,000/month |
| **Net** | **≈ ₹8,000/month, plus avoided uneconomic returns** |

**Read that honestly:** at 5,000 returns/month the subscription roughly pays for
itself on review time alone, and the actual return comes from the second lever.
At 1,000 returns/month, Starter tier is harder to justify on labour savings
alone — the pitch there is decision consistency and fraud visibility, not
headcount.

That is a real limitation of the pricing at the low end and worth knowing before
a sales call, rather than discovering it mid-negotiation.

---

## Discounting Guidance

| Situation | Guidance |
|---|---|
| First 3 customers | Up to 50% off for 12 months in exchange for a written case study and a reference call |
| Annual prepay | 15% discount |
| Non-profit / educational | 40% discount |
| Multi-year (2yr) | 20% discount, price locked |
| Competitive displacement | Match the remaining term of their existing contract free |

**Never discount implementation services below cost.** Free implementation
signals the work is trivial, and it is the part most likely to determine whether
the client succeeds.

---

## Statement of Work — Template Structure

Every engagement gets an SoW containing:

1. **Parties and effective date**
2. **Scope** — what is being delivered, itemised
3. **Explicitly out of scope** — the most important section. List what is *not*
   included, especially the roadmap items (route optimization, customer portal,
   ERP connectors) that a client may have assumed
4. **Deliverables and acceptance criteria** — how "done" is judged
5. **Timeline and milestones**
6. **Client responsibilities** — server access, data export, staff availability,
   named point of contact. Most delays are client-side; name them upfront
7. **Fees and payment schedule** — typically 40% on signing, 40% on go-live,
   20% on acceptance
8. **Change control** — how scope changes are priced and approved
9. **Support terms post-go-live**
10. **Limitation of liability** — mirrors the Terms of Service cap
11. **Data protection** — DPDP Act obligations, who is controller vs processor

**Non-negotiable clause for every SoW:**

> ReturnIQ Enterprise produces routing *recommendations*. The Client remains
> solely responsible for all return-handling decisions. The Client shall
> maintain human review for high-value returns and for any case where a
> recommendation would result in denial of a customer claim.

This protects both parties and is consistent with the Terms of Service and
AI Transparency Statement.

---

## Service Catalog Summary

| Category | Offering |
|---|---|
| **Software** | Starter · Professional · Enterprise · Perpetual Licence |
| **Implementation** | Quick Start · Standard · Enterprise |
| **Training** | Administrator · Operator · Developer / API |
| **Support** | Standard (2 day) · Priority (1 day) · Enterprise (4 hour) |
| **Consulting** | Returns process assessment · Workflow rule design · Custom integration · Model evaluation |

---

## What to Fix Before Selling

| # | Blocker | Why it blocks a paid engagement |
|---|---|---|
| 1 | Company not incorporated | Cannot legally contract or invoice |
| 2 | SMTP not wired | Password reset doesn't work — a support burden from day one |
| 3 | No consent capture at registration | DPDP Act exposure with real customer data |
| 4 | PII stored in plaintext | Would fail any enterprise security review |
| 5 | Legal review of ToS and Privacy Policy not done | Contracts would rest on unreviewed terms |
| 6 | No load test executed | Cannot state capacity limits in an SoW |

Items 1 and 5 are hard blockers. Items 2–4 could be accepted by a pilot customer
under a written caveat, but not by an enterprise buyer.
