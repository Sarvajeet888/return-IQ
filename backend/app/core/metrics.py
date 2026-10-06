"""
Prometheus metrics for ReturnIQ Enterprise (Phase 8.6)

Exposes:
  - HTTP request counts, latency histograms (via prometheus-fastapi-instrumentator)
  - ML inference latency
  - Business metrics: predictions, fraud flags, exports, login failures
  - Liveness / readiness endpoints

Add to requirements.txt:
  prometheus-fastapi-instrumentator==6.4.0
"""
from __future__ import annotations

from fastapi import FastAPI

# Guard: if prometheus_client is not installed, metrics are silently disabled
try:
    # generate_latest/CONTENT_TYPE_LATEST are not imported: the
    # Instrumentator's .expose() call renders /metrics for us.
    from prometheus_client import Counter, Gauge, Histogram
    from prometheus_fastapi_instrumentator import Instrumentator
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False

# ── Business Counters ─────────────────────────────────────────────────────────

if _PROMETHEUS_AVAILABLE:
    PREDICTIONS_TOTAL = Counter(
        "returniq_predictions_total",
        "Total AI scoring requests",
        ["routing_decision"],
    )

    LOGIN_FAILURES_TOTAL = Counter(
        "returniq_login_failures_total",
        "Total failed login attempts",
    )

    DATA_EXPORTS_TOTAL = Counter(
        "returniq_data_exports_total",
        "Total data export requests",
        ["export_type"],
    )

    FRAUD_FLAGS_TOTAL = Counter(
        "returniq_fraud_flags_total",
        "Returns flagged as high fraud risk (score > 70)",
    )

    WORKFLOW_RULES_TRIGGERED = Counter(
        "returniq_workflow_rules_triggered_total",
        "Workflow rules that fired",
        ["rule_type"],
    )

    ML_INFERENCE_LATENCY = Histogram(
        "returniq_ml_inference_latency_ms",
        "ML model inference latency in milliseconds",
        buckets=[10, 25, 50, 100, 250, 500, 1000],
    )

    ACTIVE_ORGS = Gauge(
        "returniq_active_orgs",
        "Number of active organisations",
    )


def register_metrics(app: FastAPI) -> None:
    """Attach Prometheus instrumentation to the FastAPI app."""
    if not _PROMETHEUS_AVAILABLE:
        return

    Instrumentator(
        should_group_status_codes=True,
        should_ignore_untemplated=True,
        excluded_handlers=["/metrics", "/health", "/health-fe"],
    ).instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)


def record_prediction(routing_decision: str, latency_ms: float, fraud_score: float) -> None:
    if not _PROMETHEUS_AVAILABLE:
        return
    PREDICTIONS_TOTAL.labels(routing_decision=routing_decision).inc()
    ML_INFERENCE_LATENCY.observe(latency_ms)
    if fraud_score > 70:
        FRAUD_FLAGS_TOTAL.inc()


def record_login_failure() -> None:
    if _PROMETHEUS_AVAILABLE:
        LOGIN_FAILURES_TOTAL.inc()


def record_export(export_type: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        DATA_EXPORTS_TOTAL.labels(export_type=export_type).inc()


def record_workflow_trigger(rule_type: str) -> None:
    if _PROMETHEUS_AVAILABLE:
        WORKFLOW_RULES_TRIGGERED.labels(rule_type=rule_type).inc()
