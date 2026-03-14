"""Add retry columns to search_configs (FLI-30)

Revision ID: b5c6d7e8
Revises: a1b2c3d4
Create Date: 2026-03-14

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b5c6d7e8"
down_revision: str | None = "a1b2c3d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "search_configs",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "search_configs",
        sa.Column("needs_attention", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("search_configs", "needs_attention")
    op.drop_column("search_configs", "retry_count")
