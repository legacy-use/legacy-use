"""
Database package for the API Gateway.
"""

from .service import DatabaseService

# Create a single shared database instance
db_shared = DatabaseService()

__all__ = ['DatabaseService', 'db_shared']
