# Model Card — ReturnIQ Cost Prediction Model

**Model:** ReturnIQ Return Cost Predictor
**Version:** as recorded in `ml/artifacts/model_metadata.json`
**Division:** Kalman Enterprise · Kalman Consultancy Services
**Date:** August 2026

Format follows the model card convention (Mitchell et al., 2019).

---

## 1. Model Details

| | |
|---|---|
| **Type** | Gradient-boosted decision tree regressor (XGBoost) |
| **Task** | Regression — predict reverse logistics processing cost in INR |
| **Input** | 15 features (4 categorical, 11 numeric) |
| **Output** | Single continuous value: predicted cost in INR |
| **Training data size** | ~80,000 historical return records |
| **Framework** | XGBoost 2.1.3, scikit-learn preprocessing |
| **Artifact** | `ml/artifacts/model.joblib` + `preprocessor.joblib` |
| **Licence** | Proprietary — Kalman Consultancy Services |

### Important scope limitation

**This is the only trained ML model in ReturnIQ Enterprise.** The fraud score,
damage probability, resale estimate, and carbon footprint are business-rule
engines — deterministic calculations, not learned models. They are presented
alongside the ML output in the same API response, which makes it easy to
mistake them for model outputs. They are not.

See `AI_TRANSPARENCY.md` for the full breakdown.

---

## 2. Intended Use

### Intended
- Estimate the processing cost of an individual return at intake
- Feed a routing recommendation (accept / reject / manual review / refund-and-keep)
- Support human decision-making in reverse logistics operations
- Indian e-commerce and 3PL contexts

### Out of scope
- **Not** for automated denial of customer claims without human review
- **Not** validated outside India — pincode tiers, courier set, and cost
  structures are India-specific
- **Not** a forecasting model. It scores individual returns, not aggregate volume
- **Not** for pricing decisions, insurance underwriting, or credit assessment
- **Not** for product categories outside the six it was trained on

### Users
Merchant operations staff, warehouse teams, and automated workflow rules
configured by the merchant.

---

## 3. Features

| Feature | Type | Source |
|---|---|---|
| `product_value` | numeric | Item value in INR |
| `actual_weight` | numeric | kg |
| `volumetric_weight` | numeric | kg |
| `chargeable_weight` | numeric | Derived: max(actual, volumetric) |
| `distance_km` | numeric | **Estimated** from pincode tiers — not real geographic distance |
| `pickup_tier` | numeric | 1–3, derived from origin pincode |
| `destination_tier` | numeric | 1–3, derived from destination pincode |
| `fragile` | binary | Merchant-declared |
| `festive` | binary | Merchant-declared |
| `customer_return_rate` | numeric | Derived, capped at 0.6 |
| `merchant_return_rate` | numeric | Derived, capped at 0.30 |
| `courier` | categorical | 6 values |
| `category` | categorical | 6 values |
| `payment_mode` | categorical | 2 values |
| `return_reason` | categorical | 5 values |

**Note on `distance_km`:** this is a heuristic estimate derived from pincode
tier difference, not a routed or geodesic distance. It should not be described
as route calculation.

### Vocabulary

| Feature | Accepted values |
|---|---|
| courier | BlueDart, DTDC, Delhivery, Ekart, Shadowfax, Xpressbees |
| category | Beauty, Books, Electronics, Fashion, Home, Sports |
| payment_mode | COD, Prepaid |
| return_reason | Changed Mind, Damaged, Quality Issue, Wrong Item, Wrong Size |

Values outside these sets are one-hot encoded as all zeros — the feature is
effectively dropped. The API returns a `data_quality_warnings` field when this
happens.

---

## 4. Performance

### The reported metric, with its caveat

`model_metadata.json` records **R² = 0.9993**.

**This number should not be quoted as a performance guarantee.** Reasons:

1. It came from a **single training run** with no documented train/test split
   methodology and no cross-validation.
2. **The original 80,000-row dataset is not in the repository.** The metric
   cannot be re-verified or re-computed.
3. An R² of 0.9993 on a real-world cost prediction task is unusually high. In
   practice this pattern usually indicates either target leakage (a feature
   that encodes the answer) or an evaluation performed on training data.
4. No baseline comparison exists. Without knowing how a simple linear model or
   a weight × distance heuristic performs, the number has no context.

**We have not proven the model is bad — we have not proven it is good.** The
honest statement is: *unverified*.

Full analysis in `docs/ai/ML_EVALUATION_AUDIT.md`.

### What is verified

| Property | Status | How |
|---|---|---|
| Pipeline executes correctly | ✅ | 25 automated tests |
| Preprocessing is deterministic | ✅ | Tested — same input always yields same features |
| Feature mapping matches model vocabulary | ✅ | Test asserts every emitted value exists in training vocabulary |
| Derived features are bounded | ✅ | Rates capped, distance bounded 10–2500km |
| Inference latency | ✅ | Under 100ms end-to-end including DB writes |
| Unknown values are surfaced | ✅ | `data_quality_warnings` on every affected request |

**Real-world accuracy has not been measured.** It can only be measured once
confirmed outcomes accumulate through `PATCH /returns/{id}/outcome`.

---

## 5. Explainability

