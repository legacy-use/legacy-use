"""init_settings_and_rdp_params

Revision ID: 1c2d3e4f0001
Revises: 0a7bc5c94ccb
Create Date: 2025-08-08 12:35:00.000000

"""

from typing import Sequence, Union

from alembic import op

from server.migrations.tenant import for_each_tenant_schema


# revision identifiers, used by Alembic.
revision: str = '1c2d3e4f0001'
down_revision: Union[str, None] = '0a7bc5c94ccb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


@for_each_tenant_schema
def upgrade(schema: str) -> None:
    # Create settings table per tenant (idempotent)
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {schema}.settings (
            id UUID PRIMARY KEY,
            key VARCHAR(256) NOT NULL,
            value VARCHAR(4096),
            created_at TIMESTAMP,
            updated_at TIMESTAMP
        )
        """
    )
    op.execute(
        f"""
        CREATE INDEX IF NOT EXISTS ix_settings_key ON {schema}.settings (key)
        """
    )

    # Add RDP params to targets (idempotent)
    op.execute(
        f"""
        ALTER TABLE {schema}.targets ADD COLUMN IF NOT EXISTS rdp_params VARCHAR
        """
    )

    # Seed API key for default tenant if not present
    if schema == 'tenant_default':
        op.execute(
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM tenant_default.settings WHERE key = 'API_KEY'
                ) THEN
                    INSERT INTO tenant_default.settings (id, key, value, created_at, updated_at)
                    VALUES (
                        gen_random_uuid(),
                        'API_KEY',
                        encode(gen_random_bytes(24), 'hex'),
                        NOW(),
                        NOW()
                    );
                END IF;
            END$$;
            """
        )


@for_each_tenant_schema
def downgrade(schema: str) -> None:
    # Drop merged changes (idempotent safe drops)
    op.execute(f"""ALTER TABLE {schema}.targets DROP COLUMN IF EXISTS rdp_params""")
    op.execute(f"""DROP INDEX IF EXISTS {schema}.ix_settings_key""")
    op.execute(f"""DROP TABLE IF EXISTS {schema}.settings""")
