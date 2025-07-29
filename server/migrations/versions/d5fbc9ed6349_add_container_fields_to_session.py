"""add container fields to session

Revision ID: d5fbc9ed6349
Revises: fcfc272b8ede
Create Date: 2025-03-04 21:35:43.596799

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'd5fbc9ed6349'
down_revision: Union[str, None] = 'fcfc272b8ede'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a table using database-agnostic method."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table)]
    return column in columns


def upgrade() -> None:
    # Add container_id column if it doesn't exist
    if not column_exists('sessions', 'container_id'):
        op.add_column('sessions', sa.Column('container_id', sa.String(), nullable=True))

    # Add mapped_port column if it doesn't exist
    if not column_exists('sessions', 'mapped_port'):
        op.add_column('sessions', sa.Column('mapped_port', sa.String(), nullable=True))


def downgrade() -> None:
    # PostgreSQL supports dropping columns directly
    if column_exists('sessions', 'mapped_port'):
        op.drop_column('sessions', 'mapped_port')
    if column_exists('sessions', 'container_id'):
        op.drop_column('sessions', 'container_id')
