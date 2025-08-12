"""
Shared database service instance for operations that span tenants.
"""

from server.database.service import DatabaseService


# Create a single shared database service using the centralized engine
db_shared = DatabaseService()

__all__ = ['db_shared']
