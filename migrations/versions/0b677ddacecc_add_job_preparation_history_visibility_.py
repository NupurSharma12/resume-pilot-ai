"""add job preparation history visibility and soft delete

Revision ID: 0b677ddacecc
Revises: c122c2e3a625
Create Date: 2026-08-15 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0b677ddacecc"
down_revision: str | Sequence[str] | None = "c122c2e3a625"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # `server_default=true` is what makes every existing row read as
    # "a real, History-visible, not-deleted preparation" the instant this
    # column exists -- exactly what every row created before this
    # migration actually was. See app.persistence.db.tables.JobPreparationRow's
    # docstring.
    op.add_column(
        "job_preparations",
        sa.Column(
            "include_in_history",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "job_preparations",
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("job_preparations", "deleted_at")
    op.drop_column("job_preparations", "include_in_history")
