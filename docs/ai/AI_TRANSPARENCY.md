# AI Transparency Statement — ReturnIQ Enterprise

**Version:** 1.0
**Last Updated:** 1 August 2025

This document explains exactly what AI and machine learning is and is not doing in
ReturnIQ, what its limitations are, and how human oversight is built into the system.
Accurate disclosure is important here because the platform was previously labelled as
having "5 AI models" — this document corrects that characterisation.

---

## 1. What Runs in ReturnIQ When You Submit a Return

| Component | Technology | Trained on real data? | Honest label |
|---|---|---|---|
| **Cost Prediction** | XGBoost gradient-boosted model | ✅ Yes — trained on ~80K historical returns | Real ML model |
| **Fraud Detection** | Weighted rule engine | ❌ No — hand-coded thresholds | Business-rule heuristic |
| **Damage Assessment** | Weighted rule engine | ❌ No — hand-coded thresholds | Business-rule heuristic |
| **Resale Estimation** | Formula with category multipliers | ❌ No — documented business assumptions | Parametric formula |
| **Carbon Footprint** | Formula with per-courier emission factors | ❌ No — estimated industry averages | Parametric formula |

**Plain English:** When you use ReturnIQ, one real ML model runs — the cost predictor.
The other four outputs are deterministic calculations based on rules our team wrote.
They are not machine learning, even though they are presented alongside the ML output
in the API response.

---

## 2. The Cost Prediction Model — What It Does

### 2.1 What It Predicts
The predicted cost of processing a return, in INR. This includes estimated courier
charges, handling, and re-stocking costs based on the return's characteristics.

### 2.2 Inputs (Features)
The model uses these input features:
- Item value (INR)
- Item category (one-hot encoded)
- Weight (grams), volumetric weight (grams)
- Origin and destination pincode zone
- Return reason code (one-hot encoded)
- Courier name
- Payment mode (COD vs. prepaid)
- Fragile flag, festive season flag
- Customer return frequency (historical count)

### 2.3 Model Details
| Attribute | Value |
|---|---|
| Algorithm | XGBoost (gradient-boosted decision trees) |
| Training data size | ~80,000 historical returns |
| Evaluation metric | R² (coefficient of determination) |
| Reported R² | 0.9993 (from training run — see caveat below) |
| Feature importance method | XGBoost gain-based `feature_importances_` |
| Explainability | Importance-weighted heuristic (not full SHAP values) |

**⚠️ Important caveat on the R² figure:** An R² of 0.9993 is unusually high and was
produced in a single training run without confirmed train/test split methodology or
cross-validation. It may reflect overfitting or leakage from the original dataset
(which is no longer in the repository). Do not cite this number as a validated
performance metric. The model's real-world accuracy should be measured against new
production data once the outcome-labeling pipeline (Phase 4.7/4.8) has collected
sufficient labels.

### 2.4 What the Model Cannot Do
- It cannot account for fraud it has never seen before
- It is less accurate for product categories not well-represented in training data
- It does not update itself — it is a static artifact trained once; predictions will
  drift over time as market conditions change
- It cannot assess physical item condition from text descriptions alone

---

## 3. The Fraud Score — What It Actually Is

The fraud score (0–100) is produced by a weighted rule engine, not a trained model.
The rules check factors such as:
- Return frequency for this customer identifier
- Time since purchase
- Whether the return reason is a high-fraud reason code
- Payment mode (COD returns have higher fraud rates historically)
- Whether the customer is on the blacklist
- Item value relative to median return value

**These weights and thresholds are estimated business rules, not learned from data.**
A customer with a high fraud score has matched our heuristic criteria — they have not
been classified by a model trained on confirmed fraud outcomes.

A low fraud score does **not** mean a return is not fraudulent. A high score does
**not** mean a return is fraudulent. The score is a risk indicator to support, not
replace, human judgment.

**Path to a real fraud ML model:** The platform now captures confirmed outcome labels
via `PATCH /api/v1/returns/{id}/outcome`. Once 200+ labeled outcomes have been
collected, `ml/train_fraud_model.py` can be run to train a real supervised model.

---

## 4. Routing Decisions — How They Are Made

The final routing recommendation (accept / reject / manual_review / refund_and_keep)
is determined by a deterministic decision tree that combines:
1. The predicted cost vs. item value ratio
2. The risk score threshold configured by the Merchant
3. The fraud score
4. The damage probability

This is **not** a learned classification model. It is a set of if/else rules that can
be read in `app/services/ml_service.py`, function `_decide_routing()`.

---

## 5. Human Override

Every routing decision can be overridden by an authorised user:
- `POST /api/v1/ai/predictions/{return_id}/override`
- Requires `analyst`, `org_admin`, or `super_admin` role
- The override reason is mandatory and stored in the return's audit trail
- Overrides are recorded in the audit log for compliance

**We strongly recommend** that you configure your workflow rules (Phase 5.12) so that
high-value returns, returns from new customers, and returns with high fraud scores always
route to `manual_review` rather than being auto-approved or auto-rejected by the
platform alone.

---

## 6. Confidence Score

The confidence score reported by the platform is a **heuristic proxy**, not a
statistically calibrated probability. It is calculated from the model's prediction
interval and the input feature values, and is intended to flag cases where the model
is likely operating outside its training distribution. Do not interpret it as a
percentage probability of the prediction being correct.

---

## 7. Model Versioning & Updates

- The current model version is recorded in every prediction record
- The model registry (`ml/model_registry.py`) maintains versioned artifacts with
  rollback capability
- When a new model is trained and deployed, all predictions made under the previous
  version retain their original version label for auditability
- You can view which model version produced a prediction in the explainability endpoint:
  `GET /api/v1/ai/predictions/{return_id}/explain`

---

## 8. Feedback & Improvement

Two mechanisms exist for improving prediction quality over time:

1. **Outcome Labels** — `PATCH /api/v1/returns/{id}/outcome` captures confirmed
   fraud decisions and damage grades. These become training data for future models.

2. **Qualitative Feedback** — `POST /api/v1/ai/feedback` allows staff to flag
   individual predictions as inaccurate and explain why. These are stored in the
   audit log for manual review.

Neither mechanism triggers automatic retraining. Model updates are deliberate, versioned
events, not continuous learning.

---

## 9. What We Commit To

- We will not misrepresent rule-based components as ML models
- We will document every model update in the CHANGELOG
- We will maintain human override capability for every prediction
- We will not use your data to train models for other customers
- We will clearly label the model version used for every prediction

---

## 10. Contact

Questions about AI use in ReturnIQ: ai@returniq.in
