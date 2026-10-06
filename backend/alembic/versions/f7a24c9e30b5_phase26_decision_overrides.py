"""Phase 26: decision overrides (human-in-the-loop capture)

Revision ID: f7a24c9e30b5
Revises: e6f13b2a94c8
Create Date: 2026-08-15

Records what the system recommended, what a person decided, and why.

This is a training table, not a log. Overrides are the only labelled signal
ReturnIQ can generate without waiting for outcomes: an outcome label takes
weeks (ship back, inspect, resell, money lands), while an override exists the
moment a warehouse manager disagrees.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "f7a24c9e30b5"
down_revision = "e6f13b2a94c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "decision_overrides",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("return_request_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("system_decision", sa.String(length=40), nullable=False),
        sa.Column("system_confidence", sa.String(length=16), nullable=True),
        sa.Column("system_risk_score", sa.Float(), nullable=True),
        sa.Column("system_fraud_score", sa.Float(), nullable=True),
        sa.Column("human_decision", sa.String(length=40), nullable=False),
        sa.Column("reason_category", sa.String(length=40), nullable=False),
        sa.Column("reason_detail", sa.Text(), nullable=False, server_default=""),
        sa.Column("feature_snapshot", sa.JSON(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(["org_id"], ["orgs.id"]),
        sa.ForeignKeyConstraint(["return_request_id"], ["return_requests.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_index("ix_decision_overrides_org_id", "decision_overrides", ["org_id"])
    op.create_index(
        "ix_decision_overrides_return_request_id", "decision_overrides",
        ["return_request_id"],
    )
    op.create_index("ix_decision_overrides_created_at", "decision_overrides", ["created_at"])
    op.create_index(
        "ix_decision_overrides_human_decision", "decision_overrides", ["human_decision"],
    )
    op.create_index(
        "ix_decision_overrides_reason_category", "decision_overrides", ["reason_category"],
    )

    # "Which recommendations does this org reject most often" is the question
    # that identifies where the models are worst, and it is the first thing
    # anyone will ask of this table.
    op.create_index(
        "ix_decision_overrides_org_recommendation",
        "decision_overrides",
        ["org_id", "system_decision"],
    )


def downgrade() -> None:
    for name in (
        "ix_decision_overrides_org_recommendation",
        "ix_decision_overrides_reason_category",
        "ix_decision_overrides_human_decision",
        "ix_decision_overrides_created_at",
        "ix_decision_overrides_return_request_id",
        "ix_decision_overrides_org_id",
    ):
        op.drop_index(name, table_name="decision_overrides")
    op.drop_table("decision_overrides")
