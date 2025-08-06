"""add vpn_container_id to sessions

Revision ID: vpn_container_id_001
Revises: 222c1b640d27
Create Date: 2025-01-27 12:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'vpn_container_id_001'
down_revision = '222c1b640d27'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add vpn_container_id column to sessions table."""
    op.add_column('sessions', sa.Column('vpn_container_id', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove vpn_container_id column from sessions table."""
    op.drop_column('sessions', 'vpn_container_id')
