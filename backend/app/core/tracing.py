"""PHASE 9 — Tracing, the third observability pillar.

WHAT WAS ALREADY HERE
---------------------
Logs and metrics were both in good shape before this phase: structured JSON
logging with a `request_id` ContextVar, Prometheus counters and histograms for
predictions, login failures, exports and ML latency, and liveness/readiness
endpoints that actually check dependencies.

WHAT WAS MISSING
----------------
The access log records that `POST /api/v1/returns` took 2,400ms. It does not
record *where* those 2,400ms went. Was it the ML model? Three N+1 queries? A
courier API timeout? Answering that today means adding print statements and
redeploying, or SSH-ing into a container and guessing -- which is precisely
the situation Phase 9 exists to end.

WHAT THIS IS
------------
In-process span timing, correlated by request ID. Each span records what it
was, how long it took, and how it nested. On a slow request the log line
names the dominant span, so the first question of any latency investigation
is answered before anyone opens a terminal.

WHAT THIS IS NOT
----------------
This is not distributed tracing. It cannot follow a request across a service
boundary into a worker or a third-party call, because there is no propagation
format and no collector. For that, OpenTelemetry plus a collector (Jaeger,
Tempo, or a hosted backend) is the correct answer, and adopting it is logged
for Phase 40 rather than half-implemented here.

ReturnIQ is currently one FastAPI process talking to Postgres and Redis. For
that topology in-process spans answer nearly every real question, and they
cost no infrastructure. When background workers arrive (Phase 2/38), this
becomes insufficient and should be replaced rather than extended.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Iterator

from app.core.logging_config import request_id_var

logger = logging.getLogger("returniq.trace")

__all__ = ["Span", "current_trace", "span", "start_trace", "trace_summary"]

# Requests that exceed this are logged with a full span breakdown. Below it,
# only the summary line is emitted -- tracing every fast request at full
# detail would cost more in log volume than it returns in insight.
SLOW_REQUEST_MS: float = 500.0


@dataclass
class Span:
    name: str
    started_at: float
    duration_ms: float | None = None
    depth: int = 0
    attributes: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "duration_ms": round(self.duration_ms or 0.0, 2),
            "depth": self.depth,
            **({"error": self.error} if self.error else {}),
            **({"attributes": self.attributes} if self.attributes else {}),
        }


# A list per request rather than a tree: spans record their depth, so the tree
# is reconstructable for display, and appending stays O(1) on the hot path.
_spans_var: ContextVar[list[Span] | None] = ContextVar("trace_spans", default=None)
_depth_var: ContextVar[int] = ContextVar("trace_depth", default=0)


def start_trace() -> list[Span]:
    """Begin collecting spans for the current request."""
    spans: list[Span] = []
    _spans_var.set(spans)
    _depth_var.set(0)
    return spans


def current_trace() -> list[Span]:
    return _spans_var.get() or []


@contextmanager
def span(name: str, **attributes: Any) -> Iterator[Span]:
    """Time a section of work.

    Outside a request (a CLI script, a test calling a service directly) this
    is a no-op beyond the timing itself -- there is no trace to append to. It
    must never raise for that reason: instrumentation that breaks code when
    observability is absent is worse than no instrumentation.
    """
    spans = _spans_var.get()
    depth = _depth_var.get()

    record = Span(name=name, started_at=time.perf_counter(), depth=depth, attributes=dict(attributes))
    if spans is not None:
        spans.append(record)

    depth_token = _depth_var.set(depth + 1)
    try:
        yield record
    except Exception as exc:
        # Record the failure on the span, then re-raise. Swallowing here would
        # turn an instrumentation helper into a silent error handler.
        record.error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        _depth_var.reset(depth_token)
        record.duration_ms = (time.perf_counter() - record.started_at) * 1000


def record_query(kind: str, duration_ms: float) -> None:
    """Record one database statement against the current request.

    Queries are aggregated into a single counter per statement kind rather
    than one span each. A dashboard request issuing 200 SELECTs would produce
    200 spans, drowning the breakdown it is supposed to clarify -- and the
    useful signal is "200 SELECTs totalling 1,800ms", which is what an N+1
    looks like from the outside.
    """
    spans = _spans_var.get()
    if spans is None:
        return

    name = f"db.{kind.lower()}"
    for existing in spans:
        if existing.name == name and existing.depth == 0:
            existing.duration_ms = (existing.duration_ms or 0.0) + duration_ms
            existing.attributes["count"] = existing.attributes.get("count", 1) + 1
            return

    spans.append(Span(
        name=name,
        started_at=time.perf_counter(),
        duration_ms=duration_ms,
        depth=0,
        attributes={"count": 1},
    ))


def trace_summary(total_ms: float) -> dict[str, Any]:
    """Summarise the current trace for logging.

    The key field is `dominant_span`: on a slow request, the first question is
    always "what took the time", and answering it in the log line means an
    engineer does not have to reproduce the request to find out.

    Only top-level (depth 0) spans are considered for dominance. Nested spans
    are contained within their parents, so counting them would double-count
    the same milliseconds and could name a child as dominant over the parent
    that entirely contains it.
    """
    spans = current_trace()
    if not spans:
        return {"total_ms": round(total_ms, 2), "spans": 0}

    top_level = [s for s in spans if s.depth == 0 and s.duration_ms is not None]
    dominant = max(top_level, key=lambda s: s.duration_ms or 0.0, default=None)

    measured = sum(s.duration_ms or 0.0 for s in top_level)

    return {
        "total_ms": round(total_ms, 2),
        "spans": len(spans),
        "dominant_span": dominant.name if dominant else None,
        "dominant_ms": round(dominant.duration_ms, 2) if dominant else None,
        # What the spans did not account for: framework overhead, serialization,
        # or simply uninstrumented code. A large unaccounted figure is itself a
        # finding -- it says the instrumentation is looking in the wrong place.
        "unaccounted_ms": round(max(total_ms - measured, 0.0), 2),
        "errors": [s.name for s in spans if s.error],
    }


def log_trace(total_ms: float, *, method: str = "", path: str = "") -> None:
    """Emit the trace for a completed request.

    Slow requests get the full span breakdown; fast ones get the summary only.
    """
    summary = trace_summary(total_ms)
    if not summary.get("spans"):
        return

    extra: dict[str, Any] = {
        "request_id": request_id_var.get(""),
        "method": method,
        "path": path,
        **summary,
    }

    if total_ms >= SLOW_REQUEST_MS or summary.get("errors"):
        extra["span_detail"] = [s.as_dict() for s in current_trace()]
        logger.warning(
            "Slow request: %s %s took %.0fms (%s dominated)",
            method, path, total_ms, summary.get("dominant_span") or "unknown",
            extra=extra,
        )
    else:
        logger.info("%s %s traced", method, path, extra=extra)
