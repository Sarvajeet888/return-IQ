# COD Risk Feature — What Changed

New feature: pre-shipment COD fraud/RTO risk scoring, built to match this
repo's existing conventions exactly (layered store.py / schemas.py /
services/ / api/v1/routes/ pattern already used everywhere else).

## New files

- `backend/app/services/cod_risk_service.py` — the rule engine
- `backend/app/api/v1/routes/cod_risk.py` — `POST /api/v1/cod-risk/score`, `GET /api/v1/cod-risk/assessments`
- `backend/alembic/versions/f3b7e0c19a44_add_cod_risk_assessments_table.py` — migration (chained after your current head, `d9e2f4a7b831`)
- `backend/tests/unit/test_cod_risk_service.py` — 6 tests, pure logic, mocked store
- `backend/tests/integration/test_cod_risk_api.py` — 6 tests, real app + real temp DB + real auth

## Modified files

- `backend/app/db/models.py` — added `CODRiskAssessment` table
- `backend/app/db/store.py` — added `get_customer_by_phone`, `create_cod_risk_assessment`, `get_recent_names_at_address`, `get_cod_risk_assessments_for_org`
- `backend/app/schemas/schemas.py` — added `CODRiskScoreRequest`, `CODRiskFlagOut`, `CODRiskScoreResponse`
- `backend/app/main.py` — registered the new router

## What it deliberately reuses instead of duplicating

Your `Customer` table already tracks `risk_level`, `is_blacklisted`, and
`total_returns` from return history — the scoring service pulls these in
rather than recomputing customer risk from scratch. Only genuinely new
signals get their own rules: high-risk pincode, new-customer + high-value
COD, order value spike vs. customer's average, and same-address/multiple-names
(fraud ring pattern).

## Bugs our own tests caught and fixed before you'd see them

1. A blacklisted customer was scoring only "medium — call to confirm"
   instead of being forced to "high — hold for review." Fixed as an
   explicit override, not just a point value, since blacklist status is a
   human decision made elsewhere in ReturnIQ and shouldn't get diluted by
   unrelated low signals.
2. Multiple weak-but-real signals stacking together (e.g. new customer +
   high value + risky pincode) weren't compounding into real suspicion.
   Added a "signals compounding" rule — standard practice in real fraud
   engines.

## Test results

- Baseline before any change: 223/223 passing
- After this feature: 235/235 passing (223 existing + 12 new)
- `test_migrated_schema_matches_orm_models` confirms the new Alembic
  migration matches the SQLAlchemy model exactly
- `test_upgrade_head_succeeds_on_fresh_database` confirms the migration
  applies cleanly

## Fixed after review: no more fabricated demo data

An earlier version of this feature hardcoded a fake "high-risk pincodes"
list (`110091`, `400104`, `560099`) — leftover demo/test values that had
no business being in production logic. This has been replaced entirely:
`HIGH_RISK_PINCODE` is now computed from real historical data already in
this org's own `ReturnRequest` + `Prediction` tables — the actual average
fraud score of past returns shipped to that exact pincode, with a minimum
sample size (3) so a pincode isn't judged risky off one bad return. See
`store.get_pincode_fraud_stats()` and the updated Rule 2 in
`cod_risk_service.py`. Tests were rewritten to build genuine return
history through the real `/api/v1/returns` endpoint rather than asserting
against a fabricated list.

## Still open — needs a business decision, not an engineering one

- `HIGH_RISK_PINCODES` in `cod_risk_service.py` is currently a hardcoded
  seed set of 3 pincodes. In production this should come from a real,
  periodically-refreshed table of actual RTO rates by pincode — flagged
  in the code as a follow-up, same pattern as `RETURN_FEE_RECOVERY_RATE`
  in `store.py`.
- All point weights are a starting judgment call. Worth reviewing with
  Om/Jeet before this goes live, and revisiting once `actual_outcome`
  data accumulates on real assessments.
