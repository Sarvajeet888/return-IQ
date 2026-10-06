# ML Pipeline — How It Actually Works

*(Phase 4.1. Every claim here was verified against the actual source in this repo, not assumed.)*

## End-to-end flow for one return

```
API request (returns.py)
    │
    ▼
feature_mapping.build_feature_dict()
    - normalises free-text input (courier/category/reason strings) into the
      model's exact training vocabulary via lookup dicts
    - computes chargeable_weight = max(actual_weight, volumetric_weight)
    - computes distance_km from a pincode-difference heuristic (NOT real
      routing distance - see "Known limitations" below)
    - computes customer_return_rate / merchant_return_rate from historical
      counts, capped at 0.6 / 0.30 respectively
    │
    ▼
ml_service.score_return(features, item_value, risk_threshold, condition)
    │
    ├─▶ predictor.predict_with_explanation(features)      [REAL ML]
    │       preprocessor.transform()  → 30-element one-hot + numeric vector
    │       model.predict()           → XGBoost regression → predicted_cost_inr
    │       top_drivers_for_row()     → importance-weighted driver ranking
    │
    ├─▶ _compute_fraud_score(...)          [rule-based, if/else + weighted sum]
    ├─▶ _compute_damage_probability(...)   [rule-based, if/else]
    ├─▶ _estimate_resale_value(...)        [formula: condition x category x damage]
    ├─▶ _compute_carbon_footprint(...)     [formula: distance x weight x courier factor]
    │
    ▼
_derive_routing() → accept / reject / refund_and_keep / charge_return_fee
    (based on fraud_score, risk_score, predicted_cost vs item_value)
    │
    ▼
Persisted to `predictions` table, returned to caller
```

## What's real ML vs what isn't

| Component | Type | Input → Output |
|---|---|---|
| Cost prediction | **Trained XGBoost regressor** | 30-dim feature vector → predicted shipping/processing cost (₹) |
| Fraud score | Weighted if/else rules | return-rate, payment mode, reason, value, season → 0-100 score |
| Damage probability | Lookup table + adjustments | return_reason, condition, fragile → 0-1 probability |
| Resale value | Formula | item_value × condition multiplier × category depreciation × (1 − damage×0.5) |
| Carbon footprint | Formula | distance × weight × per-courier emission factor |
| Risk score | Formula (not ML) | combines predicted_cost/item_value ratio + return rates |
| Confidence score | Formula | fixed base + small bumps, **not derived from the model's actual prediction uncertainty** — see limitations |

Only the first row is a trained model. Everything else is deterministic business logic — legitimate for an MVP, but only one of these six numbers has any statistical backing.

## Known limitations (found during this audit, not previously documented)

1. **`distance_km` is not real distance.** It's `abs(pincode_diff) // 40`, clamped to [10, 2500]. This is a rough proxy, not a routing-API result — worth knowing since it's one of the top 2 cost drivers per the model's own feature importances.
2. **`confidence_score` doesn't come from the model.** It's a fixed formula (`0.85 + bonuses`) that doesn't reflect how far out-of-distribution a given input is from what the model was trained on. A truly novel combination of features (e.g. a courier/category pair rarely seen in training) gets the same confidence treatment as a common one.
3. **No feature drift monitoring.** Nothing currently tracks whether live traffic's feature distributions (e.g. average `distance_km`, category mix) are drifting away from what the 80K-row training set looked like. The model would silently degrade if the business changes shape (new courier partnerships, new categories) without anyone knowing.
4. **`get_predictor()` is `@lru_cache(maxsize=1)`** — the model loads once per process and is never reloaded. Fine for a single deploy, but means a hot-swap of `model.joblib` on disk (e.g. via the new `model_registry.py`) requires a process restart to take effect; there's no live-reload path today.
