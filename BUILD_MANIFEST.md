# Final Build Manifest — ReturnIQ Enterprise

**Version 0.9.0-rc1 · Built 4 August 2026**
**All 11 phases merged and verified.**

---

## Merge Verification

Every uploaded phase archive was compared file-by-file against this build.

| Source archive | Files unique to it | Resolution |
|---|---|---|
| `returniq_enterprise_phase11.zip` | — | **Used as the base.** Confirmed superset of phases 1–11 |
| `returniq_enterprise_phase10.zip` | 0 | Fully contained |
| `returniq_enterprise_phase9.zip` | 9 | All 9 were **relocated** in the Phase 10 docs restructure, not lost — verified present at their new paths |
| `returniq_enterprise_phase8.zip` | 9 | Same 9 relocations |
| `rl_enterprise_phase2_fixed.zip` | **7 video assets** | ⚠️ **Genuinely missing — restored.** See below |
| `rl_enterprise_phase3–7` | 0 | Superseded |

### The one real gap found

`frontend/public/` — the entire directory was absent from every archive after
Phase 5, because an early packaging step used `-x "*.mp4"` to keep the zip small
and the exclusion was never removed.

`frontend/src/pages/Landing.jsx` references `/scroll_video.mp4` (line 97) and
`/truck_video.mp4` (line 376). **The landing page had broken video elements in
every build from Phase 5 onward.** Restored from the Phase 2 archive.

### Relocated files (not missing)

| Old path | Current path |
|---|---|
| `ML_PIPELINE.md` | `docs/ai/ML_PIPELINE.md` |
| `ML_EVALUATION_AUDIT.md` | `docs/ai/ML_EVALUATION_AUDIT.md` |
| `docs/guides/USER_GUIDE.md` | `docs/client/USER_GUIDE.md` |
| `docs/guides/ADMIN_GUIDE.md` | `docs/client/ADMIN_GUIDE.md` |
| `docs/guides/TROUBLESHOOTING.md` | `docs/client/TROUBLESHOOTING.md` |
| `docs/guides/INSTALLATION.md` | `docs/operations/INSTALLATION.md` |
| `docs/guides/DEPLOYMENT.md` | `docs/operations/DEPLOYMENT.md` |
| `docs/guides/API_GUIDE.md` | `docs/api/API_GUIDE.md` |
| `docs/legal/AI_TRANSPARENCY.md` | `docs/ai/AI_TRANSPARENCY.md` |

---

## Verified Build State

| Gate | Result |
|---|---|
| Full test suite | ✅ **223 passed** |
| Migration integrity (fresh DB) | ✅ **5 passed** |
| Security penetration tests | ✅ **36 passed** |
| Ruff correctness (F, E9) | ✅ **All checks passed** |
| Bandit high severity | ✅ **0** |
| Bandit medium severity | ✅ **0** |

---

## Contents

```
returniq_enterprise_FINAL/            219 files
├── backend/          67 Python files · 93 endpoints · 21 tables · 4 migrations
├── frontend/         19 JSX pages · 7 public assets (restored)
├── infra/            Docker · nginx · monitoring · logging · backups · Terraform
├── qa/               Test strategy · coverage matrix · QA report · evidence
├── phase11/          Production audit · performance · security · DR · beta · KPIs
├── docs/             59 markdown files across 15 categories
├── data/             Synthetic dataset + honest assessment
├── LICENSE           Proprietary licence with AI disclaimer
└── README.md         Master index
```

---

## Phase Contribution

| Phase | Contribution | Evidence |
|---|---|---|
| 1 | Audit — found "5 AI models" was 1 model + 4 rule engines | `docs/ai/AI_TRANSPARENCY.md` |
| 2 | Migration race condition, auth duplication | `FIXES_STATUS.md` |
| 3 | DRY helpers, dead code removal, Dockerfile fix | `FIXES_STATUS.md` |
| 4 | Fake explainability fixed, model registry, 18 tests | `docs/ai/ML_PIPELINE.md` |
| 5 | 9 route modules, workflow engine, 8 tables | `docs/release/CHANGELOG.md` |
| 6 | 4 critical security fixes, headers, non-root containers | `SECURITY_AUDIT_PHASE6.md` |
| 7 | 20 legal and compliance documents | `docs/legal/`, `docs/compliance/` |
| 8 | CI/CD, Terraform, monitoring, logging, backups | `infra/` |
| 9 | 33 → 218 tests; **7 real bugs found** | `qa/reports/QA_SUMMARY_REPORT.md` |
| 10 | Brand, doc architecture, business material, standards | `docs/brand/`, `docs/standards/` |
| 11 | **4 more real defects found by execution** | `phase11/production/PRODUCTION_AUDIT.md` |
| Merge | Restored missing frontend assets | This document |

---

## Cumulative Defects Found

**12 real bugs across Phases 9–11, plus 1 in this merge.**

| # | Defect | Phase | Severity |
|---|---|---|---|
| 1 | App would not boot — deleted middleware class | 9 | 🔴 Critical |
| 2 | `cache.py` crashed on import | 9 | 🔴 Critical |
| 3 | Blacklisting silently did nothing (ORM/migration drift) | 9 | 🔴 High |
| 4 | Phase 5 customer endpoints unreachable (route shadowing) | 9 | 🟠 High |
| 5 | ML predictions silently degraded on unknown inputs | 9 | 🟠 High |
| 6 | Wrong status code on duplicate registration | 9 | 🟡 Low |
| 7 | Duplicate function in `store.py` | 9 | 🟡 Low |
| 8 | **`alembic upgrade head` failed — no deployment possible** | 11 | 🔴 Critical |
| 9 | Dashboard N+1 — 10.6× slower, outage at scale | 11 | 🔴 High |
| 10 | 9 starlette CVEs in the request path | 11 | 🟠 High |
| 11 | 3 fabricated dashboard KPIs shown as measurements | 11 | 🟠 High |
| 12 | Frontend public assets missing — broken landing page videos | Merge | 🟡 Medium |

---

## Still Blocking General Availability

| # | Blocker | Type |
|---|---|---|
| 1 | Company not incorporated | Legal |
| 2 | ToS / Privacy Policy not legally reviewed | Legal |
| 3 | Frontend has zero automated tests | Engineering |
| 4 | No load test on production-spec hardware | Engineering |
| 5 | Customer PII plaintext at rest | Engineering |
| 6 | SMTP not wired | Engineering |
| 7 | No consent capture at registration | Engineering |
| 8 | Company Profile claims 4 features that don't exist | Directors |

Items 1, 2, and 8 are not engineering work. Item 8 is the fastest to fix and the
most damaging if left — see `docs/product/PRODUCT_CLAIMS_AUDIT.md`.

---

## Version

Tagged **0.9.0-rc1**, not 1.0.0. Rationale in
`phase11/release/VERSION_1.0.md`: 1.0 means "we stand behind this in production
for anyone who buys it," and software that has never run in someone else's
production environment does not meet that bar regardless of test coverage.
