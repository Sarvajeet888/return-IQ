# Courier Remittance Reconciliation — What Changed

Second feature, built on top of the COD risk scoring feature from before.
Answers: "did the courier actually pay what they were supposed to, per order?"

## How it connects to the first feature

Reconciliation needs an "expected amount" to compare against. Rather than
inventing a separate order-tracking system, it looks up the
`CODRiskAssessment` row created when that order was scored pre-shipment
(feature #1) and uses its `order_value` as the expected amount. If an
order was never scored, that's marked `unmatched_no_expected` rather than
guessed at — flagged clearly so you know pre-shipment scoring coverage
directly improves reconciliation coverage.

## New files

- `backend/app/services/remittance_service.py` — matching/discrepancy logic
- `backend/app/api/v1/routes/remittance.py` — 5 endpoints (below)
- `backend/alembic/versions/a1c58d0e7fb2_add_courier_remittances_table.py`
- `backend/tests/unit/test_remittance_service.py` — 6 tests
- `backend/tests/integration/test_remittance_api.py` — 8 tests, including real CSV upload

## New endpoints

- `POST /api/v1/remittance/ingest` — JSON batch reconciliation
- `POST /api/v1/remittance/upload` — CSV upload (what couriers actually export), same secure streamed-read pattern already used for document uploads elsewhere in this codebase
- `GET /api/v1/remittance/summary` — totals + per-courier breakdown
- `GET /api/v1/remittance/mismatches` — flagged discrepancies for drill-down
- `GET /api/v1/remittance/unmatched` — orders with no expected amount on file

## Modified files

- `backend/app/db/models.py` — added `CourierRemittance` table
- `backend/app/db/store.py` — added `get_cod_risk_assessment_by_order_id`, `create_courier_remittance`, `get_remittances_for_org`
- `backend/app/schemas/schemas.py` — added remittance request/response schemas
- `backend/app/main.py` — registered the new router

## Test results

- Before this feature: 235/235 passing (includes feature #1)
- After this feature: 249/249 passing (235 + 6 unit + 8 integration)
- Migration verified against fresh DB + against ORM model shape

## Still open — business decisions, not engineering ones

- `DISCREPANCY_TOLERANCE_INR = 5.0` in `remittance_service.py` — the
  rounding tolerance before something counts as a real mismatch. Worth
  confirming this matches what Finance actually considers "close enough."
- Reconciliation coverage is capped by pre-shipment scoring coverage —
  the more orders that go through `/cod-risk/score` before shipping, the
  fewer `unmatched_no_expected` rows you'll see here. Worth deciding
  whether pre-shipment scoring becomes mandatory in the seller workflow.
