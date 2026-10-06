# Brand Guidelines — Kalman Consultancy Services

**Version 1.0 · August 2026**
**Status:** Company registration in progress (Phase 2 of 11). Do not use "Private
Limited" on external material until the Certificate of Incorporation is issued.

---

## 1. Brand Architecture

```
Kalman Consultancy Services                    ← Company
        │
        ├── Kalman Enterprise                  ← Division
        │       └── ReturnIQ Enterprise        ← Product
        │
        ├── Kalman AI
        │       ├── Gaze Glide
        │       └── Multi-Agent Simulation
        │
        ├── Kalman Cloud
        │       └── Portfolio Builder
        │
        ├── Kalman Semiconductor
        │       ├── Chip Design Assistant
        │       ├── AI RTL Bug Finder
        │       └── Chip Verification Automation
        │
        ├── Kalman Space
        │       └── Space Software Platform
        │
        └── Kalman Finance
                └── Financial Infrastructure Platform
```

**Naming rule:** `Kalman [Division]` for divisions. Products get their own name
without the Kalman prefix (ReturnIQ, Gaze Glide) — this lets a product build its
own recognition while the division provides credibility.

**Always write:** "ReturnIQ Enterprise, a Kalman Enterprise product"
**Never write:** "Kalman ReturnIQ" or "ReturnIQ by Kalman AI" (wrong division)

---

## 2. The Name

**Kalman** — after the Kalman filter, the algorithm that estimates true state
from noisy measurements. It is the right namesake for a company whose products
turn imperfect data into reliable decisions, and it is literally used in Gaze
Glide.

**Tagline:** *Precision Data. Optimized Intelligence.*

Use the tagline under the logo, on the first slide of a deck, and in email
signatures. Do not use it mid-sentence in body copy.

**ReturnIQ** — "Return" (the domain) + "IQ" (intelligence applied to it).
**Enterprise** — the tier. It signals multi-tenant, RBAC, audit logging, and API
access, and leaves room for a future Starter or Cloud tier.

---

## 3. Colour System

### Primary

| Role | Hex | Use |
|---|---|---|
| Kalman Indigo | `#4F46E5` | Primary brand colour, CTAs, links, active states |
| Indigo Light | `#818CF8` | Hover states, accents on dark backgrounds |
| Indigo Subtle | `#EEF2FF` | Tinted backgrounds, selected rows |

### Neutrals

| Role | Hex | Use |
|---|---|---|
| Ink | `#0F172A` | Headings, primary text on light |
| Slate | `#475569` | Body text, secondary information |
| Muted | `#94A3B8` | Labels, captions, disabled states |
| Border | `#E2E8F0` | Dividers, input borders |
| Surface | `#FFFFFF` | Cards, panels |
| Canvas | `#F8FAFC` | Page background |

### Semantic

| Role | Hex | Meaning in ReturnIQ |
|---|---|---|
| Success | `#16A34A` | Accept routing decision, healthy status, SLA met |
| Warning | `#D97706` | Manual review, degraded state, approaching SLA |
| Danger | `#DC2626` | Reject decision, high fraud score, SLA breach |
| Info | `#0284C7` | Refund-and-keep, neutral notifications |

**Rule:** semantic colours carry meaning. Never use Danger red as a decorative
accent — in this product, red means a return was rejected or an SLA broke.

### Accessibility

All text/background pairs above meet WCAG AA (4.5:1) except `Muted` on
`Canvas`, which is 3.9:1. **Use Muted only for non-essential text** (captions,
timestamps), never for information the user needs. See
`docs/compliance/ACCESSIBILITY_AUDIT.md`.

---

## 4. Typography

| Role | Font | Weight | Size |
|---|---|---|---|
| Display | Inter | 600 | 32–48px |
| Heading 1 | Inter | 600 | 24px |
| Heading 2 | Inter | 600 | 18px |
| Body | Inter | 400 | 14–16px |
| Label | Inter | 500 | 11–12px, uppercase, 0.05em tracking |
| Code / Data | JetBrains Mono | 400 | 13px |

**Fallback stack:**
`Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`

Inter is open source (SIL Open Font License) — free for commercial use, no
attribution required in the UI. JetBrains Mono is Apache 2.0.

**Rule:** monospace for anything a user might copy — IDs, API keys, pincodes,
SKUs, currency amounts in tables. It makes transcription errors visible.

---

## 5. Logo Usage

The mark is not yet designed. When it is, these rules apply:

| Rule | Specification |
|---|---|
| Clear space | Minimum 1× the logo height on all sides |
| Minimum size | 24px height digital, 15mm print |
| Backgrounds | Full colour on light; white/reversed on Kalman Indigo or Ink |
| Never | Stretch, rotate, recolour, add effects, or place on a busy photo |
| File formats | SVG for digital, PDF vector for print, PNG @1x/@2x/@3x fallback |

**Product lockup:** when ReturnIQ appears with the Kalman mark, the Kalman mark
leads and ReturnIQ sits to the right, separated by a vertical rule at 60% opacity.

---

## 6. Voice and Tone

Kalman writes like an engineer explaining something to a colleague they respect.

### Principles

**Be precise.** "Scores returns in under 100ms" beats "lightning-fast
performance." Numbers you can defend beat adjectives you can't.

**Be honest about limits.** If the fraud scoring is rule-based, say so. The
credibility gained is worth more than the feature bullet lost. This is a
company value, not just a style preference — see `PRODUCT_CLAIMS_AUDIT.md`.

**Explain, don't impress.** The reader is a logistics manager or a CTO. They
have been sold to before. Clear beats clever.

**Respect the reader's time.** Lead with the answer. Put the caveat after.

### Words we use

| Use | Not |
|---|---|
| "recommends a routing decision" | "decides automatically" |
| "estimated" (for cost, carbon, resale) | "calculated exactly" |
| "rule-based fraud scoring" | "AI fraud detection" |
| "trained model" | "advanced AI" |
| "reduces manual review time" | "revolutionizes returns" |
| "in under 100ms" | "blazing fast" |

### Words we avoid entirely

*Revolutionary, game-changing, cutting-edge, seamless, robust, world-class,
best-in-class, leverage (as a verb), synergy, disrupt.*

They appear in every competitor's deck. Using them makes Kalman sound like
everyone else, and they carry no information.

### Tone by context

| Context | Tone |
|---|---|
| Product docs | Neutral, instructional, second person ("you") |
| Sales material | Confident, specific, evidence-led |
| Error messages | Plain, blameless, actionable — "That pincode needs 6 digits", not "Invalid input" |
| Incident comms | Direct, factual, no minimising. State impact, cause, and fix |
| API docs | Terse, example-first |

---

## 7. Writing Rules

- **Indian numbering for currency:** ₹1,00,000 not ₹100,000
- **Dates:** 4 August 2026 (never 04/08/26 — ambiguous internationally)
- **Time:** 24-hour with timezone — 14:30 IST
- **Product name:** always "ReturnIQ Enterprise" on first mention; "ReturnIQ"
  acceptable thereafter
- **Sentence case for headings**, not Title Case
- **Oxford comma:** yes
- **Never** hyphenate "ecommerce" (write "e-commerce")

---

## 8. Document Standards

Every Kalman external document carries:

```
[Kalman mark]                    Kalman Consultancy Services
                                 Precision Data. Optimized Intelligence.

Document title
Product · Version · Date · Classification (Public / Confidential / Internal)
```

Footer: `Kalman Consultancy Services · [Document Title] · Page N of M`

**Classification:**
- **Public** — website, brochures, published docs
- **Confidential** — shared with a named client under NDA
- **Internal** — never leaves the company
