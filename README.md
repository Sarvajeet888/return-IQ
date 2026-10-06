# ReturnIQ Enterprise

**Returns intelligence and workflow automation for reverse logistics**

**Kalman Enterprise** · A division of Kalman Consultancy Services
Version 3.0.0 · August 2026

> **Company status:** Kalman Consultancy Services is completing company
> registration in India (Phase 2 of 11 — DSC issuance). The Certificate of
> Incorporation has not yet been issued. Until it is, do not use "Private
> Limited" on external material, print a CIN, or sign contracts in the
> company's name.

---

## What This Is

ReturnIQ Enterprise scores incoming product returns and recommends what to do
with each one — accept, reject, send for manual review, or refund the customer
and let them keep the item. It combines a trained machine learning model for
cost prediction with configurable business rules for fraud and damage risk, and
returns a decision with an explanation in under 100 milliseconds.

**Being precise about the AI:** cost prediction is a genuinely trained XGBoost
model. Fraud scoring, damage assessment, resale estimation, and carbon footprint
are business-rule engines — deterministic calculations, not learned models. See
[AI Transparency](docs/ai/AI_TRANSPARENCY.md).

---

## Quick Start

```bash
cp .env.example .env

# Generate the two required secrets
python3 -c "import secrets; print(secrets.token_hex(64))"   # → SECRET_KEY
python3 -c "import secrets; print(secrets.token_hex(64))"   # → API_KEY_HASH_PEPPER

docker compose up --build
```

Open http://localhost:3000 and register.

Full instructions: [Installation Guide](docs/operations/INSTALLATION.md)

---

## Package Contents

```
returniq-enterprise/
├── backend/          FastAPI · 66 Python files · 93 endpoints · 21 tables
├── frontend/         React 18 + Vite · 14 pages
├── infra/            Docker · nginx · monitoring · logging · backups · Terraform
├── qa/               Test strategy · coverage matrix · QA report · evidence
├── docs/             14 documentation categories
└── .github/          CI/CD pipeline with quality gates
```

---

## Documentation Index

### Product
| Document | Read if you want to |
|---|---|
| [Product Overview](docs/product/PRODUCT_OVERVIEW.md) | Understand what this is and who it's for |
| [Product Claims Audit](docs/product/PRODUCT_CLAIMS_AUDIT.md) | **Read before writing any marketing material** |

### Technical
| Document | Read if you want to |
|---|---|
| [System Architecture](docs/architecture/SYSTEM_ARCHITECTURE.md) | Understand how it fits together, and why |
| [API Reference](docs/api/API_GUIDE.md) | Integrate with it — all 93 endpoints |
| [Developer Guide](docs/developer/DEVELOPER_GUIDE.md) | Contribute code |

### AI / ML
| Document | Read if you want to |
|---|---|
| [Model Card](docs/ai/MODEL_CARD.md) | Evaluate the model rigorously |
| [AI Transparency](docs/ai/AI_TRANSPARENCY.md) | Know what's ML and what's rules |
| [ML Pipeline](docs/ai/ML_PIPELINE.md) | Understand the scoring flow |
| [ML Evaluation Audit](docs/ai/ML_EVALUATION_AUDIT.md) | See why the R² isn't trusted |

### Client
| Document | Read if you want to |
|---|---|
| [User Guide](docs/client/USER_GUIDE.md) | Use the product day to day |
| [Admin Guide](docs/client/ADMIN_GUIDE.md) | Manage users, rules, API keys |
| [Troubleshooting](docs/client/TROUBLESHOOTING.md) | Fix something that broke |

### Operations
| Document | Read if you want to |
|---|---|
| [Installation](docs/operations/INSTALLATION.md) | Get it running |
| [Deployment](docs/operations/DEPLOYMENT.md) | Run it in production |
| [Deployment Runbook](infra/deployment/DEPLOYMENT_RUNBOOK.md) | Do a first production deploy |
| [Rollback Plan](docs/release/ROLLBACK_PLAN.md) | Undo a bad deploy |

### Business
| Document | Read if you want to |
|---|---|
| [Pricing & Services](docs/business/PRICING_AND_SERVICES.md) | Price an engagement |
| [Website & Sales Material](docs/marketing/WEBSITE_AND_SALES.md) | Present or publish |

