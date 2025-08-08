"""
Tenant-aware migration utilities for Alembic.
"""

import functools
from typing import Callable

from alembic import op
from sqlalchemy import text


def for_each_tenant_schema(func: Callable) -> Callable:
    """Decorator that applies a migration function to each tenant schema."""

    @functools.wraps(func)
    def wrapped():
        schemas = (
            op.get_bind().execute(text('SELECT schema FROM shared.tenants')).fetchall()
        )
        for (schema,) in schemas:
            func(schema)

    return wrapped
