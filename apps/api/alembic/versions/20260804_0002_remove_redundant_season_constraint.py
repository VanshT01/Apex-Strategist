"""Remove redundant season year unique constraint.

Revision ID: 20260804_0002
Revises: 20260804_0001
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260804_0002"
down_revision: str | None = "20260804_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("seasons") as batch_op:
        batch_op.drop_constraint("seasons_year_key", type_="unique")


def downgrade() -> None:
    with op.batch_alter_table("seasons") as batch_op:
        batch_op.create_unique_constraint("seasons_year_key", ["year"])
