"""add cod_risk_assessments table

Revision ID: f3b7e0c19a44
Revises: d9e2f4a7b831
Create Date: 2026-08-07 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f3b7e0c19a44'
# Re-parented during the merge. This branch was authored against
# d9e2f4a7b831 in parallel with e4b7c1d90a23 (consent + PII encryption),
# which would have left two heads. Chained after it instead.
down_revision: Union[str, None] = 'e4b7c1d90a23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cod_risk_assessments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('platform_order_id', sa.String(length=128), nullable=False),
        sa.Column('customer_identifier', sa.String(length=64), nullable=False),
        sa.Column('customer_name', sa.String(length=200), nullable=False),
        sa.Column('delivery_address', sa.Text(), nullable=False),
        sa.Column('delivery_pincode', sa.String(length=6), nullable=False),
        sa.Column('order_value', sa.Float(), nullable=False),
        sa.Column('risk_score', sa.Float(), nullable=False),
        sa.Column('risk_band', sa.String(length=20), nullable=False),
        sa.Column('flags', sa.JSON(), nullable=False),
        sa.Column('recommendation', sa.String(length=200), nullable=False),
        sa.Column('actual_outcome', sa.String(length=20), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cod_risk_assessments_org_id'), 'cod_risk_assessments', ['org_id'], unique=False)
    op.create_index(op.f('ix_cod_risk_assessments_platform_order_id'), 'cod_risk_assessments', ['platform_order_id'], unique=False)
    op.create_index(op.f('ix_cod_risk_assessments_customer_identifier'), 'cod_risk_assessments', ['customer_identifier'], unique=False)
    op.create_index(op.f('ix_cod_risk_assessments_delivery_pincode'), 'cod_risk_assessments', ['delivery_pincode'], unique=False)
    op.create_index(op.f('ix_cod_risk_assessments_risk_band'), 'cod_risk_assessments', ['risk_band'], unique=False)
    op.create_index(op.f('ix_cod_risk_assessments_created_at'), 'cod_risk_assessments', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cod_risk_assessments_created_at'), table_name='cod_risk_assessments')
    op.drop_index(op.f('ix_cod_risk_assessments_risk_band'), table_name='cod_risk_assessments')
    op.drop_index(op.f('ix_cod_risk_assessments_delivery_pincode'), table_name='cod_risk_assessments')
    op.drop_index(op.f('ix_cod_risk_assessments_customer_identifier'), table_name='cod_risk_assessments')
    op.drop_index(op.f('ix_cod_risk_assessments_platform_order_id'), table_name='cod_risk_assessments')
    op.drop_index(op.f('ix_cod_risk_assessments_org_id'), table_name='cod_risk_assessments')
    op.drop_table('cod_risk_assessments')
