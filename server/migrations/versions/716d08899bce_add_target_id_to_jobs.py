"""add_target_id_to_jobs

Revision ID: 716d08899bce
Revises: 7f239bd86566
Create Date: 2025-04-15 15:51:04.574253

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

# revision identifiers, used by Alembic.
revision: str = '716d08899bce'
down_revision: Union[str, None] = '7f239bd86566'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define Base
Base = declarative_base()


def upgrade() -> None:
    # Check if target_id column already exists in jobs table
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [column['name'] for column in inspector.get_columns('jobs')]

    # Only add the column if it doesn't already exist
    if 'target_id' not in columns:
        # Add target_id column to jobs table
        op.add_column(
            'jobs', sa.Column('target_id', sa.String(length=36), nullable=True)
        )

    # PostgreSQL supports adding foreign keys with ALTER TABLE
    # Check if the foreign key constraint already exists
    try:
        # Create foreign key
        op.create_foreign_key(
            'fk_jobs_target_id',
            'jobs',
            'targets',
            ['target_id'],
            ['id'],
            ondelete='SET NULL',
        )
    except Exception as e:
        # If the constraint already exists or there's another issue, log it but continue
        print(f'Note: Could not create foreign key constraint: {e}')

    # Data migration
    # Bind a connection to use for data migration
    session = Session(bind=connection)

    try:
        # Find all jobs with a session_id
        jobs_with_session = session.execute(
            text('SELECT id, session_id FROM jobs WHERE session_id IS NOT NULL')
        ).fetchall()

        for job_id, session_id in jobs_with_session:
            # Find the target_id associated with this session
            target_result = session.execute(
                text('SELECT target_id FROM sessions WHERE id = :session_id'),
                {'session_id': session_id},
            ).fetchone()

            if target_result and target_result[0]:
                # Update the job with the target_id
                session.execute(
                    text('UPDATE jobs SET target_id = :target_id WHERE id = :job_id'),
                    {'target_id': target_result[0], 'job_id': job_id},
                )

        # Commit all changes
        session.commit()

    except Exception as e:
        session.rollback()
        raise e
    finally:
        session.close()


def downgrade() -> None:
    # Try to drop the foreign key constraint first
    try:
        op.drop_constraint('fk_jobs_target_id', 'jobs', type_='foreignkey')
    except Exception as e:
        print(f'Note: Could not drop foreign key constraint: {e}')

    # Check if target_id column exists before trying to drop it
    connection = op.get_bind()
    inspector = sa.inspect(connection)
    columns = [column['name'] for column in inspector.get_columns('jobs')]

    # Only drop the column if it exists
    if 'target_id' in columns:
        # Then drop the column
        op.drop_column('jobs', 'target_id')
