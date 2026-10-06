"""Phase 5: account tokens for invitation and email verification

Revision ID: c4a91e8b52f0
Revises: b2d84f0c31e7
Create Date: 2026-08-14

Replaces the emailed-temporary-password invitation flow with single-use,
purpose-scoped, hash-stored tokens.

Only the SHA-256 hash of a token is persisted, so read access to this table
(a backup leak, SQL injection, a curious operator) cannot be converted into
account access. `purpose` is part of the primary lookup rather than metadata:
without it, a token minted for email verification could be replayed against
the invitation endpoint to set a password on somebody else's account.

Existing users are untouched. Accounts previously created with a temporary
password keep working; the audit note below records why they should still be
reviewed.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "c4a91e8b52f0"
down_revision = "b2d84f0c31e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_tokens",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index("ix_account_tokens_user_id", "account_tokens", ["user_id"])
    op.create_index("ix_account_tokens_purpose", "account_tokens", ["purpose"])

    # Consuming a token filters on hash + purpose + used_at + expires_at in a
    # single UPDATE. A composite index means that lookup stays one index probe
    # rather than a scan as the table accumulates spent tokens.
    op.create_index(
        "ix_account_tokens_lookup",
        "account_tokens",
        ["token_hash", "purpose"],
    )


def downgrade() -> None:
    op.drop_index("ix_account_tokens_lookup", table_name="account_tokens")
    op.drop_index("ix_account_tokens_purpose", table_name="account_tokens")
    op.drop_index("ix_account_tokens_user_id", table_name="account_tokens")
    op.drop_table("account_tokens")
