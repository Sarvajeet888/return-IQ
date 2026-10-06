"""add courier_remittances table

Revision ID: a1c58d0e7fb2
Revises: f3b7e0c19a44
Create Date: 2026-08-07 00:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1c58d0e7fb2'
down_revision: Union[str, None] = 'f3b7e0c19a44'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'courier_remittances',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('org_id', sa.String(length=36), nullable=False),
        sa.Column('platform_order_id', sa.String(length=128), nullable=False),
        sa.Column('courier', sa.String(length=50), nullable=False),
        sa.Column('awb_number', sa.String(length=64), nullable=True),
        sa.Column('remittance_date', sa.DateTime(timezone=True), nullable=False),
        sa.Column('remitted_amount', sa.Float(), nullable=False),
        sa.Column('expected_amount', sa.Float(), nullable=True),
        sa.Column('discrepancy_amount', sa.Float(), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['org_id'], ['orgs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_courier_remittances_org_id'), 'courier_remittances', ['org_id'], unique=False)
    op.create_index(op.f('ix_courier_remittances_platform_order_id'), 'courier_remittances', ['platform_order_id'], unique=False)
    op.create_index(op.f('ix_courier_remittances_courier'), 'courier_remittances', ['courier'], unique=False)
    op.create_index(op.f('ix_courier_remittances_status'), 'courier_remittances', ['status'], unique=False)
    op.create_index(op.f('ix_courier_remittances_created_at'), 'courier_remittances', ['created_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_courier_remittances_created_at'), table_name='courier_remittances')
    op.drop_index(op.f('ix_courier_remittances_status'), table_name='courier_remittances')
    op.drop_index(op.f('ix_courier_remittances_courier'), table_name='courier_remittances')
    op.drop_index(op.f('ix_courier_remittances_platform_order_id'), table_name='courier_remittances')
    op.drop_index(op.f('ix_courier_remittances_org_id'), table_name='courier_remittances')
    op.drop_table('courier_remittances')
