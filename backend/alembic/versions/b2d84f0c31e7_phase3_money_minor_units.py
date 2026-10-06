"""Phase 3: money as integer minor units + explicit currency

Revision ID: b2d84f0c31e7
Revises: a1c58d0e7fb2
Create Date: 2026-08-13

WHY
---
Every monetary column was a SQL Float. Binary floating point cannot represent
0.10 exactly, so summed refunds and courier remittances drift. At merchant
scale (10k refunds of Rs 19.99) the total comes out as 199899.99999999997
instead of 199900.00 -- a discrepancy with no traceable cause, in a product
whose entire job is reconciliation.

Additionally, currency was encoded in column *names* (predicted_cost_inr).
That made Phase 43 globalisation a full-schema rewrite. Currency is now an
explicit column.

MIGRATION STRATEGY
------------------
Add-backfill-verify-drop, not a bare ALTER TYPE:

  1. add the new *_minor BigInteger columns as NULLable
  2. add currency columns defaulting to INR (all existing data is Indian)
  3. backfill by ROUNDing the float major value * 100 to an integer
  4. VERIFY -- abort the whole migration if any row failed to convert
  5. drop the old float columns
  6. tighten NOT NULL where the original column was NOT NULL

Step 4 matters. A silent partial backfill would leave zeroed money in
production. Better to fail the deploy.

ROUNDING NOTE
-------------
ROUND(value * 100) is half-up in PostgreSQL for the numeric type. We cast to
numeric first, because rounding a float8 uses banker's rounding and would send
a stored 0.005 to 0 instead of 1 paisa. The cast is not cosmetic.

BigInteger, not Integer: INR paise for a large enterprise merchant's annual
recovery total will exceed 2^31 (about Rs 2.1 crore). BigInt costs 4 extra
bytes and removes the ceiling entirely.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "b2d84f0c31e7"
down_revision = "a1c58d0e7fb2"
branch_labels = None
depends_on = None


# (table, old_float_column, new_minor_column, was_nullable)
MONEY_COLUMNS: list[tuple[str, str, str, bool]] = [
    ("orgs", "total_revenue_saved", "total_revenue_saved_minor", False),
    ("return_requests", "item_value", "item_value_minor", False),
    ("predictions", "predicted_cost_inr", "predicted_cost_minor", False),
    ("predictions", "resale_value_estimate", "resale_value_estimate_minor", False),
    ("prediction_outcomes", "actual_cost_inr", "actual_cost_minor", True),
    ("prediction_outcomes", "actual_resale_price_inr", "actual_resale_price_minor", True),
    ("customers", "clv", "clv_minor", False),
    ("cod_risk_assessments", "order_value", "order_value_minor", False),
    ("courier_remittances", "remitted_amount", "remitted_amount_minor", False),
    ("courier_remittances", "expected_amount", "expected_amount_minor", True),
    ("courier_remittances", "discrepancy_amount", "discrepancy_amount_minor", True),
]

# Tables that gain a currency column. Kept separate: resale_value_estimate and
# predicted_cost live on the same table and share one currency column.
CURRENCY_TABLES: list[str] = [
    "orgs",
    "return_requests",
    "predictions",
    "prediction_outcomes",
    "customers",
    "cod_risk_assessments",
    "courier_remittances",
]


def upgrade() -> None:
    bind = op.get_bind()
    # SQLite cannot ALTER COLUMN or ADD CONSTRAINT in place; Alembic's batch
    # mode emulates it by rebuilding the table. Postgres does support them
    # natively, and a table rebuild there would be needlessly expensive on a
    # large table -- so the strategy is chosen per dialect rather than
    # applying the slow path everywhere.
    is_sqlite = bind.dialect.name == "sqlite"

    # ---- 1 & 2: add new columns, all nullable for now -----------------------
    for table, _old, new, _was_nullable in MONEY_COLUMNS:
        op.add_column(table, sa.Column(new, sa.BigInteger(), nullable=True))

    for table in CURRENCY_TABLES:
        op.add_column(
            table,
            sa.Column(
                "currency",
                sa.String(length=3),
                nullable=False,
                server_default="INR",
            ),
        )

    # ---- 3: backfill --------------------------------------------------------
    # Cast to numeric before ROUND so we get half-up, not float8 banker's
    # rounding. INR has exponent 2, and every existing row is INR.
    for table, old, new, _was_nullable in MONEY_COLUMNS:
        op.execute(
            f"UPDATE {table} "
            f"SET {new} = ROUND(CAST({old} AS numeric) * 100) "
            f"WHERE {old} IS NOT NULL"
        )

    # ---- 4: verify, or abort ------------------------------------------------
    problems: list[str] = []
    for table, old, new, _was_nullable in MONEY_COLUMNS:
        unconverted = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE {old} IS NOT NULL AND {new} IS NULL"
            )
        ).scalar_one()
        if unconverted:
            problems.append(f"{table}.{old}: {unconverted} rows failed to convert")

        # Round-trip check: the new integer must reproduce the old float to
        # within half a paisa. Anything worse means the source data was not
        # what we assumed.
        drifted = bind.execute(
            sa.text(
                f"SELECT COUNT(*) FROM {table} "
                f"WHERE {old} IS NOT NULL "
                f"AND ABS(CAST({old} AS numeric) - ({new} / 100.0)) > 0.005"
            )
        ).scalar_one()
        if drifted:
            problems.append(f"{table}.{old}: {drifted} rows drifted beyond half a paisa")

    if problems:
        raise RuntimeError(
            "Money migration aborted -- refusing to drop the float columns "
            "while conversions are incomplete:\n  " + "\n  ".join(problems)
        )

    # ---- 5 & 6: drop old columns, restore NOT NULL --------------------------
    if is_sqlite:
        # One batch per table: each batch rebuilds the table, so doing all of
        # that table's changes together means one rebuild instead of several.
        tables = {t for t, _o, _n, _w in MONEY_COLUMNS}
        for table in tables:
            cols = [c for c in MONEY_COLUMNS if c[0] == table]
            with op.batch_alter_table(table) as batch:
                for _t, old, _new, _was_nullable in cols:
                    batch.drop_column(old)
                for _t, _old, new, was_nullable in cols:
                    if not was_nullable:
                        batch.alter_column(
                            new, existing_type=sa.BigInteger(), nullable=False
                        )
    else:
        for table, old, _new, _was_nullable in MONEY_COLUMNS:
            op.drop_column(table, old)
        for table, _old, new, was_nullable in MONEY_COLUMNS:
            if not was_nullable:
                op.alter_column(
                    table, new, existing_type=sa.BigInteger(), nullable=False
                )

    # Currency must be a known ISO-4217 code. A CHECK constraint here is worth
    # more than application validation alone -- it survives bad imports and
    # direct SQL fixes.
    _CURRENCY_CHECK = (
        "currency IN ('INR','USD','EUR','GBP','AED','JPY','KWD','BHD','OMR')"
    )
    for table in CURRENCY_TABLES:
        if is_sqlite:
            with op.batch_alter_table(table) as batch:
                batch.create_check_constraint(
                    f"ck_{table}_currency_iso4217", _CURRENCY_CHECK
                )
        else:
            op.create_check_constraint(
                f"ck_{table}_currency_iso4217", table, _CURRENCY_CHECK
            )


def downgrade() -> None:
    """Reverse the migration.

    Honest warning: this is lossy in principle. Converting integer paise back
    to float rupees reintroduces the representation error this migration
    exists to remove. It is provided so a failed deploy can roll back, not as
    a supported operating mode.
    """
    is_sqlite = op.get_bind().dialect.name == "sqlite"

    for table in CURRENCY_TABLES:
        if is_sqlite:
            with op.batch_alter_table(table) as batch:
                batch.drop_constraint(f"ck_{table}_currency_iso4217", type_="check")
        else:
            op.drop_constraint(f"ck_{table}_currency_iso4217", table, type_="check")

    for table, old, new, was_nullable in MONEY_COLUMNS:
        op.add_column(table, sa.Column(old, sa.Float(), nullable=True))
        op.execute(f"UPDATE {table} SET {old} = {new} / 100.0 WHERE {new} IS NOT NULL")
        if is_sqlite:
            with op.batch_alter_table(table) as batch:
                if not was_nullable:
                    batch.alter_column(old, existing_type=sa.Float(), nullable=False)
                batch.drop_column(new)
        else:
            if not was_nullable:
                op.alter_column(table, old, existing_type=sa.Float(), nullable=False)
            op.drop_column(table, new)

    for table in CURRENCY_TABLES:
        op.drop_column(table, "currency")
