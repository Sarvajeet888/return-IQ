"""
Migration integrity tests (Phase 11).

The rest of the suite builds its schema from the SQLAlchemy models, which
means a broken Alembic migration passes every other test while making a
fresh production deployment impossible.

That is exactly what happened: the Phase 8 index migration created an index
on `prediction_outcomes.return_request_id`, a column that does not exist
(it is `prediction_id`). Every test passed. `alembic upgrade head` on a new
database failed outright, so no new deployment could start.
"""
from __future__ import annotations
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _alembic(args: list[str], db_url: str):
    env = {
        **os.environ,
        "DATABASE_URL": db_url,
        "SECRET_KEY": "migration-test-secret-not-for-production-use-only",
        "API_KEY_HASH_PEPPER": "migration-test-pepper-not-for-production-only",
        "ENVIRONMENT": "test",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=BACKEND_DIR, env=env, capture_output=True, text=True, timeout=180,
    )


@pytest.fixture
def fresh_db():
    with tempfile.TemporaryDirectory() as d:
        yield f"sqlite:///{d}/migration_test.db"


def test_upgrade_head_succeeds_on_fresh_database(fresh_db):
    """
    The single most important migration test: can a brand-new deployment
    build its schema at all?
    """
    r = _alembic(["upgrade", "head"], fresh_db)
    assert r.returncode == 0, (
        "DEPLOYMENT BLOCKER: `alembic upgrade head` failed on a fresh database. "
        "No new environment can be provisioned.\n\n"
        f"stdout:\n{r.stdout}\n\nstderr:\n{r.stderr}"
    )


def test_full_downgrade_and_re_upgrade(fresh_db):
    """Every migration must be reversible - this is what a rollback relies on."""
    up = _alembic(["upgrade", "head"], fresh_db)
    assert up.returncode == 0, up.stderr

    down = _alembic(["downgrade", "base"], fresh_db)
    assert down.returncode == 0, (
        f"downgrade to base failed - rollback would not work:\n{down.stderr}"
    )

    re_up = _alembic(["upgrade", "head"], fresh_db)
    assert re_up.returncode == 0, (
        f"re-upgrade after full downgrade failed:\n{re_up.stderr}"
    )


def test_single_step_downgrade_works(fresh_db):
    """`alembic downgrade -1` is the documented rollback command."""
    assert _alembic(["upgrade", "head"], fresh_db).returncode == 0
    r = _alembic(["downgrade", "-1"], fresh_db)
    assert r.returncode == 0, f"single-step downgrade failed:\n{r.stderr}"


def test_migrated_schema_matches_orm_models(fresh_db):
    """
    Catches schema drift in the other direction: a column added to a model
    but never migrated, or migrated under a different name.

    This is the failure mode that silently broke customer blacklisting -
    is_blacklisted existed in the migration but not the model, so writes
    were dropped by store.update_customer()'s hasattr() filter.
    """
    assert _alembic(["upgrade", "head"], fresh_db).returncode == 0

    from sqlalchemy import create_engine, inspect
    from app.db.models import Base

    engine = create_engine(fresh_db)
    inspector = inspect(engine)
    db_tables = set(inspector.get_table_names())

    mismatches = []
    for table_name, table in Base.metadata.tables.items():
        if table_name not in db_tables:
            mismatches.append(f"table '{table_name}' is in the models but not the migrations")
            continue
        db_cols = {c["name"] for c in inspector.get_columns(table_name)}
        model_cols = {c.name for c in table.columns}

        missing = model_cols - db_cols
        if missing:
            mismatches.append(
                f"{table_name}: columns in model but NOT in migrated schema: {sorted(missing)}"
            )

    assert not mismatches, "SCHEMA DRIFT between ORM models and migrations:\n  " + "\n  ".join(mismatches)


def test_no_duplicate_revision_ids():
    """Two migrations sharing a revision id corrupts the chain."""
    versions = BACKEND_DIR / "alembic" / "versions"
    revisions = []
    for f in versions.glob("*.py"):
        for line in f.read_text().splitlines():
            if line.strip().startswith("revision =") and "down_revision" not in line:
                revisions.append(line.split("=")[1].strip().strip("'\""))
                break
    dupes = {r for r in revisions if revisions.count(r) > 1}
    assert not dupes, f"duplicate alembic revision ids: {dupes}"
