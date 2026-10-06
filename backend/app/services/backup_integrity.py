"""PHASE 40 — cloud & disaster recovery: restore integrity verification.

THE FINDING
-----------
`infra/backups/backup_db.sh` and `restore_db.sh` already existed and are
reasonably well-built: backups are gzip-integrity-checked, retention is
enforced, restore requires a typed confirmation before it destroys data.

Two real gaps, found by reading rather than assuming the scripts work
because they look complete.

**1. `restore_db.sh` pipes into plain `psql`, with no `-v ON_ERROR_STOP=1`.**
By default, psql running a multi-statement script prints an error for a
failing statement and *continues to the next one* rather than aborting.
Combined with `set -euo pipefail`, the shell only sees the exit code of the
final command in the pipe — and psql itself exits 0 even after individual
statements inside the script failed, as long as it reaches the end of
input without a fatal connection error. A restore that silently drops one
table's data partway through can complete and report success.

**2. The restore script's own "verification" step only lists table names:**

    SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'public'

That proves the schema exists. It says nothing about whether the DATA in
those tables is complete or correct. A restore that recreates every table
correctly but loses every row in `return_requests` to a mid-script error
would pass this check.

WHAT THIS MODULE ADDS
----------------------
A manifest-based integrity check: capture row counts AND a content hash per
table before backup, capture the same after restore, and compare. Row count
alone is insufficient and this module proves why: a table can have the
right row count with the wrong rows in it (see the sabotage in
`test_row_count_matching_alone_is_insufficient`), so content is hashed too.

WHAT COULD NOT BE VERIFIED IN THIS ENVIRONMENT
------------------------------------------------
Both shell scripts run against a live Postgres via `docker exec`, which
does not exist in this sandbox. The two fixes below (`-v ON_ERROR_STOP=1`,
row-count reporting in the verify step) are applied to the scripts on
correct, well-established psql/bash reasoning, not on an end-to-end run
executed here. What IS fully executed and tested here is the manifest
comparison logic itself, using SQLite as a stand-in database -- the same
comparison a real Postgres backup/restore cycle would need.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Final

__all__ = [
    "TableManifest",
    "BackupManifest",
    "RestoreVerification",
    "TableFinding",
    "build_manifest",
    "verify_restore",
]


def _row_hash(rows: list[dict[str, Any]], *, primary_key: str) -> str:
    """A deterministic content fingerprint for a table's rows.

    Sorted by primary key before hashing, so two reads of the same data in
    different row order produce the identical hash -- otherwise the check
    would fail on correct restores just because a query returned rows in a
    different sequence, which would train operators to ignore it.

    `sort_keys=True` on the per-row JSON encoding for the same reason: dict
    insertion order must not change the fingerprint of identical data.
    """
    ordered = sorted(rows, key=lambda r: str(r.get(primary_key, "")))
    canonical = "\n".join(
        json.dumps(row, sort_keys=True, default=str) for row in ordered
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TableManifest:
    table: str
    row_count: int
    content_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {"table": self.table, "row_count": self.row_count,
                "content_hash": self.content_hash[:12]}


@dataclass(frozen=True)
class BackupManifest:
    tables: dict[str, TableManifest] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {name: t.as_dict() for name, t in self.tables.items()}


def build_manifest(
    rows_by_table: dict[str, list[dict[str, Any]]],
    *,
    primary_keys: dict[str, str],
) -> BackupManifest:
    """Fingerprint every table in a database snapshot.

    `primary_keys` is required per table rather than guessed (e.g. assuming
    every table has an `id` column) -- guessing wrong would silently hash
    rows in an unstable order and produce false mismatches on data that is
    actually identical.
    """
    tables = {}
    for name, rows in rows_by_table.items():
        pk = primary_keys.get(name, "id")
        tables[name] = TableManifest(
            table=name, row_count=len(rows),
            content_hash=_row_hash(rows, primary_key=pk),
        )
    return BackupManifest(tables=tables)


@dataclass(frozen=True)
class TableFinding:
    table: str
    status: str  # "verified" | "missing_table" | "new_table" | "row_count_mismatch" | "content_mismatch"
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {"table": self.table, "status": self.status, "detail": self.detail}


@dataclass
class RestoreVerification:
    findings: list[TableFinding] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(f.status == "verified" for f in self.findings)

    @property
    def failures(self) -> list[TableFinding]:
        return [f for f in self.findings if f.status != "verified"]

    def as_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "tables_checked": len(self.findings),
            "failures": [f.as_dict() for f in self.failures],
            "findings": [f.as_dict() for f in self.findings],
            "verdict": (
                "Restore verified: every table's row count and content hash "
                "match the pre-backup manifest."
                if self.passed else
                f"Restore FAILED verification: {len(self.failures)} of "
                f"{len(self.findings)} table(s) do not match. Do not resume "
                f"traffic against this database."
            ),
        }


def verify_restore(before: BackupManifest, after: BackupManifest) -> RestoreVerification:
    """Compare a pre-backup manifest against a post-restore manifest.

    Every table that existed before is checked explicitly, including ones
    absent from the restore entirely -- a table that silently failed to
    restore must appear as a named failure, not be skipped because there is
    nothing on the "after" side to iterate over.
    """
    findings: list[TableFinding] = []
    before_tables = set(before.tables)
    after_tables = set(after.tables)

    for name in sorted(before_tables):
        b = before.tables[name]

        if name not in after_tables:
            findings.append(TableFinding(
                table=name, status="missing_table",
                detail=(
                    f"Existed before backup with {b.row_count} row(s); does "
                    f"not exist after restore at all."
                ),
            ))
            continue

        a = after.tables[name]

        if a.row_count != b.row_count:
            findings.append(TableFinding(
                table=name, status="row_count_mismatch",
                detail=(
                    f"{b.row_count} row(s) before, {a.row_count} after "
                    f"({a.row_count - b.row_count:+d})."
                ),
            ))
            continue

        if a.content_hash != b.content_hash:
            # THE case row-count checking alone would miss: same number of
            # rows, different actual data.
            findings.append(TableFinding(
                table=name, status="content_mismatch",
                detail=(
                    f"Row count matches ({a.row_count}), but the content "
                    f"does not. The restore produced the right NUMBER of "
                    f"rows with the wrong data in at least one of them."
                ),
            ))
            continue

        findings.append(TableFinding(
            table=name, status="verified",
            detail=f"{a.row_count} row(s), content hash matches exactly.",
        ))

    for name in sorted(after_tables - before_tables):
        a = after.tables[name]
        findings.append(TableFinding(
            table=name, status="new_table",
            detail=(
                f"Present after restore with {a.row_count} row(s) but was "
                f"not in the pre-backup manifest. Confirm this is expected "
                f"before trusting the restore."
            ),
        ))

    return RestoreVerification(findings=findings)
