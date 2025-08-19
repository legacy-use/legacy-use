"""add_rustdesk_to_targettype_enum

Revision ID: 2a2594a812b7
Revises: f2b2b0c1c9ab
Create Date: 2025-08-19 14:55:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '2a2594a812b7'
down_revision: Union[str, None] = 'f2b2b0c1c9ab'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add RUSTDESK to the targettype enum in the shared schema
    op.execute("ALTER TYPE shared.targettype ADD VALUE 'RUSTDESK'")


def downgrade() -> None:
    # Note: PostgreSQL doesn't support removing enum values directly
    # This would require recreating the enum type, which is complex
    # For now, we'll leave the RUSTDESK value in place
    pass
