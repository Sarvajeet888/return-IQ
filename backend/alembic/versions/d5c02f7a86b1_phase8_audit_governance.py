"""Phase 8: audit governance — categories, resource identity, hash chain

Revision ID: d5c02f7a86b1
Revises: c4a91e8b52f0
Create Date: 2026-08-14

Adds the columns that turn `audit_logs` from a skimmable activity feed into
something you can investigate with, and chains events so tampering is
detectable.

EXISTING ROWS
-------------
Historical events predate the chain and cannot be retro-hashed honestly: we
have no evidence they were not already altered, and computing hashes for them
now would manufacture exactly the assurance this feature is supposed to
provide. They are left with NULL prev_hash/event_hash and are explicitly
excluded from verification, so the chain's guarantee starts at this migration
and says so.

`category` defaults to 'business' for existing rows, which is accurate for the
majority (approvals, invitations, exports) and imprecise for a few login
events. Backfilling by pattern-matching `action` strings was considered and
rejected -- a guess recorded as fact in an audit table is worse than a
conservative default.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "d5c02f7a86b1"
down_revision = "c4a91e8b52f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "audit_logs",
        sa.Column("category", sa.String(length=16), nullable=False, server_default="business"),
    )
    op.add_column("audit_logs", sa.Column("resource_type", sa.String(length=50), nullable=True))
    op.add_column("audit_logs", sa.Column("resource_id", sa.String(length=64), nullable=True))
    # 45 chars: an IPv4-mapped IPv6 address is the longest realistic form.
    op.add_column("audit_logs", sa.Column("ip_address", sa.String(length=45), nullable=True))
    op.add_column("audit_logs", sa.Column("user_agent", sa.String(length=256), nullable=True))
    op.add_column("audit_logs", sa.Column("request_id", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("changes", sa.JSON(), nullable=True))
    op.add_column("audit_logs", sa.Column("prev_hash", sa.String(length=64), nullable=True))
    op.add_column("audit_logs", sa.Column("event_hash", sa.String(length=64), nullable=True))

    op.create_index("ix_audit_logs_category", "audit_logs", ["category"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_event_hash", "audit_logs", ["event_hash"])

    # "Everything this user did to this return" is the question an
    # investigation actually asks, so index the pair rather than each column
    # separately.
    op.create_index(
        "ix_audit_logs_resource",
        "audit_logs",
        ["resource_type", "resource_id"],
    )

    # NOTE: the (org_id, created_at) composite index that the append path
    # needs already exists -- migration d9e2f4a7b831 created it. Creating it
    # again fails on a fresh database, which is how this was caught. Verified
    # rather than assumed before removing it from here.


def downgrade() -> None:
    for name in (
        "ix_audit_logs_resource",
        "ix_audit_logs_event_hash",
        "ix_audit_logs_request_id",
        "ix_audit_logs_action",
        "ix_audit_logs_category",
    ):
        op.drop_index(name, table_name="audit_logs")

    for column in (
        "event_hash", "prev_hash", "changes", "request_id",
        "user_agent", "ip_address", "resource_id", "resource_type", "category",
    ):
        op.drop_column("audit_logs", column)
