"""add width and height columns to targets

Revision ID: add_width_height_to_targets
Revises: fcfc272b8ede
Create Date: 2023-05-23 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision = 'add_width_height_to_targets'
down_revision = 'fcfc272b8ede'
branch_labels = None
depends_on = None


def column_exists(table: str, column: str) -> bool:
    """Check if a column exists in a table using database-agnostic method."""
    conn = op.get_bind()
    inspector = inspect(conn)
    columns = [col['name'] for col in inspector.get_columns(table)]
    return column in columns


def upgrade():
    # Add width column if it doesn't exist
    if not column_exists('targets', 'width'):
        op.add_column(
            'targets',
            sa.Column('width', sa.String(), nullable=True, server_default='1024'),
        )

    # Add height column if it doesn't exist
    if not column_exists('targets', 'height'):
        op.add_column(
            'targets',
            sa.Column('height', sa.String(), nullable=True, server_default='768'),
        )

    # Update existing records to set width and height to the default values
    op.execute("UPDATE targets SET width = '1024' WHERE width IS NULL")
    op.execute("UPDATE targets SET height = '768' WHERE height IS NULL")


def downgrade():
    # PostgreSQL supports dropping columns directly
    if column_exists('targets', 'height'):
        op.drop_column('targets', 'height')
    if column_exists('targets', 'width'):
        op.drop_column('targets', 'width')
