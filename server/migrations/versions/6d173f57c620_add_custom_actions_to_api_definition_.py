"""add custom_actions to api_definition_versions

Revision ID: 6d173f57c620
Revises: f2b2b0c1c9ab
Create Date: 2025-08-29 11:43:13.711977

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from server.migrations.tenant import for_each_tenant_schema

# revision identifiers, used by Alembic.
revision: str = '6d173f57c620'
down_revision: Union[str, None] = 'f2b2b0c1c9ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


@for_each_tenant_schema
def upgrade(schema: str) -> None:
    op.add_column(
        'api_definition_versions',
        sa.Column(
            'custom_actions', postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        schema=schema,
    )


@for_each_tenant_schema
def downgrade(schema: str) -> None:
    op.drop_column('api_definition_versions', 'custom_actions', schema=schema)
