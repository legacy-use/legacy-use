"""add_recovery_feature

Revision ID: b1c2d3e4f5a6
Revises: 0a7bc5c94ccb
Create Date: 2025-08-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5a6'
down_revision: Union[str, None] = '0a7bc5c94ccb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add recovery_prompt column to tenant_default.api_definition_versions
    op.add_column(
        'api_definition_versions',
        sa.Column('recovery_prompt', sa.String(), nullable=True),
        schema='tenant_default',
    )

    # Extend shared.jobstatus enum with new values (PostgreSQL-specific)
    # Note: Adding values is irreversible in PostgreSQL enums; IF NOT EXISTS avoids errors on re-run
    op.execute("ALTER TYPE shared.jobstatus ADD VALUE IF NOT EXISTS 'RECOVERY'")
    op.execute("ALTER TYPE shared.jobstatus ADD VALUE IF NOT EXISTS 'FAILED'")


def downgrade() -> None:
    # Remove recovery_prompt column
    op.drop_column('api_definition_versions', 'recovery_prompt', schema='tenant_default')
    # Enum value removal is not supported in a straightforward way; leave as-is
    pass

