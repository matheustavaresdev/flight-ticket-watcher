"""Add search_configs, scan_runs, price_snapshots tables

Revision ID: 69af851a
Revises:
Create Date: 2026-03-10

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "69af851a"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "search_configs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("origin", sa.String(length=3), nullable=False),
        sa.Column("destination", sa.String(length=3), nullable=False),
        sa.Column("must_arrive_by", sa.Date(), nullable=False),
        sa.Column("must_stay_until", sa.Date(), nullable=False),
        sa.Column("max_trip_days", sa.Integer(), nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_search_configs_origin_dest", "search_configs", ["origin", "destination"])

    op.create_table(
        "scan_runs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("search_config_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.Enum("running", "completed", "failed", name="scanstatus", native_enum=False), server_default="running", nullable=False),
        sa.Column("last_successful_date", sa.Date(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["search_config_id"], ["search_configs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scan_runs_config_id", "scan_runs", ["search_config_id"])
    op.create_index("ix_scan_runs_status", "scan_runs", ["status"])

    op.create_table(
        "price_snapshots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scan_run_id", sa.Integer(), nullable=False),
        sa.Column("origin", sa.String(length=3), nullable=False),
        sa.Column("destination", sa.String(length=3), nullable=False),
        sa.Column("flight_date", sa.Date(), nullable=False),
        sa.Column("flight_code", sa.String(length=20), nullable=False),
        sa.Column("departure_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("arrival_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("duration_min", sa.Integer(), nullable=False),
        sa.Column("stops", sa.Integer(), nullable=False),
        sa.Column("brand", sa.String(length=30), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("search_type", sa.Enum("oneway", "roundtrip", name="searchtype", native_enum=False), nullable=False),
        sa.Column("fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["scan_run_id"], ["scan_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_price_snapshots_run_id", "price_snapshots", ["scan_run_id"])
    op.create_index("ix_price_snapshots_route_date", "price_snapshots", ["origin", "destination", "flight_date"])


def downgrade() -> None:
    op.drop_index("ix_price_snapshots_route_date", table_name="price_snapshots")
    op.drop_index("ix_price_snapshots_run_id", table_name="price_snapshots")
    op.drop_table("price_snapshots")

    op.drop_index("ix_scan_runs_status", table_name="scan_runs")
    op.drop_index("ix_scan_runs_config_id", table_name="scan_runs")
    op.drop_table("scan_runs")

    op.drop_index("ix_search_configs_origin_dest", table_name="search_configs")
    op.drop_table("search_configs")
