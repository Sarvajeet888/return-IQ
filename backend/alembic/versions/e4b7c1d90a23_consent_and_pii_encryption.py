"""Phase 12 — consent records (DPDP Act) and PII encryption at rest.

Adds:
  - consent_records table: auditable proof of Terms/Privacy acceptance
  - widens customers.name/email/phone to hold Fernet ciphertext

IMPORTANT — existing plaintext data:
This migration widens the columns but does NOT encrypt rows already in the
table. Application code tolerates that: decrypt_value() returns non-Fernet
values unchanged, so mixed plaintext/ciphertext works during rollout.

Run scripts/encrypt_existing_pii.py after upgrading to backfill.

Revision ID: e4b7c1d90a23
Revises: d9e2f4a7b831
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "e4b7c1d90a23"
down_revision = "d9e2f4a7b831"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "consent_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("consent_type", sa.String(50), nullable=False, server_default="terms_and_privacy"),
        sa.Column("policy_version", sa.String(20), nullable=False),
        sa.Column("granted", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_consent_records_user_created", "consent_records", ["user_id", "created_at"])

    # Fernet ciphertext is base64(IV + ciphertext + HMAC) - roughly 1.6x the
    # plaintext plus ~100 bytes fixed overhead. EncryptedString sizes itself as
    # max(length*3, 512); these ALTERs keep the database in step.
    #
    # SQLite ignores VARCHAR length entirely, so batch_alter_table is used for
    # portability - it is a no-op there and a real ALTER on PostgreSQL.
    with op.batch_alter_table("customers") as batch:
        batch.alter_column("name", type_=sa.String(600), existing_type=sa.String(200))
        batch.alter_column("email", type_=sa.String(960), existing_type=sa.String(320))
        batch.alter_column("phone", type_=sa.String(512), existing_type=sa.String(20),
                           existing_nullable=True)


def downgrade() -> None:
    # WARNING: downgrading truncates encrypted values back to plaintext widths.
    # Decrypt with scripts/encrypt_existing_pii.py --decrypt BEFORE downgrading,
    # or the ciphertext will be cut and the data lost.
    with op.batch_alter_table("customers") as batch:
        batch.alter_column("phone", type_=sa.String(20), existing_type=sa.String(512),
                           existing_nullable=True)
        batch.alter_column("email", type_=sa.String(320), existing_type=sa.String(960))
        batch.alter_column("name", type_=sa.String(200), existing_type=sa.String(600))

    op.drop_index("ix_consent_records_user_created", "consent_records")
    op.drop_table("consent_records")
