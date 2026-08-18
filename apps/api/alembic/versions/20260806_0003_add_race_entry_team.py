"""Store a driver's team on the race entry.

Revision ID: 20260806_0003
Revises: 20260804_0002
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_0003"
down_revision: str | None = "20260804_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("race_entries", sa.Column("team_name", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("race_entries", "team_name")
