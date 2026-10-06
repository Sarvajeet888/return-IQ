"""PHASE 40 — restore integrity verification.

The property under test: a restore that looks structurally fine (right
tables, right row counts) but silently has wrong data in it must be caught,
not waved through by a check that only counted rows.
"""
from __future__ import annotations

import pytest

from app.services.backup_integrity import build_manifest, verify_restore


def _rows(n: int, *, id_prefix: str = "r", value: int = 100) -> list[dict]:
    return [{"id": f"{id_prefix}{i}", "amount_minor": value} for i in range(n)]


# ──────────────────────────── the honest baseline ─────────────────────────────

def test_an_identical_restore_verifies_cleanly():
    before = build_manifest(
        {"return_requests": _rows(50), "orgs": _rows(3)},
        primary_keys={"return_requests": "id", "orgs": "id"},
    )
    after = build_manifest(
        {"return_requests": _rows(50), "orgs": _rows(3)},
        primary_keys={"return_requests": "id", "orgs": "id"},
    )
    result = verify_restore(before, after)
    assert result.passed is True
    assert result.failures == []


def test_row_order_does_not_affect_the_hash():
    """A restore reading rows back in a different physical order than the
    backup wrote them must not be flagged as corrupted — that would train
    operators to distrust a genuinely correct restore."""
    rows = _rows(20)
    before = build_manifest({"t": rows}, primary_keys={"t": "id"})
    after = build_manifest({"t": list(reversed(rows))}, primary_keys={"t": "id"})
    assert verify_restore(before, after).passed is True


# ─────────────────── the finding: row count alone is insufficient ────────────

def test_row_count_matching_alone_is_insufficient():
    """THE case this module exists to catch.

    A restore can produce exactly the right NUMBER of rows in a table with
    the wrong data in at least one of them — a plain `SELECT COUNT(*)`
    check, which is common in disaster-recovery scripts, would report this
    restore as successful.
    """
    before = build_manifest({"t": _rows(10, value=100)}, primary_keys={"t": "id"})
    after = build_manifest(
        {"t": _rows(10, value=999)},  # same 10 rows, same ids, wrong amounts
        primary_keys={"t": "id"},
    )
    result = verify_restore(before, after)
    assert result.passed is False
    finding = result.failures[0]
    assert finding.status == "content_mismatch"
    assert "right NUMBER of rows with the wrong data" in finding.detail


def test_row_count_mismatch_is_reported_with_the_exact_difference():
    before = build_manifest({"t": _rows(500)}, primary_keys={"t": "id"})
    after = build_manifest({"t": _rows(497)}, primary_keys={"t": "id"})
    finding = verify_restore(before, after).failures[0]
    assert finding.status == "row_count_mismatch"
    assert "-3" in finding.detail


# ───────────────────── a table missing entirely is not skipped ───────────────

def test_a_table_absent_from_the_restore_is_a_named_failure():
    """The critical failure mode: iterating only over what exists in the
    'after' snapshot would silently skip a table that failed to restore at
    all, because there is nothing on that side to iterate over."""
    before = build_manifest(
        {"return_requests": _rows(100), "orgs": _rows(2)},
        primary_keys={"return_requests": "id", "orgs": "id"},
    )
    after = build_manifest({"orgs": _rows(2)}, primary_keys={"orgs": "id"})

    result = verify_restore(before, after)
    assert result.passed is False
    failure = next(f for f in result.failures if f.table == "return_requests")
    assert failure.status == "missing_table"
    assert "does not exist after restore at all" in failure.detail


def test_an_unexpected_new_table_is_reported_not_ignored():
    before = build_manifest({"orgs": _rows(2)}, primary_keys={"orgs": "id"})
    after = build_manifest(
        {"orgs": _rows(2), "mystery_table": _rows(5)},
        primary_keys={"orgs": "id", "mystery_table": "id"},
    )
    result = verify_restore(before, after)
    new = next(f for f in result.findings if f.table == "mystery_table")
    assert new.status == "new_table"


# ─────────────────────────────── the verdict ──────────────────────────────────

def test_the_verdict_explicitly_warns_against_resuming_traffic():
    before = build_manifest({"t": _rows(10)}, primary_keys={"t": "id"})
    after = build_manifest({"t": _rows(8)}, primary_keys={"t": "id"})
    verdict = verify_restore(before, after).as_dict()["verdict"]
    assert "Do not resume" in verdict


def test_a_clean_restore_states_every_table_matches():
    before = build_manifest({"a": _rows(5), "b": _rows(5)},
                            primary_keys={"a": "id", "b": "id"})
    after = build_manifest({"a": _rows(5), "b": _rows(5)},
                           primary_keys={"a": "id", "b": "id"})
    verdict = verify_restore(before, after).as_dict()["verdict"]
    assert "verified" in verdict.lower()


def test_multiple_failures_are_all_reported_not_just_the_first():
    """Fixing one problem and re-running to discover the next is how a
    disaster recovery drill takes all night."""
    before = build_manifest(
        {"a": _rows(10), "b": _rows(10), "c": _rows(10)},
        primary_keys={"a": "id", "b": "id", "c": "id"},
    )
    after = build_manifest(
        {"a": _rows(8), "b": _rows(10, value=999)},  # c missing, a short, b corrupted
        primary_keys={"a": "id", "b": "id"},
    )
    result = verify_restore(before, after)
    assert len(result.failures) == 3
    statuses = {f.table: f.status for f in result.failures}
    assert statuses["a"] == "row_count_mismatch"
    assert statuses["b"] == "content_mismatch"
    assert statuses["c"] == "missing_table"


# ─────────────────────────── manifest construction ────────────────────────────

def test_manifest_requires_an_explicit_primary_key_per_table():
    """Guessing a default (e.g. always 'id') would silently hash rows in an
    unstable order on a table keyed differently, producing false mismatches
    on data that is actually identical."""
    rows = [{"return_id": "x1", "v": 1}, {"return_id": "x2", "v": 2}]
    m = build_manifest({"custom": rows}, primary_keys={"custom": "return_id"})
    assert m.tables["custom"].row_count == 2


def test_an_empty_table_is_still_fingerprinted_consistently():
    a = build_manifest({"t": []}, primary_keys={"t": "id"})
    b = build_manifest({"t": []}, primary_keys={"t": "id"})
    assert verify_restore(a, b).passed is True
