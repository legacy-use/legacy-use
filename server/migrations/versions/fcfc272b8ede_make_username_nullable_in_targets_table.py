"""Make username nullable in targets table

Revision ID: fcfc272b8ede
Revises: f4ac82882dc0
Create Date: 2025-03-02 16:35:58.443518

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'fcfc272b8ede'
down_revision: Union[str, None] = 'f4ac82882dc0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # PostgreSQL supports ALTER COLUMN directly
    op.alter_column('targets', 'username', nullable=True)


def downgrade() -> None:
    # PostgreSQL supports ALTER COLUMN directly
    # First update any NULL values to empty string
    op.execute("UPDATE targets SET username = '' WHERE username IS NULL")
    op.alter_column('targets', 'username', nullable=False)
