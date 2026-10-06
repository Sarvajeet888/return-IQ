# RETURNIQ_BASELINE.md

**Audit date:** 13 August 2026
**Artefact audited:** `returniq_finalfrontend.zip` → `returniq_enterprise_FINAL/`
**Method:** static analysis of source code. Claims in the repo's 65 markdown files were *not* trusted; every finding below is traced to a file and line.

---

## 1. What is actually here

| Layer | Measured |
|---|---|
| Backend Python | 84 files, 12,745 lines |
| Frontend source | 31 files, 5,887 lines |
| Frontend pages | 14 |
| Alembic migrations | 7 |
| Backend test files | 5 named + `integration/` + `security/` dirs |
| Frontend test files | **0** |
| Documentation | 65 `.md` files |
| ML artefacts | `model.joblib` (1.5 MB), `preprocessor.joblib` |
| Training data | 5,000 rows, synthetic |

Backend layering is genuinely reasonable: `api/v1/routes` → `services` → `db/store` with `core` for config, security, cache, metrics, encryption. This is not a beginner structure. Whoever built this understood separation of concerns.

---

## 2. Findings, by severity

### BLOCKER-1 — The ML model cannot be trusted with real customer money

`data/DATASET_ASSESSMENT.md` (written during a previous session, and correct) establishes:

- The deployed cost model needs **15 features**. The available dataset has **2 of them**.
- There is **no cost target column at all** in the dataset.
- The `R² = 0.9993` recorded in `model_metadata.json` is therefore **unverifiable**.
- The training data is **synthetic** — generated, not observed.

The dataset even contains `approval_probability_true` and `fraud_risk_true` columns. Those are the generator's own ground-truth parameters. A model trained on a synthetic set whose labels were *derived from* those parameters will score beautifully and mean nothing.

**Why this is the top blocker for a real-customer launch:** the entire value proposition — Phase 24's "Repair ₹1,550 vs Restock ₹1,050, recommendation: Repair" — is arithmetic on numbers this model produces. If those numbers are fiction, ReturnIQ confidently tells a merchant to scrap a repairable item, or to restock a fraudulent return. That is worse for them than having no software.

### BLOCKER-2 — Money is stored as floating-point

`backend/app/db/models.py` — 20+ columns use `Float`:

```
line  91: item_value              Float
line 119: predicted_cost_inr      Float
line 123: resale_value_estimate   Float
line 164: actual_cost_inr         Float
line 466: remitted_amount         Float
line 467: expected_amount         Float
```

Floating-point cannot represent 0.1 exactly. Summing thousands of refunds accumulates drift. For a remittance-reconciliation feature — which `remittance_service.py` is — this eventually produces a number that doesn't match the courier's number, and no one can explain why.

Your own roadmap flags this at Phase 3. It is still unfixed.

**Secondary issue:** currency is baked into *column names* (`predicted_cost_inr`, `actual_cost_inr`). Phase 43 (globalisation) cannot be done without a migration touching every one of these.

### HIGH-1 — Tenant isolation is enforced in only one layer

15 query functions in `db/store.py` accept an ID and filter by **nothing else**:

`get_prediction`, `get_return_notes`, `get_return_documents`, `get_sla_for_return`, `get_predictions_for_returns`, `get_consent_history`, `has_valid_consent`, and 8 others.

**Good news, and I want to be accurate here:** I traced every call site. All of them are currently guarded — routes call `_get_owned_return_or_404(return_id, org)` first, and `ai_ux.py` does its own inline org check at lines 88 and 155. **There is no live cross-tenant leak today.**

**The risk is structural.** Isolation depends on every developer remembering the guard on every future route. One forgotten line in one new endpoint = one org reading another org's fraud scores. Phase 4 asks for automated isolation tests in CI; there are none.

### HIGH-2 — Zero frontend tests, zero E2E tests

`frontend/package.json` has no Vitest, no React Testing Library, no Playwright. Scripts are `dev`, `build`, `preview` only. 5,887 lines of UI that decides whether a return gets approved, with no automated verification.

### MEDIUM-1 — No accessibility affordances in the component library

`frontend/src/components/ui/index.jsx` contains **0** `aria-` attributes. Phase 11 and Phase 48 target WCAG 2.2 AA. Current state is far from it.

### MEDIUM-2 — HTML email built by string formatting

`email_service.py` lines 141 and 168 use `_WRAPPER.format(content=f"""...""")`. If any user-controlled value (customer name, return reason, note text) reaches those f-strings unescaped, that's HTML injection into an email. Needs checking per call site and a proper template engine with autoescaping.

---

## 3. What is genuinely good

Being fair to the existing work:

- **Auth is well built.** `core/security.py` uses server-persisted refresh-token `jti`s so tokens can actually be revoked before expiry — with a comment explaining exactly why plain JWTs can't be. That's real engineering judgement.
- **Secrets are not hardcoded.** `config.py` resolves `SECRET_KEY` from env with a dev-only file fallback, and the encryption key is HKDF-derived with a note about rotation breaking stored PII.
- **CI exists and is real** — Postgres service container, lint, tests, security, build, staged deploy.
- **PII encryption and consent tracking** have their own migration (`e4b7c1d90a23`).
- **Ownership guards are consistently applied** at the route layer.
- **The previous work documented its own ML weaknesses honestly** instead of hiding them. That is rarer and more valuable than it sounds.

---

## 4. All 60 phases — real status

Legend: **✅ done** · **🟡 partial** · **⬜ not started** · **🔒 blocked on something money/time/data can't shortcut**

