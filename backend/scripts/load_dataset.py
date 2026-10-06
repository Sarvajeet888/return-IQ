#!/usr/bin/env python3
"""
Load synthetic_returns_dataset.csv into ReturnIQ.

    cd backend
    python3 scripts/load_dataset.py --dry-run
    python3 scripts/load_dataset.py --limit 500
    python3 scripts/load_dataset.py                 # all 5,000

## What is real and what is not

The source file has 5 of the 15 features the cost model consumes:

    REAL (from the file)          ABSENT (generated here)
    ------------------------      -------------------------------
    order_value                   actual_weight, volumetric_weight
    product_category              chargeable_weight
    return_reason                 courier, payment_mode
    customer_return_rate          pickup_tier, destination_tier
    merchant_id -> merchant rate  distance_km, fragile, festive

That matters more than it sounds, because the trained model's importances are:

    distance_km          91.8%
    chargeable_weight     3.5%
    volumetric_weight     3.4%
    everything else      <0.5%

98.7% of the model's decision weight sits on fields this dataset does not
contain. If those were held constant, every one of the 5,000 predictions came
back between Rs 439 and Rs 514 - a Rs 75 spread across a Rs 300 lipstick and a
Rs 90,000 laptop. Verified, not assumed.

So the generated logistics fields below are what make the cost predictions
vary at all. They are drawn from documented, deterministic distributions
(seeded, so runs are reproducible) - but they are OUR numbers, not the
dataset's.

Every imported return therefore carries:

    raw_payload.synthetic_logistics = True
    raw_payload.real_fields         = [...]
    raw_payload.generated_fields    = [...]

so anyone reading a record later can tell exactly which half is which.

## What IS genuinely real on the resulting dashboard

Return volume, category mix, return-reason distribution, customer return
rates, per-merchant return rates, and the 303 ground-truth fraud labels.
Those come straight from the file and are fully defensible.
"""
from __future__ import annotations

import argparse
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from app.db import store  # noqa: E402
from app.services.feature_mapping import build_feature_dict  # noqa: E402
from app.services.ml_service import score_return  # noqa: E402

SEED = 20260806
DATASET = Path(__file__).resolve().parent.parent.parent / "data" / "synthetic_returns_dataset.csv"

# ── Vocabulary mapping: file values -> model vocabulary ──────────────────────
# 100% coverage verified against the dataset.
CATEGORY_MAP = {
    "Accessories": "Fashion", "Apparel": "Fashion", "Footwear": "Fashion",
    "Home & Kitchen": "Home", "Toys": "Sports",
    "Beauty": "Beauty", "Books": "Books", "Electronics": "Electronics", "Sports": "Sports",
}

REASON_MAP = {
    "Better price found": "change_of_mind", "Changed mind": "change_of_mind",
    "Damaged/Defective": "damaged", "Late delivery": "change_of_mind",
    "Not as described": "not_as_described", "Quality issue": "quality_issue",
    "Wrong item shipped": "wrong_item", "Wrong size": "size_issue",
}

# ── Generated logistics fields ───────────────────────────────────────────────
# Median weights per category, in grams. Rough but ordered sensibly: books and
# beauty are light, home goods heavy.
CATEGORY_WEIGHT_G = {
    "Electronics": 1800, "Fashion": 450, "Books": 600,
    "Home": 2500, "Beauty": 300, "Sports": 1400,
}

# Real Indian pincodes with their tier, so distance is at least plausible.
PINCODES = [
    ("400001", 1, "Mumbai"), ("110001", 1, "Delhi"), ("560001", 1, "Bengaluru"),
    ("600001", 1, "Chennai"), ("500001", 1, "Hyderabad"), ("700001", 1, "Kolkata"),
    ("411001", 2, "Pune"), ("380001", 2, "Ahmedabad"), ("302001", 2, "Jaipur"),
    ("226001", 2, "Lucknow"), ("431122", 3, "Beed"), ("442001", 3, "Wardha"),
    ("577001", 3, "Davangere"), ("621001", 3, "Tiruchirappalli"),
]

COURIERS = ["BlueDart", "Delhivery", "Ekart", "DTDC", "Xpressbees", "Shadowfax"]


