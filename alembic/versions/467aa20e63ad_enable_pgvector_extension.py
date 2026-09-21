"""enable pgvector extension

Revision ID: 467aa20e63ad
Revises: 60c04b6f7435
Create Date: 2026-09-21 23:34:27.111316

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "467aa20e63ad"
down_revision: str | Sequence[str] | None = "60c04b6f7435"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Enable the pgvector extension.

    Autogenerate cannot detect this — it only diffs Base.metadata against
    the live schema, and an extension isn't a table. Kept as its own
    migration, separate from the table-creating one that follows, so a
    failure partway through table creation can't leave a half-applied
    CREATE EXTENSION in the same transaction.
    """
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")


def downgrade() -> None:
    """Disable the pgvector extension."""
    op.execute("DROP EXTENSION IF EXISTS vector")
