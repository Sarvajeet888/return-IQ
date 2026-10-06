"""Phase 8 — Performance: add composite indexes for common query patterns.

Targets:
  - returns dashboard (org_id + created_at + status)
  - fraud analytics (risk_score filtering)
  - customer search (org_id + email)
  - audit log queries (org_id + created_at)
  - notification queries (org_id + read + created_at)

Revision ID: d9e2f4a7b831
Revises: c7f91a3d2e55
Create Date: 2025-08-01
"""
from alembic import op
import sqlalchemy as sa

revision = 'd9e2f4a7b831'
down_revision = 'c7f91a3d2e55'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # return_requests — most frequent query pattern is org_id + status + created_at
    op.create_index(
        'ix_return_requests_org_status_created',
        'return_requests',
        ['org_id', 'status', 'created_at'],
    )

    # predictions — fraud analytics filter on risk_score
    op.create_index(
        'ix_predictions_return_risk',
        'predictions',
        ['return_request_id', 'risk_score'],
    )

    # predictions — fraud score range queries
    op.create_index(
        'ix_predictions_fraud_score',
        'predictions',
        ['fraud_score'],
    )

    # customers — search by org + email
    op.create_index(
        'ix_customers_org_email',
        'customers',
        ['org_id', 'email'],
    )

    # customers — blacklist filter
    op.create_index(
        'ix_customers_org_blacklisted',
        'customers',
        ['org_id', 'is_blacklisted'],
    )

    # audit_logs — org + time (dashboard queries)
    op.create_index(
        'ix_audit_logs_org_created',
        'audit_logs',
        ['org_id', 'created_at'],
    )

    # notifications — unread count query
    op.create_index(
        'ix_notifications_org_read',
        'notifications',
        ['org_id', 'read'],
    )

    # workflow_rules — ordered by priority within org
    op.create_index(
        'ix_workflow_rules_org_active_priority',
        'workflow_rules',
        ['org_id', 'is_active', 'priority'],
    )

    # sla_tracking — breach detection query
    op.create_index(
        'ix_sla_tracking_org_breached',
        'sla_tracking',
        ['org_id', 'breached', 'resolved_at'],
    )

    # prediction_outcomes — count queries for ML label accumulation.
    # NOTE: the column is prediction_id, not return_request_id. This index
    # originally named a column that does not exist, which made
    # `alembic upgrade head` fail outright on any fresh database.
    op.create_index(
        'ix_prediction_outcomes_prediction',
        'prediction_outcomes',
        ['prediction_id'],
    )


def downgrade() -> None:
    op.drop_index('ix_return_requests_org_status_created', 'return_requests')
    op.drop_index('ix_predictions_return_risk', 'predictions')
    op.drop_index('ix_predictions_fraud_score', 'predictions')
    op.drop_index('ix_customers_org_email', 'customers')
    op.drop_index('ix_customers_org_blacklisted', 'customers')
    op.drop_index('ix_audit_logs_org_created', 'audit_logs')
    op.drop_index('ix_notifications_org_read', 'notifications')
    op.drop_index('ix_workflow_rules_org_active_priority', 'workflow_rules')
    op.drop_index('ix_sla_tracking_org_breached', 'sla_tracking')
    op.drop_index('ix_prediction_outcomes_prediction', 'prediction_outcomes')
