"""
Centralized structured logging for ReturnIQ Enterprise (Phase 8.7)

All logs are emitted as JSON so they can be ingested by:
  - Docker log driver -> Loki / CloudWatch / Papertrail
  - Filebeat -> Elasticsearch
  - Fluentd/Fluent Bit -> any target

Every log line includes: timestamp, level, logger, message, request_id, extras.
"""
from __future__ import annotations

import json
import logging
import sys
import time
import uuid
from contextvars import ContextVar
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="")


class JSONFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log: dict[str, Any] = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": request_id_var.get("") or getattr(record, "request_id", ""),
        }
        skip = {
            "args","created","exc_info","exc_text","filename","funcName",
            "levelname","levelno","lineno","message","module","msecs",
            "msg","name","pathname","process","processName","relativeCreated",
            "stack_info","thread","threadName","taskName",
        }
        for k, v in record.__dict__.items():
            if k not in skip and not k.startswith("_"):
                log[k] = v
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)
        return json.dumps(log, default=str)


def configure_logging(log_level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(log_level)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root.handlers.clear()
    root.addHandler(handler)
    for noisy in ["uvicorn.access", "sqlalchemy.engine", "passlib"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Assigns a unique request ID to every request and logs structured access logs."""

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = request_id_var.set(req_id)
        # PHASE 9: begin span collection for this request. Imported here
        # rather than at module scope because tracing imports request_id_var
        # from this module -- a top-level import would be circular.
        from app.core.tracing import log_trace, start_trace
        start_trace()
        try:
            start = time.perf_counter()
            response = await call_next(request)
            latency_ms = (time.perf_counter() - start) * 1000
            logging.getLogger("returniq.access").info(
                "%s %s %d",
                request.method, request.url.path, response.status_code,
                extra={
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "latency_ms": round(latency_ms, 2),
                    "client_ip": request.client.host if request.client else "",
                },
            )
            # Span breakdown, so a slow request names its own cause in the
            # logs instead of requiring someone to reproduce it.
            log_trace(latency_ms, method=request.method, path=request.url.path)
            response.headers["X-Request-ID"] = req_id
            return response
        finally:
            request_id_var.reset(token)


# Backward-compatible alias. The pre-Phase-8 codebase referred to this class
# as RequestIdMiddleware (lowercase 'd'); main.py and any external code still
# import that name. Keeping both names pointing at one class avoids either a
# breaking rename across the codebase or - worse - two copies of the same
# middleware both running and assigning conflicting request IDs.
RequestIdMiddleware = RequestIDMiddleware
