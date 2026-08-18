"""Store historical driver identity on each race entry.

Revision ID: 20260806_0004
Revises: 20260806_0003
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260806_0004"
down_revision: str | None = "20260806_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("race_entries", sa.Column("abbreviation", sa.String(length=4)))
    op.add_column("race_entries", sa.Column("full_name", sa.String(length=120)))
    op.add_column("race_entries", sa.Column("country_code", sa.String(length=5)))


def downgrade() -> None:
    op.drop_column("race_entries", "country_code")
    op.drop_column("race_entries", "full_name")
    op.drop_column("race_entries", "abbreviation")
