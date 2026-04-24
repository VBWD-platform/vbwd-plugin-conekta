"""Create conekta_orders table.

Revision ID: 20260424_1100_conekta
Revises: 20260424_1000_toss
Create Date: 2026-04-24

Sprint 35 — Conekta Mexico.
"""
from alembic import op
import sqlalchemy as sa


revision = "20260424_1100_conekta"
down_revision = "20260424_1000_toss"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conekta_orders",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("invoice_no", sa.String(length=64), nullable=False, unique=True),
        sa.Column("order_id", sa.String(length=128), nullable=True),
        sa.Column("method", sa.String(length=32), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column(
            "currency", sa.String(length=3), nullable=False, server_default="MXN"
        ),
        sa.Column("msi", sa.Integer(), nullable=True),
        sa.Column("reference", sa.String(length=64), nullable=True),
        sa.Column("clabe", sa.String(length=32), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "status", sa.String(length=24), nullable=False, server_default="pending"
        ),
        sa.Column("last_provider_status", sa.String(length=32), nullable=True),
        sa.Column("extra_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "ix_conekta_orders_order_id",
        "conekta_orders",
        ["order_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_conekta_orders_order_id", table_name="conekta_orders")
    op.drop_table("conekta_orders")
