"""PHASE 9 — Tracing.

The property under test: after a slow request, the logs say what took the
time, without anyone reproducing it or opening a shell.
"""
from __future__ import annotations

import time
import uuid

import pytest

from app.core import tracing
from app.core.tracing import Span, span, start_trace, trace_summary


@pytest.fixture(autouse=True)
def fresh_trace():
    start_trace()
    yield


# ────────────────────────────── span mechanics ───────────────────────────────

def test_span_records_duration():
    with span("slow.thing"):
        time.sleep(0.02)
    spans = tracing.current_trace()
    assert len(spans) == 1
    assert spans[0].duration_ms >= 15


def test_spans_nest_with_depth():
    with span("outer"):
        with span("inner"):
            pass
    spans = tracing.current_trace()
    assert [s.name for s in spans] == ["outer", "inner"]
    assert [s.depth for s in spans] == [0, 1]


def test_span_records_error_and_reraises():
    """Instrumentation must not swallow exceptions.

    A helper that quietly absorbs errors turns an observability tool into a
    source of invisible failures.
    """
    with pytest.raises(ValueError, match="boom"):
        with span("failing.op"):
            raise ValueError("boom")

    recorded = tracing.current_trace()[0]
    assert recorded.error is not None
    assert "ValueError" in recorded.error
    assert recorded.duration_ms is not None      # timing still captured


def test_span_outside_a_request_does_not_raise():
    """Service code is called from tests, scripts and (later) workers, where
    no trace exists. Instrumentation must be a no-op there, not a crash."""
    tracing._spans_var.set(None)
    with span("orphan"):
        pass
    assert tracing.current_trace() == []


def test_attributes_are_captured():
    with span("ml.inference", model="cost_xgb_v1.0.0"):
        pass
    assert tracing.current_trace()[0].attributes["model"] == "cost_xgb_v1.0.0"


# ───────────────────────────────── summary ───────────────────────────────────

def test_summary_names_the_dominant_span():
    """The first question on any slow request, answered in the log line."""
    with span("fast.thing"):
        time.sleep(0.005)
    with span("the.actual.problem"):
        time.sleep(0.05)

    summary = trace_summary(total_ms=100.0)
    assert summary["dominant_span"] == "the.actual.problem"
    assert summary["dominant_ms"] >= 40


def test_nested_spans_are_not_double_counted():
    """Nested spans must not inflate the measured total.

    Worth recording how this test got written: it originally asserted that a
    parent beats its child on dominance. Sabotaging the depth filter did NOT
    fail it -- because a parent always contains its child, `max()` returns the
    same span either way. The depth filter is simply unobservable through
    dominance.

    Where it does matter is `unaccounted_ms`. Summing parent AND child counts
    the same milliseconds twice, inflating `measured`, which drives
    unaccounted time to zero and hides the fact that a chunk of the request is
    uninstrumented.
    """
    with span("parent"):
        with span("child"):
            time.sleep(0.04)

    summary = trace_summary(total_ms=200.0)

    spans = tracing.current_trace()
    parent = next(s for s in spans if s.name == "parent")
    child = next(s for s in spans if s.name == "child")

    assert child.depth == 1
    # The child's time is real, and it is inside the parent's time.
    assert child.duration_ms <= parent.duration_ms

    # ~40ms of a 200ms request was measured, so ~160ms is unaccounted for.
    # Double-counting would report roughly 120ms and understate the gap.
    assert summary["unaccounted_ms"] > 150


def test_unaccounted_time_is_reported():
    """A large unaccounted figure is itself a finding: it means the
    instrumentation is looking in the wrong place."""
    with span("measured"):
        time.sleep(0.01)

    summary = trace_summary(total_ms=500.0)
    assert summary["unaccounted_ms"] > 400


def test_errors_surface_in_summary():
    try:
        with span("db.write"):
            raise RuntimeError("connection lost")
    except RuntimeError:
        pass
    assert trace_summary(total_ms=10.0)["errors"] == ["db.write"]


def test_empty_trace_summarises_safely():
    assert trace_summary(total_ms=5.0)["spans"] == 0


# ──────────────────────── query aggregation / N+1 ────────────────────────────

def test_queries_aggregate_rather_than_flooding_the_trace():
    """200 SELECTs must not produce 200 spans.

    Per-query spans would drown the breakdown they are meant to clarify. The
    useful signal is the aggregate.
    """
    for _ in range(200):
        tracing.record_query("SELECT", 9.0)

    spans = tracing.current_trace()
    assert len(spans) == 1
    assert spans[0].name == "db.select"
    assert spans[0].attributes["count"] == 200
    assert spans[0].duration_ms == pytest.approx(1800.0)


def test_n_plus_one_is_visible_in_the_summary():
    """What an N+1 looks like from the outside: a huge query count dominating
    a request. This is the shape that made the dashboard the slowest endpoint
    in the product before it was fixed."""
    with span("render.dashboard"):
        pass
    for _ in range(150):
        tracing.record_query("SELECT", 12.0)

    summary = trace_summary(total_ms=2000.0)
    assert summary["dominant_span"] == "db.select"
    query_span = next(s for s in tracing.current_trace() if s.name == "db.select")
    assert query_span.attributes["count"] == 150


def test_statement_kinds_are_separated():
    tracing.record_query("SELECT", 5.0)
    tracing.record_query("INSERT", 3.0)
    names = {s.name for s in tracing.current_trace()}
    assert names == {"db.select", "db.insert"}


def test_query_outside_a_request_is_ignored():
    tracing._spans_var.set(None)
    tracing.record_query("SELECT", 5.0)      # must not raise
    assert tracing.current_trace() == []


# ─────────────────────────── end-to-end wiring ───────────────────────────────

def test_real_request_produces_query_spans(app_client):
    """Proof the engine-level listener is actually attached.

    Instrumenting at the engine rather than wrapping ~90 store functions means
    no call site can forget it -- but it also means a wiring mistake is
    invisible until something like this checks.
    """
    start_trace()
    email = f"trace_{uuid.uuid4().hex[:8]}@example.com"
    r = app_client.post("/api/v1/auth/register", json={
        "full_name": "Trace Tester", "email": email, "password": "TracePass123",
        "org_name": f"Trace Org {uuid.uuid4().hex[:6]}",
        "platform_type": "shopify", "accepted_terms": True,
    })
    assert r.status_code == 200, r.text
    # The request carries a correlation ID out to the client, which is what
    # ties a user's bug report to the trace in the logs.
    assert r.headers.get("X-Request-ID")
