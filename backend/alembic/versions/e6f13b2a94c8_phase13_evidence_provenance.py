"""Phase 13: evidence provenance and integrity

Revision ID: e6f13b2a94c8
Revises: d5c02f7a86b1
Create Date: 2026-08-14

Adds content hashing, source attribution and an evidence taxonomy to
`return_documents`.

EXISTING ROWS
-------------
`content_sha256` stays NULL for documents uploaded before this migration. It
is not backfilled, and that is deliberate: hashing the file currently sitting
in storage would produce a hash of whatever is there *now*, not of what was
uploaded then. Recording that as an integrity guarantee would assert something
we cannot know. NULL honestly means "no integrity guarantee for this file".

`source` defaults to 'merchant' and `evidence_type` to 'other', both accurate
for historical rows: they were uploaded through the merchant console, and the
only categorisation that existed was the `is_damage_photo` boolean, which is
retained rather than migrated so nothing already reading it breaks.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "e6f13b2a94c8"
down_revision = "d5c02f7a86b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "return_documents",
        sa.Column("content_sha256", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "return_documents",
        sa.Column("source", sa.String(length=20), nullable=False, server_default="merchant"),
    )
    op.add_column(
        "return_documents",
        sa.Column("evidence_type", sa.String(length=30), nullable=False, server_default="other"),
    )
    # Kept alongside the verified type so a mismatch between what a client
    # claimed and what the file actually was remains inspectable after the
    # fact -- that discrepancy is itself a signal worth being able to query.
    op.add_column(
        "return_documents",
        sa.Column("declared_file_type", sa.String(length=50), nullable=True),
    )

    op.create_index("ix_return_documents_source", "return_documents", ["source"])
    op.create_index("ix_return_documents_evidence_type", "return_documents", ["evidence_type"])

    # The reuse check runs on every upload and filters on (org_id, hash), so
    # index the pair. A hash-only index would scan every merchant's documents
    # to answer a question scoped to one.
    op.create_index(
        "ix_return_documents_org_hash",
        "return_documents",
        ["org_id", "content_sha256"],
    )


def downgrade() -> None:
    op.drop_index("ix_return_documents_org_hash", table_name="return_documents")
    op.drop_index("ix_return_documents_evidence_type", table_name="return_documents")
    op.drop_index("ix_return_documents_source", table_name="return_documents")
    for column in ("declared_file_type", "evidence_type", "source", "content_sha256"):
        op.drop_column("return_documents", column)
