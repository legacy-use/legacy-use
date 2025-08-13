"""
Log pruning utilities for multi-tenant database cleanup.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from server.database.models import JobLog
from server.database.multi_tenancy import with_db
from server.settings import settings
from server.utils.tenant_utils import get_active_tenants

logger = logging.getLogger(__name__)


def prune_old_logs_for_tenant(tenant_schema: str, days: int = 7) -> int:
    """
    Prune old logs for a specific tenant using tenant-aware database connection.

    Args:
        tenant_schema: The tenant schema to prune logs for
        days: Number of days to keep logs (default: 7)

    Returns:
        Number of deleted log records
    """
    with with_db(tenant_schema) as db_tenant:
        cutoff_date = datetime.now() - timedelta(days=days)
        deleted_count = (
            db_tenant.query(JobLog).filter(JobLog.timestamp < cutoff_date).delete()
        )
        db_tenant.commit()
        return deleted_count


async def prune_old_logs_all_tenants(days: Optional[int] = None) -> dict:
    """
    Prune old logs for all active tenants.

    Args:
        days: Number of days to keep logs (defaults to settings.LOG_RETENTION_DAYS)

    Returns:
        Dictionary with tenant schema as key and number of deleted records as value
    """
    if days is None:
        days = settings.LOG_RETENTION_DAYS

    # Get all active tenants
    tenants = get_active_tenants()

    results = {}
    total_deleted = 0

    for tenant in tenants:
        try:
            deleted_count = prune_old_logs_for_tenant(tenant['schema'], days)
            results[tenant['schema']] = deleted_count
            total_deleted += deleted_count

            if deleted_count > 0:
                logger.info(
                    f'Pruned {deleted_count} logs for tenant {tenant["name"]} '
                    f'({tenant["schema"]}) older than {days} days'
                )
        except Exception as e:
            logger.error(
                f'Error pruning logs for tenant {tenant["name"]} ({tenant["schema"]}): {str(e)}'
            )
            results[tenant['schema']] = 0

    logger.info(f'Total logs pruned across all tenants: {total_deleted}')
    return results


async def scheduled_log_pruning():
    """
    Scheduled task to prune logs for all tenants.
    Runs once a day at midnight.
    """
    while True:
        try:
            # Sleep until next pruning time (once a day at midnight)
            now = datetime.now()
            next_run = (now + timedelta(days=1)).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            sleep_seconds = (next_run - now).total_seconds()
            logger.info(
                f'Next log pruning scheduled in {sleep_seconds / 3600:.1f} hours'
            )
            await asyncio.sleep(sleep_seconds)

            # Prune logs for all tenants
            results = await prune_old_logs_all_tenants()

            # Log summary
            total_deleted = sum(results.values())
            active_tenants = len([r for r in results.values() if r > 0])
            logger.info(
                f'Pruned {total_deleted} logs across {active_tenants} tenants '
                f'older than {settings.LOG_RETENTION_DAYS} days'
            )

        except Exception as e:
            logger.error(f'Error in scheduled log pruning: {str(e)}')
            await asyncio.sleep(3600)  # Sleep for an hour and try again
