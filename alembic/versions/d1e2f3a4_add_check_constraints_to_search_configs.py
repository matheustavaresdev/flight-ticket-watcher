"""add check constraints to search_configs

Revision ID: d1e2f3a4
Revises: c7d8e9f0
Create Date: 2026-03-16

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4"
down_revision: Union[str, None] = "c7d8e9f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_check_constraint(
        "ck_search_configs_min_trip_days_positive",
        "search_configs",
        "min_trip_days IS NULL OR min_trip_days >= 1",
    )
    op.create_check_constraint(
        "ck_search_configs_min_le_max_trip_days",
        "search_configs",
        "min_trip_days IS NULL OR min_trip_days <= max_trip_days",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_search_configs_min_le_max_trip_days",
        "search_configs",
        type_="check",
    )
    op.drop_constraint(
        "ck_search_configs_min_trip_days_positive",
        "search_configs",
        type_="check",
    )
