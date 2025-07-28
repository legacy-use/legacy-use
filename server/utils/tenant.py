"""
Tenant utilities for multi-tenancy support.
"""

import hashlib
import logging
import secrets
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.schema import CreateSchema

from server.database.models import TenantModel, get_tenant_base
from server.settings import settings

logger = logging.getLogger(__name__)


def generate_api_key() -> str:
    """Generate a secure API key."""
    return secrets.token_urlsafe(32)


def hash_api_key(api_key: str, salt: str = None) -> tuple[str, str]:
    """Hash an API key with salt for secure storage."""
    if salt is None:
        salt = secrets.token_hex(16)
    
    # Use PBKDF2 for secure hashing
    key_hash = hashlib.pbkdf2_hmac('sha256', api_key.encode(), salt.encode(), 100000)
    return key_hash.hex(), salt


def verify_api_key(api_key: str, stored_hash: str, salt: str) -> bool:
    """Verify an API key against stored hash."""
    key_hash, _ = hash_api_key(api_key, salt)
    return secrets.compare_digest(key_hash, stored_hash)


def generate_schema_name(subdomain: str) -> str:
    """Generate a schema name from subdomain."""
    # Ensure schema name is valid and unique
    return f"tenant_{subdomain.lower().replace('-', '_')}"


@contextmanager
def get_tenant_db_session(tenant_schema: Optional[str] = None):
    """
    Get a database session with tenant schema mapping.
    
    Args:
        tenant_schema: The tenant schema name. If None, uses shared schema only.
    """
    engine = create_engine(settings.DATABASE_URL)
    
    if tenant_schema:
        # Set up schema translation map for tenant-specific operations
        schema_translate_map = {'tenant': tenant_schema}
        connectable = engine.execution_options(schema_translate_map=schema_translate_map)
    else:
        connectable = engine
    
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=connectable)
    session = SessionLocal()
    
    try:
        yield session
    finally:
        session.close()


def create_tenant_schema(schema_name: str) -> None:
    """Create a new tenant schema and tables."""
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.begin() as conn:
        # Create the schema
        conn.execute(CreateSchema(schema_name, if_not_exists=True))
        logger.info(f"Created schema: {schema_name}")
        
        # Create tenant-specific tables
        TenantBase = get_tenant_base(schema_name)
        TenantBase.metadata.create_all(bind=conn)
        logger.info(f"Created tables in schema: {schema_name}")


def get_shared_metadata() -> MetaData:
    """Get metadata for shared tables only."""
    from sqlalchemy import MetaData
    from server.database.models import Base
    
    meta = MetaData(schema='shared')
    for table in Base.metadata.tables.values():
        if table.schema == 'shared':
            table.tometadata(meta)
    return meta


def get_tenant_metadata() -> MetaData:
    """Get metadata for tenant-specific tables."""
    from sqlalchemy import MetaData
    from server.database.models import TenantBase
    
    meta = MetaData(schema='tenant')
    for table in TenantBase.metadata.tables.values():
        if table.schema == 'tenant':
            table.tometadata(meta)
    return meta


def initialize_shared_schema() -> None:
    """Initialize the shared schema and tables."""
    engine = create_engine(settings.DATABASE_URL)
    
    with engine.begin() as conn:
        # Create shared schema
        conn.execute(CreateSchema('shared', if_not_exists=True))
        logger.info("Created shared schema")
        
        # Create shared tables
        shared_metadata = get_shared_metadata()
        shared_metadata.create_all(bind=conn)
        logger.info("Created shared tables")


class TenantContext:
    """Context manager for tenant operations."""
    
    def __init__(self, tenant_schema: str):
        self.tenant_schema = tenant_schema
        self._session = None
    
    def __enter__(self):
        self._session = get_tenant_db_session(self.tenant_schema).__enter__()
        return self._session
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._session:
            self._session.__exit__(exc_type, exc_val, exc_tb)


def get_tenant_by_subdomain(subdomain: str) -> Optional[TenantModel]:
    """Get tenant by subdomain."""
    with get_tenant_db_session() as session:
        return session.query(TenantModel).filter(
            TenantModel.subdomain == subdomain
        ).first()


def get_tenant_by_api_key(api_key: str) -> Optional[TenantModel]:
    """Get tenant by API key."""
    with get_tenant_db_session() as session:
        tenants = session.query(TenantModel).all()
        
        for tenant in tenants:
            if verify_api_key(api_key, tenant.api_key_hash, tenant.api_key_salt):
                return tenant
    
    return None