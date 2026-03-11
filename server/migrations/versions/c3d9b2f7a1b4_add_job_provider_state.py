"""add job provider_state

Revision ID: c3d9b2f7a1b4
Revises: 2478611410c3
Create Date: 2026-03-11 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from server.migrations.tenant import for_each_tenant_schema

revision = 'c3d9b2f7a1b4'
down_revision = '2478611410c3'
branch_labels = None
depends_on = None


@for_each_tenant_schema
def upgrade(schema: str = 'tenant') -> None:
    with op.batch_alter_table('jobs', schema=schema) as batch_op:
        batch_op.add_column(
            sa.Column(
                'provider_state',
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=True,
            )
        )


@for_each_tenant_schema
def downgrade(schema: str = 'tenant') -> None:
    with op.batch_alter_table('jobs', schema=schema) as batch_op:
        batch_op.drop_column('provider_state')
