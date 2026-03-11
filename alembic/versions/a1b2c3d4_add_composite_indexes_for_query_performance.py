"""Add composite indexes for query performance (FLI-20)

Revision ID: a1b2c3d4
Revises: 69af851a
Create Date: 2026-03-11

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4"
down_revision: str | None = "69af851a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Replace two single-column scan_runs indexes with one composite index.
    # The composite (search_config_id, status) serves config-only queries via
    # leftmost prefix, making ix_scan_runs_config_id redundant. The separate
    # status-only index is low-selectivity and not useful on its own.
    op.drop_index("ix_scan_runs_config_id", table_name="scan_runs")
    op.drop_index("ix_scan_runs_status", table_name="scan_runs")
    op.create_index("ix_scan_runs_config_status", "scan_runs", ["search_config_id", "status"])

    # Add new price_snapshots indexes for cheapest-by-brand and price history queries.
    op.create_index(
        "ix_price_snapshots_route_date_brand",
        "price_snapshots",
        ["origin", "destination", "flight_date", "brand"],
    )
    op.create_index(
        "ix_price_snapshots_date_fetched",
        "price_snapshots",
        ["flight_date", "fetched_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_price_snapshots_date_fetched", table_name="price_snapshots")
    op.drop_index("ix_price_snapshots_route_date_brand", table_name="price_snapshots")

    op.drop_index("ix_scan_runs_config_status", table_name="scan_runs")
    op.create_index("ix_scan_runs_status", "scan_runs", ["status"])
    op.create_index("ix_scan_runs_config_id", "scan_runs", ["search_config_id"])
