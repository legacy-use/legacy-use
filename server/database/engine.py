"""
Centralized SQLAlchemy engine and session factory.

All database access should reuse this shared engine to avoid creating
multiple connection pools.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from server.settings import settings

# Create a single shared engine using application settings
engine = create_engine(
    settings.DATABASE_URL,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_timeout=settings.DATABASE_POOL_TIMEOUT,
    pool_recycle=settings.DATABASE_POOL_RECYCLE,
    pool_pre_ping=settings.DATABASE_POOL_PRE_PING,
)

# Shared session factory bound to the shared engine
SessionLocal = sessionmaker(bind=engine)

__all__ = ['engine', 'SessionLocal']
