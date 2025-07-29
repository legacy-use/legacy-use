"""Add job_messages table for conversation history

Revision ID: e56b923957b6
Revises: e822d56c493a
Create Date: 2025-05-04 13:00:07.981016

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# Import inspect for checking table existence
from sqlalchemy import inspect

# revision identifiers, used by Alembic.
revision: str = 'e56b923957b6'
down_revision: Union[str, None] = 'e822d56c493a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### Manually added commands with existence check ###
    bind = op.get_bind()
    inspector = inspect(bind)

    if not inspector.has_table('job_messages'):
        op.create_table(
            'job_messages',
            sa.Column(
                'id', sa.TEXT(), nullable=False
            ),  # Using TEXT based on custom UUID
            sa.Column(
                'job_id', sa.TEXT(), nullable=False
            ),  # Using TEXT based on custom UUID
            sa.Column('sequence', sa.Integer(), nullable=False),
            sa.Column('role', sa.String(), nullable=False),
            sa.Column(
                'message_content', sa.JSON(), nullable=False
            ),  # Using generic JSON
            # Use server_default for broader compatibility, especially with PostgreSQL
            sa.Column(
                'created_at',
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.now(),
            ),
            sa.ForeignKeyConstraint(['job_id'], ['jobs.id'], ondelete='CASCADE'),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index(
            'ix_jobmessage_job_id_sequence',
            'job_messages',
            ['job_id', 'sequence'],
            unique=False,
        )
        op.create_index(
            op.f('ix_job_messages_job_id'), 'job_messages', ['job_id'], unique=False
        )  # Explicit index on job_id
    else:
        print("Table 'job_messages' already exists, skipping creation.")
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### Manually added commands ###
    # Optional: Add check here too for robustness
    bind = op.get_bind()
    inspector = inspect(bind)

    if inspector.has_table('job_messages'):
        op.drop_index(op.f('ix_job_messages_job_id'), table_name='job_messages')
        op.drop_index('ix_jobmessage_job_id_sequence', table_name='job_messages')
        op.drop_table('job_messages')
    else:
        print("Table 'job_messages' does not exist, skipping drop.")
    # ### end Alembic commands ###
