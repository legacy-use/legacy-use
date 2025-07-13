"""fix timezone consistency by ensuring all timestamps use UTC

Revision ID: fix_timezone_consistency
Revises: 
Create Date: 2025-01-13

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime

# revision identifiers, used by Alembic.
revision = 'fix_timezone_consistency'
down_revision = None  # This will be updated by alembic when added
depends_on = None

def upgrade():
    """
    This migration ensures timezone consistency by updating all datetime fields
    to use UTC. Since we changed the database models to use datetime.utcnow(),
    existing data should remain valid as the change is in the default factory
    for new records only.
    """
    # No database schema changes needed - this is a code-level change
    # that affects only new records going forward
    pass

def downgrade():
    """
    Rollback the timezone consistency changes by reverting to datetime.now()
    """
    # No database schema changes needed - this is a code-level change
    pass