"""add_rdp_params_to_targets

Revision ID: 3b2c9a1d4a10
Revises: f705ed66700e
Create Date: 2025-08-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from server.migrations.tenant import for_each_tenant_schema


# revision identifiers, used by Alembic.
revision: str = '3b2c9a1d4a10'
down_revision: Union[str, None] = 'f705ed66700e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


@for_each_tenant_schema
def upgrade(schema: str) -> None:
    # Add custom RDP fields to targets table for each tenant schema
    op.add_column(
        'targets',
        sa.Column('rdp_params', sa.String(), nullable=True),
        schema=schema,
    )


@for_each_tenant_schema
def downgrade(schema: str) -> None:
    # Remove fields on downgrade
    op.drop_column('targets', 'rdp_params', schema=schema)
