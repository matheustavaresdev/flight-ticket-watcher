"""Add price_alerts table (FLI-105)

Revision ID: c3d4e5f6
Revises: b5c6d7e8
Create Date: 2026-03-15

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6"
down_revision: str | None = "b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "price_alerts",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_config_id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=3), nullable=False),
        sa.Column("destination", sa.String(length=3), nullable=False),
        sa.Column("flight_date", sa.Date(), nullable=False),
        sa.Column("airline", sa.String(length=30), nullable=False),
        sa.Column("brand", sa.String(length=30), nullable=False),
        sa.Column("previous_low_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("new_price", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column("price_drop_abs", sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column(
            "alert_type",
            sa.Enum("new_low", "threshold", name="alerttype", native_enum=False),
            nullable=False,
        ),
        sa.Column("sent_to", sa.String(length=255), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(["search_config_id"], ["search_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_price_alerts_route_date",
        "price_alerts",
        ["origin", "destination", "flight_date", "brand"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_alerts_route_date", table_name="price_alerts")
    op.drop_table("price_alerts")