### Legal & Compliance
[Privacy Policy](docs/legal/PRIVACY_POLICY.md) · [Terms of Service](docs/legal/TERMS_OF_SERVICE.md) · [Cookie Policy](docs/legal/COOKIE_POLICY.md) · [Data Retention](docs/legal/DATA_RETENTION.md)
[DPDP Checklist](docs/compliance/DPDP_CHECKLIST.md) · [Licence Audit](docs/compliance/LICENSE_AUDIT.md) · [Accessibility Audit](docs/compliance/ACCESSIBILITY_AUDIT.md)

### Quality
[Test Strategy](qa/strategy/TEST_STRATEGY.md) · [Coverage Matrix](qa/strategy/TEST_COVERAGE_MATRIX.md) · [QA Summary Report](qa/reports/QA_SUMMARY_REPORT.md)

### Standards
[Kalman Engineering Standards](docs/standards/KALMAN_ENGINEERING_STANDARDS.md) · [Brand Guidelines](docs/brand/BRAND_GUIDELINES.md) · [Security Audit](docs/standards/SECURITY_AUDIT_PHASE6.md)

---

## Verified Facts

Every number below was measured, not estimated.

| | |
|---|---|
| API endpoints | 93 |
| Database tables | 21, across 4 migrations |
| Automated tests | **218, all passing** |
| Backend coverage | **77%** |
| Security penetration tests | **36, all passing** |
| Static analysis (Bandit) | **0 high, 0 medium** across 4,969 lines |
| Lint correctness errors | **0** |
| Scoring latency | Under 100ms |

---

## Honest Limitations

| Limitation | Detail |
|---|---|
| Fraud and damage are rule-based | Not trained models. Real models need labelled outcomes the platform now collects but doesn't yet have |
| Model accuracy unverified | Training-run R² of 0.9993 could not be re-validated — the original dataset isn't in the repo. Don't quote it |
| Frontend has no tests | 0% coverage across 4,013 lines |
| Load test never executed | Capacity limits are unmeasured |
| SMTP not wired | Password reset non-functional in production |
| Customer PII unencrypted at rest | Would fail an enterprise security review |
| No consent capture at registration | DPDP Act gap |
| Not WCAG 2.1 AA certified | Gaps documented in the accessibility audit |
| India-specific | Pincode tiers, couriers, and cost patterns are Indian. Other markets need retraining |

**Not built:** customer-facing return portal · repair workflow · vendor
management · pre-built ERP/WMS connectors · route optimization.

---

## Before Selling This

| # | Blocker | Type |
|---|---|---|
| 1 | Company not incorporated | Legal — cannot contract or invoice |
| 2 | Legal review of ToS and Privacy Policy | Legal |
| 3 | SMTP not wired | Engineering — 2–3 hours |
| 4 | Consent capture at registration | Engineering — 1–2 hours |
| 5 | PII encryption at rest | Engineering — ~1 day |
| 6 | Frontend test coverage | Engineering — 2–3 days |
| 7 | Load test executed | Engineering — 4 hours + a server |

Items 1 and 2 are hard blockers. Items 3–5 could be accepted by a pilot customer
under a written caveat, but not by an enterprise buyer.

---

## Development History

| Phase | Focus | Outcome |
|---|---|---|
| 1 | Audit | Found "5 AI models" was 1 model + 4 rule engines |
| 2 | Bug fixes | Migration race condition, auth duplication |
| 3 | Code quality | DRY helpers, dead code removal |
| 4 | AI/ML | Fixed fake explainability and hardcoded stats; model registry |
| 5 | Enterprise features | 9 route modules, workflow engine, 8 tables |
| 6 | Security | 4 critical fixes, headers, non-root containers |
| 7 | Legal & docs | 20 documents — privacy, ToS, DPDP, API reference |
| 8 | DevOps | CI/CD, Terraform, monitoring, logging, backups |
| 9 | QA | 33 → 218 tests; **7 real bugs found**, including one that would have prevented the app from booting |
| 10 | Packaging | Brand, documentation architecture, business material, Kalman standards |

Full history: [CHANGELOG](docs/release/CHANGELOG.md)

---

## Licence

Proprietary. © Kalman Consultancy Services, 2026.

> **Action required:** a `LICENSE` file does not yet exist in this repository —
> flagged in [Licence Audit](docs/compliance/LICENSE_AUDIT.md). Add one before
> any external distribution.

All third-party dependencies audited: no GPL conflicts, no copyleft obligations.
See [Third-Party Notices](docs/compliance/THIRD_PARTY_NOTICES.md).

---

## Contact

**Om Pilaji** · Director, Kalman Consultancy Services
Hyderabad, Telangana, India

*Precision Data. Optimized Intelligence.*
