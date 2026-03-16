"""add min_trip_days to search_configs

Revision ID: c7d8e9f0
Revises: b5c6d7e8
Create Date: 2026-03-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c7d8e9f0"
down_revision: Union[str, None] = "b5c6d7e8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "search_configs",
        sa.Column("min_trip_days", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("search_configs", "min_trip_days")
