# Cost Model — Evaluation Audit

*(Phase 4.3. This is an audit of the reported metrics and methodology, not a
re-run of training — the original 80K-row dataset isn't in this repo, so the
numbers below are being scrutinized on paper, not reproduced. That
distinction matters and is called out explicitly wherever it applies.)*

## The reported numbers

```
train_rows: 80,000   test_rows: 20,000
MAE:  ₹6.99      RMSE: ₹8.76      R²: 0.9993
```

## Is R² = 0.9993 believable, or a red flag?

A near-perfect R² is usually the first thing to be suspicious of — it's the
classic signature of target leakage (a feature that's secretly a
near-copy of the answer). I checked for that specifically:

- `chargeable_weight` = `max(actual_weight, volumetric_weight)` — computed
  in `feature_mapping.py` from two *other* input features, not from the
  target. This isn't leakage of `predicted_cost_inr`; it's a derived
  feature, which is a completely normal and often useful thing to include.
- No feature in the 30-column vector is a transformation of the cost
  itself, as far as the code shows.

**Verdict: not obviously leakage from what's in this repo.** But I can't
fully rule it out, because:
- I don't have the training dataset, so I can't check for other
  leakage (e.g. was `distance_km` computed from data that also
  informed the true cost during dataset generation?).
- Indian courier pricing is genuinely close to a deterministic formula
  (chargeable weight × zone × courier rate card is roughly how real courier
  invoices work) — so a very high R² is *plausible* for this specific
  domain in a way it wouldn't be for, say, predicting customer churn.

**My honest read:** the number is plausible for this problem domain, but
"plausible" is not the same as "verified." Treat 0.9993 as an unconfirmed
claim inherited from before this audit, not a validated fact.

## What's missing from the methodology (can't be assessed without the dataset)

| Question | Status |
|---|---|
| Was the train/test split random or time-based? | **Unknown** — not documented anywhere in the repo. Matters a lot: a random split can leak information between similar orders; a time-based split is the honest test of "would this have worked on data the model hadn't seen yet." |
| Cross-validation / multiple splits? | **Not present.** Single 80/20 split, single reported number — no variance estimate, so we don't know if 0.9993 is stable or a lucky split. |
| Comparison against a naive baseline? | **Not present.** E.g. "predict the mean cost for that courier+category" — if a trivial baseline also scores R²=0.99 on this data, the XGBoost model's *actual* value-add is smaller than the headline number suggests. |
| Residual analysis (where does it get it wrong)? | **Not possible without the dataset.** Worth knowing if errors cluster on rare couriers, high-value items, or long-tail categories — those are exactly the cases where a wrong prediction is costliest. |

## What I could verify from code alone
- The model expects exactly the 30-feature vector `preprocessor.py` produces, in that exact order — confirmed the shapes match and wrote tests for it (`test_ml_preprocessor.py`).
- `get_model_stats()` previously hardcoded these metrics as literals in `ml_service.py`, disconnected from `model_metadata.json` — meaning if the model were retrained with different numbers, the API would keep reporting the old ones forever. **Fixed** — now reads live from the metadata file (see Phase 4 changelog).

## Recommendation
The single most valuable thing you can add — more valuable than re-tuning
this model — is **production ground-truth logging**: when a return is
actually processed and its *real* final cost is known, store it alongside
the original prediction. After a few hundred real cases, you'd have an
actual, unbiased, non-negotiable answer to "is this model still accurate
in production," instead of relying on a training-time number that could be
a year stale by the time anyone checks it again. This is the same
mechanism proposed for fraud/damage labels in the Phase 4 changelog — it's
worth building once and using for all three.
