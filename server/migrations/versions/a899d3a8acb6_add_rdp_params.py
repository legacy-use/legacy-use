"""add rdp params

Revision ID: a899d3a8acb6
Revises: f705ed66700e
Create Date: 2025-08-11 00:10:11.887893

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from server.migrations.tenant import for_each_tenant_schema

# revision identifiers, used by Alembic.
revision: str = 'a899d3a8acb6'
down_revision: Union[str, None] = 'f705ed66700e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


@for_each_tenant_schema
def upgrade(schema: str) -> None:
    op.add_column(
        'targets',
        sa.Column('rdp_params', sa.String(), nullable=True),
        schema='tenant_default',
    )


@for_each_tenant_schema
def downgrade(schema: str) -> None:
    op.drop_column('targets', 'rdp_params', schema='tenant_default')