def _generate_logistics(rng: random.Random, category: str, order_value: float) -> dict:
    """
    Produce the 10 fields the dataset lacks.

    Deterministic given the seed. Correlated where correlation is realistic:
    heavier categories get heavier parcels, higher-value goods skew slightly
    toward premium couriers and are marginally more likely to be fragile.
    """
    base_g = CATEGORY_WEIGHT_G.get(category, 800)
    actual_g = max(50, int(rng.gauss(base_g, base_g * 0.45)))
    # Volumetric is usually >= actual for e-commerce parcels, sometimes much larger.
    volumetric_g = int(actual_g * rng.uniform(0.9, 2.4))

    origin, o_tier, _ = rng.choice(PINCODES)
    dest, d_tier, _ = rng.choice(PINCODES)

    # Higher-value shipments skew to the premium couriers.
    if order_value > 5000:
        courier = rng.choice(["BlueDart", "Delhivery", "DTDC"])
    else:
        courier = rng.choice(COURIERS)

    return {
        "weight_grams": actual_g,
        "volumetric_weight_grams": volumetric_g,
        "origin_pincode": origin,
        "destination_pincode": dest,
        "courier": courier,
        # COD is ~55% of Indian e-commerce; skewed lower for high-value items.
        "payment_mode": "COD" if rng.random() < (0.30 if order_value > 5000 else 0.55) else "Prepaid",
        "fragile": category in ("Electronics", "Home") and rng.random() < 0.45,
        "festive": rng.random() < 0.18,
        "_tiers": (o_tier, d_tier),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Import the synthetic returns dataset.")
    ap.add_argument("--dry-run", action="store_true", help="Report without writing.")
    ap.add_argument("--limit", type=int, default=0, help="Import only the first N rows.")
    ap.add_argument("--org-email", default="admin@sapnacollection.com",
                    help="Import into the org owning this user.")
    args = ap.parse_args()

    if not DATASET.exists():
        print(f"ERROR: dataset not found at {DATASET}")
        return 1

    df = pd.read_csv(DATASET)
    if args.limit:
        df = df.head(args.limit)

    # Resolve target org
    user = store.get_user_by_email(args.org_email)
    if not user:
        print(f"ERROR: no user {args.org_email}. Register first, or pass --org-email.")
        return 1
    org = store.get_org(user["org_id"])
    print(f"Importing into org: {org['name']} ({org['id'][:8]}...)")
    print(f"Rows: {len(df)}{'   [DRY RUN - nothing will be written]' if args.dry_run else ''}\n")

    # merchant_return_rate derived from the file's own merchant groupings.
    mrr = df.groupby("merchant_id").apply(
        lambda g: min(g.customer_past_returns.sum() / max(g.customer_past_orders.sum(), 1), 0.30),
        include_groups=False,
    ).to_dict()

    rng = random.Random(SEED)
    now = datetime.now(timezone.utc)
    org_count = store.count_org_returns(org["id"])

    imported = failed = 0
    decisions: dict[str, int] = {}
    costs: list[float] = []

    for i, row in enumerate(df.itertuples(), start=1):
        try:
            category = CATEGORY_MAP[row.product_category]
            reason = REASON_MAP[row.return_reason]
            log = _generate_logistics(rng, category, float(row.order_value))

            return_id = str(uuid.uuid4())
            created = now - timedelta(days=int(row.days_since_purchase or 0),
                                      hours=rng.randint(0, 23))

            return_data = {
                "id": return_id,
                "org_id": org["id"], "merchant_id": org["id"],
                "platform_order_id": str(row.return_id),
                "customer_identifier": f"cust_{row.merchant_id}_{i}@imported.local",
                "sku": f"SKU-{row.product_category[:3].upper()}-{i:05d}",
                "item_category": category,
                "item_value": float(row.order_value),
                "origin_pincode": log["origin_pincode"],
                "destination_pincode": log["destination_pincode"],
                "weight_grams": log["weight_grams"],
                "volumetric_weight_grams": log["volumetric_weight_grams"],
                "return_reason_code": reason,
                "courier": log["courier"],
                "payment_mode": log["payment_mode"],
                "fragile": log["fragile"],
                "festive": log["festive"],
                "condition": "damaged" if reason == "damaged" else "good",
                "customer_notes": f"Imported from dataset. Ground-truth fraud flag: {bool(row.is_fraud_flag)}.",
                "status": "prediction_done",
                "created_at": created,
                # Provenance. Anyone reading this record later can see exactly
                # which fields came from the dataset and which we generated.
                "raw_payload": {
                    "source": "synthetic_returns_dataset.csv",
                    "synthetic_logistics": True,
                    "real_fields": [
                        "item_value", "item_category", "return_reason_code",
                        "customer_return_rate", "merchant_return_rate",
                        "days_since_purchase",
                    ],
                    "generated_fields": [
                        "weight_grams", "volumetric_weight_grams", "origin_pincode",
                        "destination_pincode", "courier", "payment_mode",
                        "fragile", "festive",
                    ],
                    "ground_truth": {
                        "is_fraud_flag": bool(row.is_fraud_flag),
                        "status": str(row.status),
                        "fraud_risk_true": float(row.fraud_risk_true),
                        "approval_probability_true": float(row.approval_probability_true),
                    },
                    "note": ("Cost prediction is driven ~92% by distance_km, which this "
                             "dataset does not contain. Treat predicted_cost_inr as "
                             "directional only."),
                },
            }

            if args.dry_run:
                imported += 1
                continue

            # Score through the real pipeline - same path a live return takes.
            features = build_feature_dict(
                return_data,
                customer_return_count=int(row.customer_past_returns or 0),
                org_return_count=org_count + imported,
            )
            # Override the two rates with the dataset's real values.
            features["customer_return_rate"] = min(float(row.customer_return_rate), 0.6)
            features["merchant_return_rate"] = float(mrr.get(row.merchant_id, 0.15))

            result = score_return(
                features=features,
                item_value=float(row.order_value),
                risk_threshold=float(org.get("risk_threshold", 50.0)),
                condition=return_data["condition"],
            )

            store.store_return(return_data)
            store.store_prediction({
                "id": str(uuid.uuid4()),
                "return_request_id": return_id,
                "predicted_cost_inr": float(result["predicted_cost_inr"]),
                "risk_score": float(result["risk_score"]),
                "fraud_score": float(result["fraud_score"]),
                "damage_probability": result["damage_probability"],
                "resale_value_estimate": float(result["resale_value_estimate"]),
                "carbon_footprint_kg": result["carbon_footprint_kg"],
                "confidence_score": result["confidence_score"],
                "routing_decision": result["routing_decision"].value,
                "model_version": result["model_version"],
                "inference_latency_ms": result["inference_latency_ms"],
                "feature_snapshot": result["feature_snapshot"],
                "explainability": result["explainability"],
                "created_at": created,
            })

            # Record the ground-truth fraud label as a confirmed outcome, so the
            # label-collection counter reflects genuinely labelled data.
            if hasattr(store, "store_prediction_outcome"):
                try:
                    store.store_prediction_outcome({
                        "return_request_id": return_id,
                        "actual_fraud_confirmed": bool(row.is_fraud_flag),
                        "notes": "Ground truth from imported dataset.",
                    })
                except Exception:
                    pass

            d = result["routing_decision"].value
            decisions[d] = decisions.get(d, 0) + 1
            costs.append(float(result["predicted_cost_inr"]))
            imported += 1

            if imported % 250 == 0:
                print(f"  ... {imported}/{len(df)}")

        except Exception as exc:
            failed += 1
            if failed <= 5:
                print(f"  row {i} failed: {type(exc).__name__}: {exc}")

    print("\n" + "=" * 58)
    print(f"Imported: {imported}    Failed: {failed}")
    if costs:
        import statistics
        print(f"\nPredicted cost  min Rs {min(costs):.0f}  "
              f"median Rs {statistics.median(costs):.0f}  max Rs {max(costs):.0f}")
        print(f"Routing decisions: {decisions}")
    if args.dry_run:
        print("\nDry run - nothing written. Re-run without --dry-run to import.")
    print("=" * 58)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
