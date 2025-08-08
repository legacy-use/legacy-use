"""
Database dependencies with tenant-aware schema mapping.
"""

from typing import Generator

from fastapi import Depends
from sqlalchemy.orm import Session
from starlette.websockets import WebSocket

from server.database.multi_tenancy import with_db
from server.database.service import DatabaseService
from server.utils.tenant_utils import get_tenant_from_request


class TenantAwareDatabaseService(DatabaseService):
    """Database service that uses tenant-aware sessions."""

    def __init__(self, tenant_session: Session):
        # Store the tenant session
        self.tenant_session = tenant_session

        # Create a session factory that returns the tenant session
        # We need to handle the session lifecycle properly since the original
        # DatabaseService expects to create and close sessions
        def get_tenant_session():
            # Return a wrapper that doesn't actually close the session
            # since it's managed by the context manager
            class SessionWrapper:
                def __init__(self, session):
                    self._session = session

                def __getattr__(self, name):
                    return getattr(self._session, name)

                def close(self):
                    # Don't actually close the session since it's managed by context
                    pass

            return SessionWrapper(self.tenant_session)

        # Override the Session property to use our tenant session
        self.Session = get_tenant_session


def get_tenant_from_websocket(websocket: WebSocket) -> dict:
    """
    Extract tenant information from websocket headers.

    Args:
        websocket: WebSocket object containing headers

    Returns:
        Dictionary containing tenant information (name, schema, etc.)
    """
    # Extract host from websocket headers
    host = websocket.headers.get('host', '')

    if not host:
        raise ValueError('No host header found in websocket request')

    # Remove port if present
    if ':' in host:
        host = host.split(':')[0]

    # Import here to avoid circular imports
    from server.database.multi_tenancy import get_tenant_by_host
    from server.utils.exceptions import TenantNotFoundError, TenantInactiveError

    # Look up tenant by host
    tenant = get_tenant_by_host(host)

    if not tenant:
        raise TenantNotFoundError(f'No tenant found for host: {host}')

    if not tenant.is_active:
        raise TenantInactiveError(f'Tenant {tenant.name} is inactive')

    # Return tenant information as dictionary
    return {
        'id': str(tenant.id),
        'name': tenant.name,
        'host': tenant.host,
        'schema': tenant.schema,
        'is_active': tenant.is_active,
    }


def get_tenant_db(
    tenant: dict = Depends(get_tenant_from_request),
) -> Generator[TenantAwareDatabaseService, None, None]:
    """
    Get a database service with tenant-specific schema mapping.

    This function automatically uses the correct schema remapping based on the tenant
    making the request. All queries are then automatically run against the correct tenant.

    Args:
        tenant: Tenant information from get_tenant dependency

    Yields:
        TenantAwareDatabaseService: Database service with tenant schema mapping
    """
    with with_db(tenant['schema']) as db_session:
        db_service = TenantAwareDatabaseService(db_session)
        yield db_service


def get_shared_db() -> Generator[DatabaseService, None, None]:
    """
    Get a shared database service for operations that need access to shared data.

    This function provides access to the shared database instance for operations
    that need to work across all tenants (like tenant management).

    Yields:
        DatabaseService: Shared database service
    """
    from server.database import db_shared

    yield db_shared


def get_tenant_db_websocket(
    websocket: WebSocket,
) -> Generator[TenantAwareDatabaseService, None, None]:
    """
    Get a database service with tenant-specific schema mapping for WebSocket connections.

    This function automatically uses the correct schema remapping based on the tenant
    making the websocket request. All queries are then automatically run against the correct tenant.

    Args:
        websocket: WebSocket object containing headers

    Yields:
        TenantAwareDatabaseService: Database service with tenant schema mapping
    """
    tenant = get_tenant_from_websocket(websocket)
    with with_db(tenant['schema']) as db_session:
        db_service = TenantAwareDatabaseService(db_session)
        yield db_service
