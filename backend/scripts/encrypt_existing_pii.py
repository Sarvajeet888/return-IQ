#!/usr/bin/env python3
"""
One-time backfill: encrypt customer PII that was written before encryption
was enabled.

Run once, after `alembic upgrade head` brings in migration e4b7c1d90a23.

    cd backend
    python3 scripts/encrypt_existing_pii.py --dry-run    # inspect first
    python3 scripts/encrypt_existing_pii.py              # apply

## Why a script and not part of the migration

Alembic migrations run raw SQL. Encryption happens in the SQLAlchemy
TypeDecorator layer, which a migration does not go through. Doing it here also
means it can be run in batches, inspected, and re-run safely.

## Safety

Idempotent. A value that already decrypts cleanly is skipped, so running twice
does not double-encrypt. Take a database backup first anyway - this rewrites
every customer row.

## Reversing

    python3 scripts/encrypt_existing_pii.py --decrypt

Needed before downgrading migration e4b7c1d90a23, which narrows the columns
back to plaintext widths and would otherwise truncate ciphertext.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text  # noqa: E402

from app.core.encryption import (  # noqa: E402
    decrypt_value, encrypt_value, is_encryption_active,
)
from app.db.database import SessionLocal  # noqa: E402

PII_COLUMNS = ("name", "email", "phone")


def _looks_encrypted(value: str | None) -> bool:
    """
    True if the value decrypts to something different from itself, i.e. it is
    already a valid Fernet token. decrypt_value() returns plaintext unchanged,
    so equality means it was never encrypted.
    """
    if not value:
        return False
    return decrypt_value(value) != value


def main() -> int:
    parser = argparse.ArgumentParser(description="Encrypt or decrypt customer PII in place.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Report what would change without writing.")
    parser.add_argument("--decrypt", action="store_true",
                        help="Reverse direction: decrypt back to plaintext.")
    parser.add_argument("--batch", type=int, default=500,
                        help="Rows per commit (default 500).")
    args = parser.parse_args()

    if not is_encryption_active():
        print("ERROR: encryption is not active.")
        print("  Install `cryptography` and ensure SECRET_KEY is set, then retry.")
        return 1

    transform = decrypt_value if args.decrypt else encrypt_value
    direction = "DECRYPT" if args.decrypt else "ENCRYPT"

    print(f"Mode: {direction}{'  (DRY RUN - no writes)' if args.dry_run else ''}")
    print("-" * 60)

    changed = skipped = 0

    with SessionLocal() as db:
        rows = db.execute(
            text("SELECT id, name, email, phone FROM customers")
        ).fetchall()

        print(f"Found {len(rows)} customer rows.\n")

        for i, row in enumerate(rows, start=1):
            row_id = row[0]
            updates = {}

            for offset, col in enumerate(PII_COLUMNS, start=1):
                raw = row[offset]
                if raw is None or raw == "":
                    continue

                already = _looks_encrypted(raw)
                if args.decrypt:
                    if not already:
                        continue          # already plaintext
                    updates[col] = decrypt_value(raw)
                else:
                    if already:
                        continue          # already encrypted
                    updates[col] = encrypt_value(raw)

            if not updates:
                skipped += 1
                continue

            changed += 1
            if args.dry_run:
                print(f"  would update {row_id}: {', '.join(sorted(updates))}")
                continue

            set_clause = ", ".join(f"{c} = :{c}" for c in updates)
            db.execute(
                text(f"UPDATE customers SET {set_clause} WHERE id = :row_id"),
                {**updates, "row_id": row_id},
            )

            if i % args.batch == 0:
                db.commit()
                print(f"  committed through row {i}")

        if not args.dry_run:
            db.commit()

    print("-" * 60)
    print(f"{'Would change' if args.dry_run else 'Changed'}: {changed}")
    print(f"Already correct, skipped: {skipped}")

    if args.dry_run and changed:
        print("\nRe-run without --dry-run to apply. Take a database backup first.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
