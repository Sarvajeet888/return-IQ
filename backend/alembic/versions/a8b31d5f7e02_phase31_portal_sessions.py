"""Phase 31: portal sessions (customer return portal)

Revision ID: a8b31d5f7e02
Revises: f7a24c9e30b5
Create Date: 2026-08-20

Scoped, short-lived access for customers who have no account.

Only the SHA-256 hash of the token is stored — this is a credential, and
database read access must not become customer-account access. The customer's
contact detail is deliberately NOT duplicated here: the order row already
holds it, and copying PII into a token table means two places to secure, two
places to purge on a deletion request, and one more place to leak from.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "a8b31d5f7e02"
down_revision = "f7a24c9e30b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "portal_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("return_request_id", sa.String(length=36), nullable=True),
        sa.Column("platform_order_id", sa.String(length=100), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column("client_fingerprint", sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["return_request_id"], ["return_requests.id"]),
        sa.PrimaryKeyConstraint("token_hash"),
    )

    op.create_index("ix_portal_sessions_org_id", "portal_sessions", ["org_id"])
    op.create_index(
        "ix_portal_sessions_return_request_id", "portal_sessions",
        ["return_request_id"],
    )
    op.create_index(
        "ix_portal_sessions_platform_order_id", "portal_sessions",
        ["platform_order_id"],
    )

    # Every portal request resolves a token and must exclude expired rows in
    # the same query. Without this index that check scans the table, on the
    # one endpoint an attacker will call thousands of times.
    op.create_index("ix_portal_sessions_expires_at", "portal_sessions", ["expires_at"])

    # Customer-supplied evidence has no staff uploader. The portal is the
    # first path where a legitimate row genuinely has no user behind it.
    with op.batch_alter_table("return_documents") as batch:
        batch.alter_column(
            "uploaded_by_user_id",
            existing_type=sa.String(length=36),
            nullable=True,
        )
    op.add_column(
        "return_documents",
        sa.Column("customer_statement", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("return_documents", "customer_statement")
    with op.batch_alter_table("return_documents") as batch:
        batch.alter_column(
            "uploaded_by_user_id",
            existing_type=sa.String(length=36),
            nullable=False,
        )

    for name in (
        "ix_portal_sessions_expires_at",
        "ix_portal_sessions_platform_order_id",
        "ix_portal_sessions_return_request_id",
        "ix_portal_sessions_org_id",
    ):
        op.drop_index(name, table_name="portal_sessions")
    op.drop_table("portal_sessions")
