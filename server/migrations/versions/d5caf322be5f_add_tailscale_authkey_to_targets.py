"""add_tailscale_authkey_to_targets

Revision ID: d5caf322be5f
Revises: 95932493eb61
Create Date: 2025-03-07 19:03:29.072389

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'd5caf322be5f'
down_revision: Union[str, None] = '95932493eb61'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a table using database-agnostic method."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table)]
    return column in columns


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    if not column_exists('targets', 'tailscale_authkey'):
        op.add_column(
            'targets', sa.Column('tailscale_authkey', sa.String(), nullable=True)
        )
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    if column_exists('targets', 'tailscale_authkey'):
        op.drop_column('targets', 'tailscale_authkey')
    # ### end Alembic commands ###
