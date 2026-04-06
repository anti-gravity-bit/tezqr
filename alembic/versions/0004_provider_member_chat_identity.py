"""add provider member chat identities

Revision ID: 0004_provider_member_chat
Revises: 0003_provider_control_plane
Create Date: 2026-04-06 20:10:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0004_provider_member_chat"
down_revision = "0003_provider_control_plane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("provider_members", sa.Column("telegram_id", sa.BigInteger(), nullable=True))
    op.add_column(
        "provider_members",
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "provider_members",
        sa.Column("whatsapp_number", sa.String(length=32), nullable=True),
    )
    op.create_unique_constraint(
        "uq_provider_members_provider_id_telegram_id",
        "provider_members",
        ["provider_id", "telegram_id"],
    )
    op.create_unique_constraint(
        "uq_provider_members_provider_id_whatsapp_number",
        "provider_members",
        ["provider_id", "whatsapp_number"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_provider_members_provider_id_whatsapp_number",
        "provider_members",
        type_="unique",
    )
    op.drop_constraint(
        "uq_provider_members_provider_id_telegram_id",
        "provider_members",
        type_="unique",
    )
    op.drop_column("provider_members", "whatsapp_number")
    op.drop_column("provider_members", "telegram_username")
    op.drop_column("provider_members", "telegram_id")
