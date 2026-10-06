"""
Database engine & session management.

Uses Postgres in production (DATABASE_URL=postgresql+psycopg2://...), and
falls back to a local SQLite file for development/tests when DATABASE_URL
isn't set. This is a genuine, persistent database — no more in-memory dicts
that wipe on every restart.
"""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

import time

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()


def _resolve_database_url() -> str:
    if settings.DATABASE_URL:
        return settings.DATABASE_URL
    # Dev/demo fallback — still a real, persistent database (a file on disk),
    # unlike the old in-memory dict store which lost everything on restart.
    return "sqlite:///./returniq_dev.db"


DATABASE_URL = _resolve_database_url()

_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


# ── PHASE 9: query instrumentation ───────────────────────────────────────────
#
# Hooked at the engine rather than wrapped around each of the ~90 store
# functions. One place to maintain, no call site can forget it, and it
# captures queries issued by SQLAlchemy internals (lazy loads, flushes) that
# per-function instrumentation would miss entirely -- which are exactly the
# queries nobody knows are happening.
#
# The listeners must be cheap: they run on every statement. They do two
# attribute operations and one subtraction.

def _statement_kind(sql: str) -> str:
    """First keyword only. Full SQL must never become a span name.

    Span names end up in log fields and, eventually, metric labels. A raw
    statement would embed literal values, so a WHERE clause containing an
    email address or an order ID would leak PII into logs and produce
    unbounded label cardinality.
    """
    return (sql or "").lstrip().split(" ", 1)[0].upper()[:12] or "UNKNOWN"


@event.listens_for(engine, "before_cursor_execute")
def _query_start(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault("_query_started", []).append(time.perf_counter())


@event.listens_for(engine, "after_cursor_execute")
def _query_end(conn, cursor, statement, parameters, context, executemany):
    started = conn.info.get("_query_started")
    if not started:
        return
    elapsed_ms = (time.perf_counter() - started.pop()) * 1000

    # Imported lazily: database.py is imported very early during app startup,
    # and a top-level import here would create a cycle through logging_config.
    from app.core.tracing import record_query

    record_query(_statement_kind(statement), elapsed_ms)


class Base(DeclarativeBase):
    pass


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional scope around a series of operations."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db() -> None:
    """Create tables if they don't exist (used for SQLite/dev + tests).
    In production, Alembic migrations (see backend/alembic/) are the source
    of truth — this call is a harmless no-op if tables already exist.
    """
    from app.db import models  # noqa: F401  (ensure models are registered)
    Base.metadata.create_all(bind=engine)
