"""add approval codes to upgrade requests

Revision ID: 0002_upgrade_request_codes
Revises: 0001_initial
Create Date: 2026-03-22 12:40:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0002_upgrade_request_codes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "upgrade_requests",
        sa.Column("approval_code", sa.String(length=32), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE upgrade_requests "
            "SET approval_code = 'TZR-' "
            "|| lpad(right(cast(telegram_chat_id as text), 4), 4, '0') "
            "|| '-' || upper(substr(replace(cast(id as text), '-', ''), 1, 4)) "
            "WHERE approval_code IS NULL"
        )
    )
    op.alter_column("upgrade_requests", "approval_code", nullable=False)
    op.create_index(
        "ix_upgrade_requests_approval_code",
        "upgrade_requests",
        ["approval_code"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_upgrade_requests_approval_code", table_name="upgrade_requests")
    op.drop_column("upgrade_requests", "approval_code")
