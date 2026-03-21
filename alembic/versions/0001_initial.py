"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-03-21 23:30:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "merchants",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=False),
        sa.Column("username", sa.String(length=255), nullable=True),
        sa.Column("first_name", sa.String(length=255), nullable=False),
        sa.Column("last_name", sa.String(length=255), nullable=True),
        sa.Column("vpa", sa.String(length=255), nullable=True),
        sa.Column("tier", sa.String(length=32), nullable=False),
        sa.Column("generation_count", sa.Integer(), nullable=False),
        sa.Column("last_command_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("telegram_id"),
    )
    op.create_index("ix_merchants_telegram_id", "merchants", ["telegram_id"], unique=False)

    op.create_table(
        "payment_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("merchant_id", sa.UUID(), nullable=False),
        sa.Column("reference", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("upi_uri", sa.Text(), nullable=False),
        sa.Column("qr_mime_type", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("reference"),
    )
    op.create_index(
        "ix_payment_requests_merchant_id",
        "payment_requests",
        ["merchant_id"],
        unique=False,
    )
    op.create_index(
        "ix_payment_requests_reference",
        "payment_requests",
        ["reference"],
        unique=False,
    )

    op.create_table(
        "upgrade_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("merchant_id", sa.UUID(), nullable=False),
        sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=False),
        sa.Column("telegram_file_id", sa.String(length=255), nullable=False),
        sa.Column("telegram_file_unique_id", sa.String(length=255), nullable=True),
        sa.Column("media_kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["merchant_id"], ["merchants.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_upgrade_requests_merchant_id",
        "upgrade_requests",
        ["merchant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_upgrade_requests_merchant_id", table_name="upgrade_requests")
    op.drop_table("upgrade_requests")
    op.drop_index("ix_payment_requests_reference", table_name="payment_requests")
    op.drop_index("ix_payment_requests_merchant_id", table_name="payment_requests")
    op.drop_table("payment_requests")
    op.drop_index("ix_merchants_telegram_id", table_name="merchants")
    op.drop_table("merchants")
