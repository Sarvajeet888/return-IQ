"""add prediction_outcomes table

Revision ID: 8a3f21c9de44
Revises: 71fe38dd182d
Create Date: 2026-08-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8a3f21c9de44'
down_revision: Union[str, None] = '71fe38dd182d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'prediction_outcomes',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('prediction_id', sa.String(length=36), nullable=False),
        sa.Column('actual_fraud_confirmed', sa.Boolean(), nullable=True),
        sa.Column('actual_damage_grade', sa.String(length=20), nullable=True),
        sa.Column('actual_cost_inr', sa.Float(), nullable=True),
        sa.Column('actual_resale_price_inr', sa.Float(), nullable=True),
        sa.Column('confirmed_by_user_id', sa.String(length=36), nullable=True),
        sa.Column('confirmed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ),
        sa.ForeignKeyConstraint(['confirmed_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_prediction_outcomes_prediction_id'),
        'prediction_outcomes', ['prediction_id'], unique=True,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_prediction_outcomes_prediction_id'), table_name='prediction_outcomes')
    op.drop_table('prediction_outcomes')
