"""add recovery prompt 2

Revision ID: ac7780c93e39
Revises: 32f7863ea65d
Create Date: 2025-09-01 12:30:50.419613

"""

from typing import Sequence, Union

from alembic import op
from alembic_postgresql_enum import TableReference

from server.migrations.tenant import for_each_tenant_schema

# revision identifiers, used by Alembic.
revision: str = 'ac7780c93e39'
down_revision: Union[str, None] = '32f7863ea65d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


@for_each_tenant_schema
def upgrade(schema: str) -> None:
    op.sync_enum_values(
        enum_schema='shared',
        enum_name='jobstatus',
        new_values=[
            'PENDING',
            'QUEUED',
            'RUNNING',
            'RECOVERY',
            'PAUSED',
            'SUCCESS',
            'FAILED',
            'ERROR',
            'CANCELED',
        ],
        affected_columns=[
            TableReference(table_schema=schema, table_name='jobs', column_name='status')
        ],
        enum_values_to_rename=[],
    )


@for_each_tenant_schema
def downgrade(schema: str) -> None:
    op.sync_enum_values(
        enum_schema='shared',
        enum_name='jobstatus',
        new_values=[
            'PENDING',
            'QUEUED',
            'RUNNING',
            'PAUSED',
            'SUCCESS',
            'ERROR',
            'CANCELED',
        ],
        affected_columns=[
            TableReference(table_schema=schema, table_name='jobs', column_name='status')
        ],
        enum_values_to_rename=[],
    )
