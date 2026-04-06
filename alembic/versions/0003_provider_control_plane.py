"""add provider control plane and rich payment management

Revision ID: 0003_provider_control_plane
Revises: 0002_upgrade_request_codes
Create Date: 2026-04-04 14:00:00
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0003_provider_control_plane"
down_revision = "0002_upgrade_request_codes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "providers",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("slug", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("api_key", sa.String(length=255), nullable=False),
        sa.Column("branding_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_providers_slug", "providers", ["slug"], unique=False)
    op.create_index("ix_providers_api_key", "providers", ["api_key"], unique=False)

    op.create_table(
        "provider_members",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("actor_code", sa.String(length=64), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "actor_code"),
    )
    op.create_index(
        "ix_provider_members_provider_id", "provider_members", ["provider_id"], unique=False
    )

    op.create_table(
        "provider_bot_instances",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("webhook_secret", sa.String(length=255), nullable=False),
        sa.Column("bot_token", sa.String(length=255), nullable=True),
        sa.Column("public_handle", sa.String(length=255), nullable=True),
        sa.Column("branding_override_json", sa.JSON(), nullable=False),
        sa.Column("configuration_json", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("webhook_secret"),
    )
    op.create_index(
        "ix_provider_bot_instances_provider_id",
        "provider_bot_instances",
        ["provider_id"],
        unique=False,
    )
    op.create_index(
        "ix_provider_bot_instances_code",
        "provider_bot_instances",
        ["code"],
        unique=False,
    )
    op.create_index(
        "ix_provider_bot_instances_platform",
        "provider_bot_instances",
        ["platform"],
        unique=False,
    )
    op.create_index(
        "ix_provider_bot_instances_webhook_secret",
        "provider_bot_instances",
        ["webhook_secret"],
        unique=False,
    )

    op.create_table(
        "payment_destinations",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("vpa", sa.String(length=255), nullable=False),
        sa.Column("payee_name", sa.String(length=255), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "code"),
    )
    op.create_index(
        "ix_payment_destinations_provider_id",
        "payment_destinations",
        ["provider_id"],
        unique=False,
    )

    op.create_table(
        "clients",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("telegram_id", sa.BigInteger(), nullable=True),
        sa.Column("telegram_username", sa.String(length=255), nullable=True),
        sa.Column("whatsapp_number", sa.String(length=32), nullable=True),
        sa.Column("external_ref", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("labels_json", sa.JSON(), nullable=False),
        sa.Column("onboarding_source", sa.String(length=64), nullable=False),
        sa.Column("bot_instance_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["bot_instance_id"], ["provider_bot_instances.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider_id", "code"),
    )
    op.create_index("ix_clients_provider_id", "clients", ["provider_id"], unique=False)
    op.create_index("ix_clients_telegram_id", "clients", ["telegram_id"], unique=False)
    op.create_index("ix_clients_whatsapp_number", "clients", ["whatsapp_number"], unique=False)

    op.create_table(
        "payment_templates",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("item_code", sa.String(length=64), nullable=True),
        sa.Column("default_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("destination_code", sa.String(length=64), nullable=True),
        sa.Column("message_template", sa.Text(), nullable=True),
        sa.Column("custom_message", sa.Text(), nullable=True),
        sa.Column("pre_generate", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
        sa.UniqueConstraint("provider_id", "item_code"),
    )
    op.create_index(
        "ix_payment_templates_provider_id", "payment_templates", ["provider_id"], unique=False
    )
    op.create_index("ix_payment_templates_code", "payment_templates", ["code"], unique=False)
    op.create_index(
        "ix_payment_templates_item_code", "payment_templates", ["item_code"], unique=False
    )

    op.alter_column("payment_requests", "merchant_id", existing_type=sa.UUID(), nullable=True)
    op.add_column("payment_requests", sa.Column("provider_id", sa.UUID(), nullable=True))
    op.add_column("payment_requests", sa.Column("client_id", sa.UUID(), nullable=True))
    op.add_column("payment_requests", sa.Column("template_id", sa.UUID(), nullable=True))
    op.add_column("payment_requests", sa.Column("item_code", sa.String(length=64), nullable=True))
    op.add_column("payment_requests", sa.Column("custom_message", sa.Text(), nullable=True))
    op.add_column("payment_requests", sa.Column("channel", sa.String(length=32), nullable=True))
    op.add_column(
        "payment_requests",
        sa.Column("status", sa.String(length=32), nullable=False, server_default="pending"),
    )
    op.add_column(
        "payment_requests", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "payment_requests", sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "payment_requests",
        sa.Column("status_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("payment_requests", sa.Column("notes_summary", sa.Text(), nullable=True))
    op.add_column(
        "payment_requests",
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default="{}"),
    )
    op.add_column(
        "payment_requests",
        sa.Column("walk_in", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        "fk_payment_requests_provider_id_providers",
        "payment_requests",
        "providers",
        ["provider_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_payment_requests_client_id_clients",
        "payment_requests",
        "clients",
        ["client_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_payment_requests_template_id_payment_templates",
        "payment_requests",
        "payment_templates",
        ["template_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_payment_requests_provider_id", "payment_requests", ["provider_id"], unique=False
    )
    op.create_index(
        "ix_payment_requests_client_id", "payment_requests", ["client_id"], unique=False
    )
    op.create_index(
        "ix_payment_requests_template_id", "payment_requests", ["template_id"], unique=False
    )
    op.create_index(
        "ix_payment_requests_item_code", "payment_requests", ["item_code"], unique=False
    )
    op.create_index("ix_payment_requests_status", "payment_requests", ["status"], unique=False)

    op.create_table(
        "payment_logs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("payment_request_id", sa.UUID(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_request_id"], ["payment_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_payment_logs_payment_request_id", "payment_logs", ["payment_request_id"], unique=False
    )

    op.create_table(
        "payment_notes",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("payment_request_id", sa.UUID(), nullable=False),
        sa.Column("note", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_request_id"], ["payment_requests.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_payment_notes_payment_request_id", "payment_notes", ["payment_request_id"], unique=False
    )

    op.create_table(
        "payment_reminders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("reminder_type", sa.String(length=32), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payment_request_id", sa.UUID(), nullable=True),
        sa.Column("client_id", sa.UUID(), nullable=True),
        sa.Column("task_name", sa.String(length=255), nullable=True),
        sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("include_qr", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["payment_request_id"], ["payment_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index(
        "ix_payment_reminders_provider_id", "payment_reminders", ["provider_id"], unique=False
    )
    op.create_index("ix_payment_reminders_code", "payment_reminders", ["code"], unique=False)
    op.create_index(
        "ix_payment_reminders_payment_request_id",
        "payment_reminders",
        ["payment_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_payment_reminders_client_id", "payment_reminders", ["client_id"], unique=False
    )
    op.create_index("ix_payment_reminders_status", "payment_reminders", ["status"], unique=False)

    op.create_table(
        "qr_assets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=True),
        sa.Column("payment_request_id", sa.UUID(), nullable=True),
        sa.Column("template_id", sa.UUID(), nullable=True),
        sa.Column("item_code", sa.String(length=64), nullable=True),
        sa.Column("asset_type", sa.String(length=32), nullable=False),
        sa.Column("mime_type", sa.String(length=64), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_bytes", sa.LargeBinary(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("upi_uri", sa.Text(), nullable=False),
        sa.Column("is_pre_generated", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_request_id"], ["payment_requests.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["template_id"], ["payment_templates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.create_index("ix_qr_assets_code", "qr_assets", ["code"], unique=False)
    op.create_index("ix_qr_assets_provider_id", "qr_assets", ["provider_id"], unique=False)
    op.create_index(
        "ix_qr_assets_payment_request_id", "qr_assets", ["payment_request_id"], unique=False
    )
    op.create_index("ix_qr_assets_template_id", "qr_assets", ["template_id"], unique=False)
    op.create_index("ix_qr_assets_item_code", "qr_assets", ["item_code"], unique=False)

    op.create_table(
        "outbound_messages",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("provider_id", sa.UUID(), nullable=False),
        sa.Column("client_id", sa.UUID(), nullable=True),
        sa.Column("payment_request_id", sa.UUID(), nullable=True),
        sa.Column("reminder_id", sa.UUID(), nullable=True),
        sa.Column("bot_instance_id", sa.UUID(), nullable=True),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("delivery_state", sa.String(length=32), nullable=False),
        sa.Column("recipient", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("share_url", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["bot_instance_id"], ["provider_bot_instances.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["client_id"], ["clients.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["payment_request_id"], ["payment_requests.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reminder_id"], ["payment_reminders.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_outbound_messages_provider_id", "outbound_messages", ["provider_id"], unique=False
    )
    op.create_index(
        "ix_outbound_messages_client_id", "outbound_messages", ["client_id"], unique=False
    )
    op.create_index(
        "ix_outbound_messages_payment_request_id",
        "outbound_messages",
        ["payment_request_id"],
        unique=False,
    )
    op.create_index(
        "ix_outbound_messages_reminder_id", "outbound_messages", ["reminder_id"], unique=False
    )

    op.alter_column("payment_requests", "status", server_default=None)
    op.alter_column("payment_requests", "metadata_json", server_default=None)
    op.alter_column("payment_requests", "walk_in", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_outbound_messages_reminder_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_payment_request_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_client_id", table_name="outbound_messages")
    op.drop_index("ix_outbound_messages_provider_id", table_name="outbound_messages")
    op.drop_table("outbound_messages")

    op.drop_index("ix_qr_assets_item_code", table_name="qr_assets")
    op.drop_index("ix_qr_assets_template_id", table_name="qr_assets")
    op.drop_index("ix_qr_assets_payment_request_id", table_name="qr_assets")
    op.drop_index("ix_qr_assets_provider_id", table_name="qr_assets")
    op.drop_index("ix_qr_assets_code", table_name="qr_assets")
    op.drop_table("qr_assets")

    op.drop_index("ix_payment_reminders_status", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_client_id", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_payment_request_id", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_code", table_name="payment_reminders")
    op.drop_index("ix_payment_reminders_provider_id", table_name="payment_reminders")
    op.drop_table("payment_reminders")

    op.drop_index("ix_payment_notes_payment_request_id", table_name="payment_notes")
    op.drop_table("payment_notes")

    op.drop_index("ix_payment_logs_payment_request_id", table_name="payment_logs")
    op.drop_table("payment_logs")

    op.drop_index("ix_payment_requests_status", table_name="payment_requests")
    op.drop_index("ix_payment_requests_item_code", table_name="payment_requests")
    op.drop_index("ix_payment_requests_template_id", table_name="payment_requests")
    op.drop_index("ix_payment_requests_client_id", table_name="payment_requests")
    op.drop_index("ix_payment_requests_provider_id", table_name="payment_requests")
    op.drop_constraint(
        "fk_payment_requests_template_id_payment_templates", "payment_requests", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_payment_requests_client_id_clients", "payment_requests", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_payment_requests_provider_id_providers", "payment_requests", type_="foreignkey"
    )
    op.drop_column("payment_requests", "walk_in")
    op.drop_column("payment_requests", "metadata_json")
    op.drop_column("payment_requests", "notes_summary")
    op.drop_column("payment_requests", "status_updated_at")
    op.drop_column("payment_requests", "paid_at")
    op.drop_column("payment_requests", "due_at")
    op.drop_column("payment_requests", "status")
    op.drop_column("payment_requests", "channel")
    op.drop_column("payment_requests", "custom_message")
    op.drop_column("payment_requests", "item_code")
    op.drop_column("payment_requests", "template_id")
    op.drop_column("payment_requests", "client_id")
    op.drop_column("payment_requests", "provider_id")
    op.alter_column("payment_requests", "merchant_id", existing_type=sa.UUID(), nullable=False)

    op.drop_index("ix_payment_templates_item_code", table_name="payment_templates")
    op.drop_index("ix_payment_templates_code", table_name="payment_templates")
    op.drop_index("ix_payment_templates_provider_id", table_name="payment_templates")
    op.drop_table("payment_templates")

    op.drop_index("ix_clients_whatsapp_number", table_name="clients")
    op.drop_index("ix_clients_telegram_id", table_name="clients")
    op.drop_index("ix_clients_provider_id", table_name="clients")
    op.drop_table("clients")

    op.drop_index("ix_payment_destinations_provider_id", table_name="payment_destinations")
    op.drop_table("payment_destinations")

    op.drop_index("ix_provider_bot_instances_webhook_secret", table_name="provider_bot_instances")
    op.drop_index("ix_provider_bot_instances_platform", table_name="provider_bot_instances")
    op.drop_index("ix_provider_bot_instances_code", table_name="provider_bot_instances")
    op.drop_index("ix_provider_bot_instances_provider_id", table_name="provider_bot_instances")
    op.drop_table("provider_bot_instances")

    op.drop_index("ix_provider_members_provider_id", table_name="provider_members")
    op.drop_table("provider_members")

    op.drop_index("ix_providers_api_key", table_name="providers")
    op.drop_index("ix_providers_slug", table_name="providers")
    op.drop_table("providers")
