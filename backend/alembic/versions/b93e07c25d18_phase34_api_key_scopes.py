"""Phase 34: API key scopes, expiry and usage tracking

Revision ID: b93e07c25d18
Revises: a8b31d5f7e02
Create Date: 2026-08-25

Before this, an API key granted everything the external API exposed. A key
given to a read-only analytics vendor could create returns.

THE BACKFILL DECISION
---------------------
Existing keys have no scopes. Two options, and the obvious one is wrong.

**Fail open** (treat NULL as "all scopes") would leave every current key
omnipotent — exactly the state this migration exists to end — and the failure
would be invisible, because everything would keep working.

**Fail closed** (NULL means no permissions) is correct in principle and would
break every live integration silently at deploy, with a 403 that looks like a
credential problem.

So neither: existing keys are **explicitly backfilled** with the read scopes
plus create, matching what the external API actually offered
(`/ext/returns` POST, GET list, GET one, GET dashboard). That preserves
current behaviour for the endpoints that exist while ending the "grants
everything" property for any endpoint added later.

`key_has_permission()` still fails closed for NULL, so a key created outside
this migration path is inert rather than omnipotent.
"""
from __future__ import annotations

import json

import sqlalchemy as sa
from alembic import op

revision = "b93e07c25d18"
down_revision = "a8b31d5f7e02"
branch_labels = None
depends_on = None


# What the external API actually exposed before this migration. Not the full
# scope list -- granting approve/reject to existing keys would hand write
# powers to integrations that never had them.
_LEGACY_SCOPES = [
    "returns.read",
    "returns.create",
    "risk.read",
    "reports.read",
    "ml.read",
]


def upgrade() -> None:
    op.add_column("api_keys", sa.Column("scopes", sa.JSON(), nullable=True))
    op.add_column(
        "api_keys",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "api_keys",
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
    )

    op.create_index("ix_api_keys_expires_at", "api_keys", ["expires_at"])

    # Explicit backfill. See the module docstring for why neither failing
    # open nor failing closed is right for keys that already exist.
    op.execute(
        sa.text("UPDATE api_keys SET scopes = :scopes WHERE scopes IS NULL")
        .bindparams(scopes=json.dumps(_LEGACY_SCOPES))
    )

    # Deliberately no expiry backfill. Setting one on existing keys would
    # break live integrations on a date nobody chose. Existing keys are
    # reported as "no expiry" by the health check so an operator can rotate
    # them deliberately.


def downgrade() -> None:
    op.drop_index("ix_api_keys_expires_at", table_name="api_keys")
    for column in ("created_by_user_id", "last_used_at", "expires_at", "scopes"):
        op.drop_column("api_keys", column)
