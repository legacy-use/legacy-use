"""add_session_logs_table

Revision ID: 665ceaa89e85
Revises: 3814b7855961
Create Date: 2025-08-05 10:34:59.435535

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


# revision identifiers, used by Alembic.
revision: str = '665ceaa89e85'
down_revision: Union[str, None] = '3814b7855961'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if session_logs table already exists
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    if 'session_logs' not in inspector.get_table_names():
        # Create session_logs table
        op.create_table(
            'session_logs',
            sa.Column('id', UUID, primary_key=True),
            sa.Column('session_id', UUID, sa.ForeignKey('sessions.id'), nullable=False),
            sa.Column('timestamp', sa.DateTime, nullable=False),
            sa.Column('log_type', sa.String, nullable=False),
            sa.Column('content', JSONB, nullable=False),
        )
    else:
        print("Table 'session_logs' already exists, skipping creation.")


def downgrade() -> None:
    # Drop session_logs table
    op.drop_table('session_logs')
