"""add content_trimmed column to job_logs

Revision ID: e822d56c493a
Revises: 716d08899bce
Create Date: 2025-04-24 22:36:46.099417

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'e822d56c493a'
down_revision: Union[str, None] = '716d08899bce'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if content_trimmed column already exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [column['name'] for column in inspector.get_columns('job_logs')]

    # Only proceed if the column doesn't already exist
    if 'content_trimmed' not in columns:
        # PostgreSQL implementation
        op.add_column(
            'job_logs',
            sa.Column('content_trimmed', postgresql.JSONB(), nullable=True),
        )
    else:
        print("Column 'content_trimmed' already exists in 'job_logs' table. Skipping.")


def downgrade() -> None:
    # Check if content_trimmed column exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [column['name'] for column in inspector.get_columns('job_logs')]

    # Only attempt to drop the column if it exists
    if 'content_trimmed' in columns:
        # PostgreSQL implementation
        op.drop_column('job_logs', 'content_trimmed')
    else:
        print(
            "Column 'content_trimmed' does not exist in 'job_logs' table. Skipping downgrade."
        )
