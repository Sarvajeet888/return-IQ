"""
Fraud model training - Phase 4.7 groundwork.

THIS DOES NOT RUN TODAY, AND THAT IS INTENTIONAL. It refuses to run until
there are enough confirmed labels in prediction_outcomes.actual_fraud_confirmed
(see app/db/models.py:PredictionOutcome). Before this endpoint existed,
there was no mechanism anywhere in the app that ever recorded whether a
return actually was fraud - so there was nothing to train on. That's what
PATCH /api/v1/returns/{id}/outcome now captures.

Usage, once you have real labels:
    cd backend && python -m ml.train_fraud_model

What it will do at that point:
    1. Pull every ReturnRequest joined with its Prediction and
       PredictionOutcome where actual_fraud_confirmed is not null.
    2. Build the same 30-feature vector used for cost prediction (reuses
       ml/preprocessor.py so fraud and cost models see identical inputs).
    3. Train a real classifier (XGBoost or sklearn GradientBoostingClassifier)
       against actual_fraud_confirmed as the label.
    4. Evaluate with a genuine held-out test split + precision/recall
       (fraud detection is a class-imbalance problem - accuracy alone would
       be misleading, since "always predict not-fraud" scores high accuracy
       on a low base rate).
    5. Register the trained model via ml/model_registry.py rather than
       overwriting anything in place.

MINIMUM_LABELS is set conservatively - a few hundred examples is still thin
for a fraud classifier, but it's enough to get a first honest read on
whether the rule-based heuristic and a trained model actually disagree in
practice, which is valuable information on its own even before the trained
model is good enough to deploy.
"""
from __future__ import annotations

MINIMUM_LABELS = 200


def main() -> None:
    from app.db import store

    labeled_count = store.count_labeled_outcomes("actual_fraud_confirmed")
    if labeled_count < MINIMUM_LABELS:
        print(
            f"Only {labeled_count} confirmed fraud outcomes recorded "
            f"(need >= {MINIMUM_LABELS}). Not training - a model trained on "
            f"fewer labels than this would be more noise than signal, and "
            f"shipping it would repeat the exact mistake this project "
            f"already caught once (presenting something as ML that isn't "
            f"reliable enough to earn that label). Keep confirming outcomes "
            f"via PATCH /api/v1/returns/{{id}}/outcome and re-run this later."
        )
        return

    # ── From here on is the real training path — deliberately not run     ──
    # ── or claimed-complete until MINIMUM_LABELS is actually met.          ──
    raise NotImplementedError(
        "Enough labels exist now - implement the training path described "
        "in this file's docstring (pull labeled data, build features via "
        "ml/preprocessor.py, train + evaluate with a proper held-out split, "
        "register via ml/model_registry.py). Do not skip the precision/"
        "recall evaluation step for the sake of shipping faster - a fraud "
        "classifier's accuracy number is close to meaningless on its own "
        "given how imbalanced fraud/not-fraud almost certainly is here."
    )


if __name__ == "__main__":
    main()
