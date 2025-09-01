"""add recovery prompt

Revision ID: 32f7863ea65d
Revises: f2b2b0c1c9ab
Create Date: 2025-09-01 12:02:30.328309

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from server.migrations.tenant import for_each_tenant_schema

# revision identifiers, used by Alembic.
revision: str = '32f7863ea65d'
down_revision: Union[str, None] = 'f2b2b0c1c9ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


@for_each_tenant_schema
def upgrade(schema: str) -> None:
    op.add_column(
        'api_definition_versions',
        sa.Column('recovery_prompt', sa.String(), nullable=True),
        schema='tenant_default',
    )


@for_each_tenant_schema
def downgrade(schema: str) -> None:
    op.drop_column(
        'api_definition_versions', 'recovery_prompt', schema='tenant_default'
    )
