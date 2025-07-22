"""add_interactive_mode_tables

Revision ID: 1f985ec5ec19
Revises: 3814b7855961
Create Date: 2025-07-22 21:51:42.766135

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1f985ec5ec19'
down_revision: Union[str, None] = '3814b7855961'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create workflows table
    op.create_table('workflows',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('session_id', sa.String(), nullable=False),
    sa.Column('steps', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create recordings table
    op.create_table('recordings',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('session_id', sa.String(), nullable=False),
    sa.Column('workflow_id', sa.String(), nullable=True),
    sa.Column('filename', sa.String(), nullable=False),
    sa.Column('file_path', sa.String(), nullable=True),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('duration', sa.Integer(), nullable=True),
    sa.Column('status', sa.String(), nullable=True),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('extracted_actions', sa.JSON(), nullable=True),
    sa.Column('started_at', sa.DateTime(), nullable=True),
    sa.Column('stopped_at', sa.DateTime(), nullable=True),
    sa.Column('processed_at', sa.DateTime(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create actions table
    op.create_table('actions',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('workflow_id', sa.String(), nullable=False),
    sa.Column('step_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('description', sa.String(), nullable=True),
    sa.Column('action_type', sa.String(), nullable=False),
    sa.Column('parameters', sa.JSON(), nullable=True),
    sa.Column('expected_ui', sa.String(), nullable=True),
    sa.Column('custom_prompt', sa.String(), nullable=True),
    sa.Column('order_index', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(), nullable=True),
    sa.Column('updated_at', sa.DateTime(), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=True),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    
    # Create execution_logs table
    op.create_table('execution_logs',
    sa.Column('id', sa.String(), nullable=False),
    sa.Column('session_id', sa.String(), nullable=False),
    sa.Column('workflow_id', sa.String(), nullable=True),
    sa.Column('action_id', sa.String(), nullable=True),
    sa.Column('step_id', sa.String(), nullable=True),
    sa.Column('action_type', sa.String(), nullable=False),
    sa.Column('parameters', sa.JSON(), nullable=True),
    sa.Column('result', sa.JSON(), nullable=True),
    sa.Column('success', sa.Boolean(), nullable=True),
    sa.Column('error_message', sa.String(), nullable=True),
    sa.Column('execution_time_ms', sa.Integer(), nullable=True),
    sa.Column('executed_at', sa.DateTime(), nullable=True),
    sa.ForeignKeyConstraint(['action_id'], ['actions.id'], ),
    sa.ForeignKeyConstraint(['workflow_id'], ['workflows.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    op.drop_table('execution_logs')
    op.drop_table('actions')
    op.drop_table('recordings')
    op.drop_table('workflows')