| Phase | Status | Note |
|---|---|---|
| 0 Product definition | 🟡 | Roadmap exists; no PRD, personas undefined in code |
| 1 Codebase audit | ✅ | This document |
| 2 Architecture hardening | 🟡 | Layering good; versioning present; no idempotency, no correlation IDs |
| 3 Database & data model | 🟡 | 7 migrations, but **BLOCKER-2** open |
| 4 Multi-tenancy | 🟡 | Works, but **HIGH-1** — no CI isolation tests |
| 5 Identity | 🟡 | JWT+refresh solid; no MFA, no email verification |
| 6 Authorization | 🟡 | RBAC exists (`test_rbac.py`); no fine-grained permission strings |
| 7 Security | 🟡 | Good foundations; no malware scan on uploads, no CSP verified |
| 8 Audit & governance | 🟡 | Audit log writes exist; immutability not enforced |
| 9 Observability | 🟡 | `core/metrics.py` exists; no tracing |
| 10 Testing | 🟡 | Backend only; **HIGH-2** |
| 11 Frontend | 🟡 | 14 pages; state coverage unverified; **MEDIUM-1** |
| 12 Lifecycle state machine | ⬜ | No enforced transition guard found |
| 13 Evidence system | 🟡 | Documents endpoint exists; no hashing/CV-ready pipeline |
| 14 Intelligence engine | 🟡 | Exists but rests on **BLOCKER-1** |
| 15 ML data pipeline | ⬜ | **BLOCKER-1** |
| 16 Feature engineering | 🟡 | `feature_mapping.py` present |
| 17–21 ML model family, benchmarking, evaluation, uncertainty, explainability | 🟡 | One model, not nine; explainability endpoint exists |
| 22 Computer vision | 🔒 | Needs labelled damage images you do not have |
| 23 Multimodal | 🔒 | Depends on 22 |
| 24–25 Decision optimisation, counterfactual | ⬜ | **BLOCKER-1 must clear first** |
| 26 Human-in-the-loop | 🟡 | `manual_override` endpoint exists |
| 27–30 ML monitoring, registry, continuous learning, per-customer ML | 🟡/🔒 | `model_registry.py` exists; 29–30 need real outcome data |
| 31 Return portal | ⬜ | |
| 32 Workflow automation | 🟡 | `workflow_service.py` + Workflows page |
| 33–34 Integrations, public API | ⬜ | |
| 35 AI copilot | 🔒 | Roadmap correctly gates this behind trustworthy analytics |
| 36–37 Executive intelligence, logistics optimisation | 🟡/⬜ | |
| 38–40 Event-driven, performance, cloud | 🟡 | Terraform + nginx + docker present |
| 41 CI/CD | ✅ | Genuinely done |
| 42 Backups & DR | 🟡 | `infra/backups` exists; **restore never drilled** |
| 43–44 Globalisation, regional ML | ⬜ | Blocked by `_inr` column naming |
| 45–46 Billing, enterprise SSO/SAML/SCIM | ⬜ | Weeks of work each, needs vendor accounts |
| 47 Compliance | 🔒 | **Needs a lawyer.** DPDP Rules 2025 position must be validated by a qualified professional |
| 48 Accessibility | ⬜ | **MEDIUM-1** |
| 49 Documentation | 🟡 | 65 files, some now inaccurate |
| 50–51 Product analytics, A/B | ⬜ | |
| 52 ROI validation | 🔒 | **Needs pilot customers.** No amount of code substitutes |
| 53–57 Digital twin, network intelligence, causal, optimisation, AI governance | ⬜/🔒 | Need production data volume |
| 58 Failure engineering | ⬜ | |
| 59 Penetration test | 🔒 | **Needs an external security firm.** Costs money |
| 60 Production certification | ⬜ | Final gate |

**Count:** ✅ 2 · 🟡 ~24 · ⬜ ~24 · 🔒 ~10

The 🔒 ten cannot be written by anyone, in any amount of time, at a keyboard. They need labelled images, paying pilot customers, a lawyer, and a security firm.

---

## 5. Ordered fix list

Ordered by *what breaks a real customer first*, not by phase number.

1. **BLOCKER-2 — money to integer minor units + currency column.** Mechanical, ~1 session, unblocks Phase 43.
2. **BLOCKER-1 — ML honesty gate.** Either obtain real return data, or ship the model as clearly-labelled *advisory with stated confidence*, never as an automated financial decision. Until then Phases 24–25 stay closed.
3. **HIGH-1 — push tenant filtering into `store.py` + add CI isolation tests.** Turns isolation from a discipline problem into a structural guarantee.
4. **HIGH-2 — Vitest + Playwright on the core journey.**
5. **Phase 12 — the state machine.** Cheap, high value, makes the lifecycle auditable.
6. **MEDIUM-1 / MEDIUM-2 — a11y pass on `ui/index.jsx`, email templating.**

---

## 6. The honest verdict

This is a substantial, competently-structured codebase — well above a typical student project. The auth layer and CI in particular are the work of someone thinking properly.

It is **not** ready for real customers today, and the reason is not the 24 unstarted phases. It is BLOCKER-1: the intelligence layer, which is the entire product, is trained on data that was generated rather than observed. Everything else on this list is fixable in weeks. That one is fixable only by getting real returns data from a real merchant.

**The good news:** that suggests the fastest path to a real product. Find one merchant — a single mid-size D2C brand — who will give you six months of historical return data in exchange for free use of the tool. That one relationship converts BLOCKER-1, Phase 29, Phase 30, and Phase 52 from impossible to possible, and it is worth more than another 20,000 lines of code.
