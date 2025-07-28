"""Add multi-tenancy support

Revision ID: 001_multitenancy
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite
from sqlalchemy.schema import CreateSchema


# revision identifiers, used by Alembic.
revision = '001_multitenancy'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Upgrade to multi-tenant database structure."""
    
    # Create shared schema for tenant management
    try:
        op.execute(CreateSchema('shared', if_not_exists=True))
    except Exception:
        # Schema might already exist or not supported (SQLite)
        pass
    
    # Create tenants table in shared schema
    op.create_table(
        'tenants',
        sa.Column('id', sa.String(), nullable=False),  # UUID as string
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('subdomain', sa.String(100), nullable=False),
        sa.Column('schema_name', sa.String(100), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, default='active'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('api_key_hash', sa.String(255), nullable=False),
        sa.Column('api_key_salt', sa.String(255), nullable=False),
        sa.Column('settings', sa.JSON(), nullable=False, default='{}'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('subdomain'),
        sa.UniqueConstraint('schema_name'),
        schema='shared'
    )
    
    # Create indexes for performance
    op.create_index('ix_tenants_subdomain', 'tenants', ['subdomain'], unique=True, schema='shared')


def downgrade():
    """Downgrade from multi-tenant structure."""
    
    # Drop tenant table
    op.drop_table('tenants', schema='shared')
    
    # Note: We don't drop the shared schema as it might be used by other tables
    # and schema dropping is not universally supported