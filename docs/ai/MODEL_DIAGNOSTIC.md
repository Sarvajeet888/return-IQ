# Model Diagnostic — What the Cost Model Actually Does

**6 August 2026 · Investigation prompted by loading `synthetic_returns_dataset.csv`**

---

## Two corrections first

While investigating, I made two confident claims that were wrong. Recording
them because a diagnostic that hides its own errors isn't worth much.

**Retracted claim 1 — "the model has target leakage and isn't valid."**
I zipped a 30-element `feature_importances_` array against the 15 names in
`feature_columns.json`. Python's `zip` truncates to the shorter one, so 15
features vanished and the rest displayed as 0.0%. I read that as a dead model.
It isn't: 300 trees, 18,516 split nodes, importances summing to 1.0.

**Retracted claim 2 — "explainability reports the wrong feature name."**
Also wrong. `ml/predict.py` uses `FEATURE_NAMES` from `ml/preprocessor.py`,
which is correctly 30 elements in the exact order `transform()` emits. The
15-entry JSON is a separate raw-input contract that no code path reads. I
"fixed" a file that was fine and have reverted it. 250 tests still pass.

**Lesson:** check array lengths before diagnosing a model as broken.

---

## The actual finding

Read correctly, the model's feature importances are:

| Feature | Importance |
|---|---:|
| **distance_km** | **91.8%** |
| chargeable_weight | 3.5% |
| volumetric_weight | 3.4% |
| fragile | 0.4% |
| payment_mode_COD | 0.2% |
| customer_return_rate | 0.2% |
| category_Electronics | 0.02% |
| **product_value** | **~0.0%** |
| **return_reason** | **~0.0%** |
| everything else | ~0.0% |

**Distance and weight account for 98.7% of every prediction.**

### What that means

The model is, functionally, a **courier pricing calculator**. It answers
"what will the shipping leg cost?" — not "how risky or expensive is this
return?"

Item value, return reason, category, and customer history contribute almost
nothing. A ₹300 lipstick and a ₹90,000 laptop travelling the same route with
similar weight get near-identical cost predictions.

That is not necessarily wrong — reverse logistics cost genuinely *is* mostly
distance × weight. But it changes how the product should be described.

### It also explains the R² of 0.9993

Flagged as suspicious since Phase 4. If the training data's cost target was
generated as roughly a function of distance and weight, then the model
recovered that formula almost exactly — and R² near 1.0 is the expected
result, not evidence of leakage.

**This does not fully close KI-009.** The original dataset still isn't
available, so the metric still can't be independently re-verified. But the
most alarming explanation is now the least likely one.

---

## Why the dataset produced flat costs

First run over all 5,000 rows returned costs of **₹439–514** — a ₹75 spread
across wildly different returns.

Cause: the dataset contains no distance, weight, or pincodes, so I held
`distance_km` fixed at 850km. That froze 91.8% of the model. The remaining
8.2% had almost nothing to vary on.

Once distance was allowed to vary across tier-1/2/3 origin pincodes, the
spread became **₹74 – ₹1,448** — which is the model behaving normally.

---

## Consequences for how this is described

| Don't say | Do say |
|---|---|
| "AI predicts return cost from 15 factors" | "A trained model estimates the shipping leg, driven mainly by distance and weight" |
| "The model considers item value and return reason" | It measurably doesn't — both are ~0% importance |
| "99.93% accurate" | Still unverified. Don't quote it |

`docs/ai/MODEL_CARD.md` and `docs/ai/AI_TRANSPARENCY.md` should be updated
with the importance table above. It is the clearest single statement of what
the model actually is.

---

## Fraud scorer benchmark — the first ever measured

The dataset carries **303 real fraud labels**, which made it possible to
score the rule engine for the first time. Run using only the dataset's real
fields (`customer_return_rate`, `return_reason`, `item_value`); COD, fragile
and festive were held neutral so they contributed exactly zero.

| Threshold | Flagged | Caught | Precision | Recall | F1 |
|---:|---:|---:|---:|---:|---:|
| ≥10 | 1,845 | 124 | 0.067 | 0.409 | 0.115 |
| ≥25 | 525 | 62 | 0.118 | 0.205 | 0.150 |
| ≥35 | 387 | 51 | 0.132 | 0.168 | 0.148 |
| **≥70** *(the app's threshold)* | **0** | **0** | — | — | — |

- Base rate: **0.061**
- **ROC-AUC: 0.539** (0.500 = chance)

### Two things follow

**1. At the configured threshold of 70, the scorer flags nothing.** The score
never reaches 70 without COD + festive + fragile all firing together. Worth
checking against production data — if real returns also rarely exceed 70, the
fraud feature is effectively inert.

**2. Discrimination is weak.** AUC 0.539 is barely above chance. Best
precision (0.132 at threshold 35) is roughly 2× the base rate — real, but
thin: 387 flagged to catch 51.

### Caveats, stated plainly

- **Synthetic data.** Labels were sampled as `Bernoulli(fraud_risk_true)`, so
  this measures agreement with a *simulator's* fraud logic, not real fraud.
- **Half the inputs missing.** COD is worth 15 points and wasn't available.
- Therefore: a strong signal that the rules need work, **not** a verdict.

The honest position remains the one in `AI_TRANSPARENCY.md`: fraud scoring is
rule-based, its real-world precision is unmeasured, and it should support
human review rather than replace it. This benchmark reinforces that.

---

## Recommended next steps

| Priority | Action |
|---|---|
| 🔴 | Update the Model Card with the importance table — "distance × weight" is the honest description |
| 🔴 | Check whether fraud scores ever reach 70 in production. If not, the threshold is misconfigured |
| 🟠 | Re-run this benchmark against real labelled outcomes once 200+ exist |
| 🟠 | If cost is genuinely distance × weight, consider whether a transparent formula would serve customers better than an opaque model |
| 🟡 | Add `product_value` interactions if item value *should* matter — currently it doesn't |
