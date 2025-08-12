"""
Multi-tenancy utilities using SQLAlchemy schema translation.
"""

from contextlib import contextmanager
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.orm import Session

from server.database.models import Base, Tenant
from server.database.service import DatabaseService


# Single default DatabaseService (engine + pool) reused across tenant sessions
db_session = DatabaseService()


def get_shared_metadata():
    meta = sa.MetaData()
    for table in Base.metadata.tables.values():
        if table.schema != 'tenant':
            table.tometadata(meta)
    return meta


def get_tenant_specific_metadata():
    """Get metadata for tenant-specific tables."""
    meta = sa.MetaData(schema='tenant')
    for table in Base.metadata.tables.values():
        if table.schema == 'tenant':
            table.tometadata(meta)
    return meta


@contextmanager
def with_db(tenant_schema: Optional[str]):
    """Context manager that returns a database session with tenant mapping."""

    if tenant_schema:
        schema_translate_map = dict(tenant=tenant_schema)
    else:
        schema_translate_map = None

    connectable = db_session.engine.execution_options(
        schema_translate_map=schema_translate_map
    )

    try:
        db = Session(autocommit=False, autoflush=False, bind=connectable)
        yield db
    finally:
        db.close()


def tenant_create(name: str, schema: str, host: str) -> None:
    """Create a new tenant with its schema and tables."""

    # Check schema name against blacklist
    blacklisted_names = {'cloud', 'www', 'admin', 'local', 'api'}
    if schema.lower() in blacklisted_names:
        raise ValueError(f'Schema name "{schema}" is not allowed (blacklisted)')

    with with_db(schema) as db_tenant:
        # Create tenant record
        tenant = Tenant(
            name=name,
            host=host,
            schema=schema,
        )
        db_tenant.add(tenant)

        # Create schema and tables
        db_tenant.execute(sa.schema.CreateSchema(schema))
        get_tenant_specific_metadata().create_all(bind=db_tenant.connection())

        db_tenant.commit()


def tenant_delete(schema: str) -> None:
    """Delete a tenant and its schema."""
    with with_db(schema) as db_tenant:
        # Drop the schema (this will drop all tables in the schema)
        db_tenant.execute(sa.schema.DropSchema(schema, cascade=True))

        # Remove tenant record
        tenant = db_tenant.query(Tenant).filter(Tenant.schema == schema).first()
        if tenant:
            db_tenant.delete(tenant)

        db_tenant.commit()


def get_tenant_by_host(host: str) -> Optional[Tenant]:
    """Get tenant by host."""
    session = db_session.Session()
    try:
        return session.query(Tenant).filter(Tenant.host == host).first()
    finally:
        session.close()


def get_tenant_by_schema(schema: str) -> Optional[Tenant]:
    """Get tenant by schema."""
    session = db_session.Session()
    try:
        return session.query(Tenant).filter(Tenant.schema == schema).first()
    finally:
        session.close()