Per-prediction, the API returns the top cost driver and a ranked feature
importance list.

**Method:** XGBoost's built-in gain-based `feature_importances_`, weighted
against the specific row's values.

**This is not SHAP.** It is an importance-weighted heuristic. Gain-based
importance is a global property of the model, not a per-prediction attribution.
It indicates which features the model relies on generally, adjusted for this
row — it does not decompose this specific prediction the way SHAP values would.

The code and the API response both label it accordingly. Prior to Phase 4 this
field was a hardcoded if/else guess that never touched the model at all; that
was a genuine defect and was fixed.

---

## 6. Limitations and Risks

### Known limitations

| Limitation | Consequence |
|---|---|
| Trained on Indian logistics data only | Predictions for other markets are unvalidated |
| Six categories, six couriers | Anything else degrades silently (now warned) |
| Static artifact — no online learning | Accuracy drifts as costs and carrier pricing change |
| No drift detection | Degradation would go unnoticed without manual review |
| Distance is heuristic | Systematic error for unusual routes |
| Trained on historical merchant behaviour | Inherits any bias present in past decisions |

### Risks and mitigations

**Automation bias.** Staff may defer to a confident-looking number. *Mitigation:*
confidence is labelled as heuristic, explainability is shown, override is always
available and audit-logged, and documentation recommends routing high-value
returns to human review by rule.

**Silent degradation on unknown inputs.** *Mitigation:* `data_quality_warnings`
now names the unrecognised value and lists valid ones.

**Model staleness.** Courier pricing changes; the artifact does not.
*Mitigation:* model registry supports versioned deployment and rollback.
Retraining is a deliberate operation. *Unmitigated:* no automated drift alert
exists yet.

**Misinterpretation as fraud detection.** The response bundles ML cost
prediction with rule-based fraud scoring. *Mitigation:* labelled in the API
response, the UI, and this document.

---

## 7. Ethical Considerations

**Effect on end customers.** A `reject` recommendation can mean a real person is
denied a legitimate return. The model was trained on historical merchant
decisions and will reproduce whatever patterns exist in them, including
unfairness.

**Mandatory human oversight.** The Terms of Service require the merchant to keep
human review for high-value returns and for any case where a recommendation
would deny a customer claim. This is stated in the ToS, the AI Transparency
Statement, and every Statement of Work.

**Fairness.** No fairness audit has been conducted. The model does not use
protected attributes directly, but `customer_return_rate` and pincode tier are
plausible proxies for socioeconomic status — a customer in a tier-3 pincode may
receive systematically less favourable outcomes. **This has not been tested for
and should be, before the model is used at scale.**

**Blacklisting.** The platform allows blacklisting a customer identifier. This
is a merchant business decision, not a model output, but it is a consequential
action and is audit-logged. Merchants should have a documented appeal process.

**Transparency to end customers.** Merchants using ReturnIQ should disclose in
their own returns policy that automated assessment is used.

---

## 8. Retraining Strategy

### Preconditions
- Access to a fresh dataset with actual observed processing costs, or
- 500+ confirmed outcomes collected via `PATCH /returns/{id}/outcome`

### Process
1. Assemble the dataset with a documented train/validation/test split
2. Check explicitly for target leakage — the most likely explanation for the
   current R²
3. Establish a baseline (linear regression, and a simple weight × distance rule)
4. Train, tune, and evaluate on a genuinely held-out set
5. Compare against the baseline. If the model does not beat weight × distance
   meaningfully, that is an important finding and should be reported
6. Register with `ml/model_registry.py` and version the artifact
7. Shadow-run against production traffic before switching over
8. Record everything in `docs/ai/MODEL_VERSION_HISTORY.md`

### Fraud and damage models
Currently rule-based. `ml/train_fraud_model.py` exists as a scaffold and
**deliberately refuses to run until 200+ labelled outcomes exist.**

We will not generate synthetic labels to produce a "trained fraud model." A model
trained on labels generated by the existing rules would just be an expensive
reimplementation of those rules, presented as machine learning. That would be a
worse version of the mislabelling problem this project already corrected once.

---

## 9. Monitoring

| Metric | Where |
|---|---|
| Inference latency (histogram) | Prometheus `returniq_ml_inference_latency_ms` |
| Predictions by routing decision | Prometheus `returniq_predictions_total` |
| Model version in use | Every prediction record; `GET /api/v1/ai/performance` |
| Label collection progress | `GET /api/v1/admin/ml-stats` |
| Data quality warnings | API response field |

**Not monitored yet:** feature drift, prediction distribution shift, accuracy
against outcomes. These need the label pipeline to accumulate data first.

---

## 10. Version History

| Version | Date | Change |
|---|---|---|
| xgb_v1 | Pre-project | Original training run. Metrics unverified, dataset unavailable |
| — | Phase 4 | Fixed fake explainability (was hardcoded if/else); stats now read from metadata rather than hardcoded literals |
| — | Phase 9 | Added unknown-value detection and `data_quality_warnings` |

**No retraining has occurred.** The artifact is the original.

---

## 11. Contact

Om Pilaji · Director, Kalman Consultancy Services
Questions about model behaviour, limitations, or retraining.
