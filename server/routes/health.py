"""
Database health check and monitoring endpoints.
"""

from fastapi import APIRouter

from server.database.engine import engine

health_router = APIRouter(prefix='/health', tags=['Health'])


@health_router.get('/db')
async def get_database_pool_status():
    """Get current database connection pool status."""
    pool = engine.pool

    return {
        'pool_size': pool.size(),
        'checked_in': pool.checkedin(),
        'checked_out': pool.checkedout(),
        'overflow': pool.overflow(),
        'total_connections': pool.checkedin() + pool.checkedout(),
        'available_connections': pool.checkedin(),
    }
