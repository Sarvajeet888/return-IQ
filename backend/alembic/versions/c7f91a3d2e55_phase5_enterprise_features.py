"""Phase 5 - Enterprise Feature Development: new tables for password reset,
return notes/documents, workflow rules, feature flags, customer blacklist,
system settings, and SLA tracking.

Revision ID: c7f91a3d2e55
Revises: 8a3f21c9de44
Create Date: 2025-08-01
"""
from __future__ import annotations
from alembic import op
import sqlalchemy as sa

revision = 'c7f91a3d2e55'
down_revision = '8a3f21c9de44'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'password_reset_tokens',
        sa.Column('token', sa.String(128), primary_key=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False, index=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean, default=False, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'return_notes',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('return_request_id', sa.String(36), sa.ForeignKey('return_requests.id'), nullable=False, index=True),
        sa.Column('user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('note', sa.Text, nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, index=True),
    )

    op.create_table(
        'return_documents',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('return_request_id', sa.String(36), sa.ForeignKey('return_requests.id'), nullable=False, index=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('orgs.id'), nullable=False, index=True),
        sa.Column('uploaded_by_user_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('file_name', sa.String(255), nullable=False),
        sa.Column('file_type', sa.String(50), nullable=False),
        sa.Column('file_size_bytes', sa.Integer, default=0),
        sa.Column('storage_key', sa.String(500), nullable=False),
        sa.Column('is_damage_photo', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'workflow_rules',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('orgs.id'), nullable=False, index=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('rule_type', sa.String(30), nullable=False),
        sa.Column('conditions', sa.JSON, nullable=False),
        sa.Column('action', sa.JSON, nullable=False),
        sa.Column('priority', sa.Integer, default=0),
        sa.Column('is_active', sa.Boolean, default=True),
        sa.Column('triggered_count', sa.Integer, default=0),
        sa.Column('created_by', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'feature_flags',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('orgs.id'), nullable=False, index=True),
        sa.Column('flag_name', sa.String(100), nullable=False, index=True),
        sa.Column('enabled', sa.Boolean, default=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'customer_blacklist',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('orgs.id'), nullable=False, index=True),
        sa.Column('customer_identifier', sa.String(64), nullable=False, index=True),
        sa.Column('reason', sa.Text, nullable=True),
        sa.Column('blacklisted_by', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'system_settings',
        sa.Column('key', sa.String(100), primary_key=True),
        sa.Column('value', sa.JSON, nullable=False),
        sa.Column('updated_by', sa.String(36), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        'sla_tracking',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('return_request_id', sa.String(36), sa.ForeignKey('return_requests.id'), unique=True, index=True, nullable=False),
        sa.Column('org_id', sa.String(36), sa.ForeignKey('orgs.id'), nullable=False, index=True),
        sa.Column('sla_deadline', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('breached', sa.Boolean, default=False),
        sa.Column('escalated', sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Add is_blacklisted column to customers table
    op.add_column('customers', sa.Column('is_blacklisted', sa.Boolean, server_default='false', nullable=False))
    op.add_column('customers', sa.Column('notes', sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_table('sla_tracking')
    op.drop_table('system_settings')
    op.drop_table('customer_blacklist')
    op.drop_table('feature_flags')
    op.drop_table('workflow_rules')
    op.drop_table('return_documents')
    op.drop_table('return_notes')
    op.drop_table('password_reset_tokens')
    op.drop_column('customers', 'is_blacklisted')
    op.drop_column('customers', 'notes')
