# Merge Record — COD Risk & Remittance Branch

**6 August 2026**

A parallel branch (`returniq_both_features.zip`) added two features but was
built on an older base, so it lacked the Phase 12 work and reintroduced three
bugs that had already been found by running the app. This records what was
merged and how the conflicts were settled.

---

## Result

| Gate | Result |
|---|---|
| Tests | **279 passed** (252 base + 27 merged) |
| Migration chain | Linear, **single head** `a1c58d0e7fb2` |
| Security suite | 36/36 |
| Ruff (F, E9) | Zero errors |
| Bandit | 0 high, 0 medium |
| Documented endpoints | **85** |

---

## What was merged in

### COD Risk Scoring
- `app/services/cod_risk_service.py` (213 lines)
- `app/api/v1/routes/cod_risk.py`
- Migration `f3b7e0c19a44` — `cod_risk_assessments` table
- Model `CODRiskAssessment`
- 3 schemas, 3 store functions
- 13 tests

`POST /api/v1/cod-risk/score` · `GET /api/v1/cod-risk/assessments`

### Courier Remittance Reconciliation
- `app/services/remittance_service.py` (128 lines)
- `app/api/v1/routes/remittance.py`
- Migration `a1c58d0e7fb2` — `courier_remittances` table
- Model `CourierRemittance`
- 6 schemas, 2 store functions
- 14 tests

`POST /ingest` · `POST /upload` · `GET /summary` · `GET /mismatches` · `GET /unmatched`

Supporting store helpers also ported: `get_customer_by_phone`,
`get_pincode_fraud_stats`, `get_recent_names_at_address`.

---

## Conflicts and how they were resolved

### 1. Divergent migration heads

Both branches forked from `d9e2f4a7b831`:

```
d9e2f4a7b831 ─┬─ e4b7c1d90a23   (consent + PII encryption)
              └─ f3b7e0c19a44 ─ a1c58d0e7fb2   (COD risk, remittance)
```

Two heads means `alembic upgrade head` fails outright — the same class of
failure that blocked all deployment in Phase 11.

**Resolved** by re-parenting `f3b7e0c19a44.down_revision` from `d9e2f4a7b831`
to `e4b7c1d90a23`, making the chain linear. Verified end to end on a fresh
database.

### 2. Base version conflicts — base kept

The feature branch was missing work that had already been validated by running
the application. In every case the current base was kept, because these were
not stylistic differences but fixes for reproduced failures:

| Item | Why the base won |
|---|---|
| Negative-cost clamp | Branch would predict **−₹738** processing costs |
| Seed race fix | Branch **crashes a worker** on first boot |
| Customers page fix | Branch renders `/customers` **blank** |
| Duplicate `getNotifications` in `api.js` | Same silent-shadowing bug class |
| ErrorBoundary | Without it, any render crash is a blank screen |
| Terracotta theme | Branch still on indigo, mismatched with the landing page |
| Consent capture, PII encryption, SMTP, S3 | Phase 12 market-readiness work |
| CI/CD workflows, `.gitignore` | Absent from the branch |

### 3. Missing pieces the branch's own code needed

Copying the services and routes alone was not enough — the branch's route
modules import 9 schema classes that also had to be ported, or the app fails
at import. Caught immediately because `import app.main` raised `ImportError`
rather than failing silently at request time.

---

## ⚠️ Security note

`returniq_both_features.zip` contained a committed `.env` with live values:

```
SECRET_KEY=4zsgfy0NI8qoyYFY6wCWQnv-KlUKzoOTVG…
API_KEY_HASH_PEPPER=9q8b6VfWsxx3lVYAecAU-F52v…
```

**Those secrets should be treated as compromised and rotated.** They were not
carried into this build. `.gitignore` here excludes `.env`; the branch had no
`.gitignore` at all.

---

## Lesson for future parallel work

Both branches started from `d9e2f4a7b831` and neither knew about the other.
The feature work was sound; the cost was a migration conflict and three
regressions that had to be re-detected.

`docs/standards/KALMAN_ENGINEERING_STANDARDS.md` already says a migration must
ship with its ORM model in the same commit. Worth adding: **rebase feature
branches onto the current head before merging, and re-run the full suite** —
divergent Alembic heads are silent until deployment, which is the worst place
to find them.
