"""
Job lock management utilities.
"""

import asyncio
import logging
from typing import Tuple

from server.models.base import Job, JobStatus
from server.utils.db_dependencies import TenantAwareDatabaseService

logger = logging.getLogger(__name__)

# Add target-specific locks for job status transitions
target_locks = {}
target_locks_lock = asyncio.Lock()


async def get_target_lock(target_id, tenant_schema: str):
    """Get target lock for specific tenant."""
    async with target_locks_lock:
        if target_id not in target_locks:
            target_locks[target_id] = asyncio.Lock()
        return target_locks[target_id]


async def clean_up_target_lock(target_id, tenant_schema: str):
    """Clean up target lock for specific tenant."""
    async with target_locks_lock:
        if target_id in target_locks:
            del target_locks[target_id]


# Helper function for precondition checks
async def _check_preconditions_and_set_running(
    job: Job, job_id_str: str, tenant_schema: str
) -> Tuple[bool, bool]:
    """Check preconditions with tenant context."""
    from server.database.multi_tenancy import with_db

    with with_db(tenant_schema) as db_session:
        db_service = TenantAwareDatabaseService(db_session)

        # Get the latest job status from database
        latest_job = db_service.get_job(job_id_str)
        if not latest_job:
            logger.error(
                f'Job {job_id_str} not found in database for tenant {tenant_schema}'
            )
            return False, False

        if latest_job.get('status') != JobStatus.QUEUED.value:
            logger.info(
                f'Job {job_id_str} status is {latest_job.get("status")}, not QUEUED for tenant {tenant_schema}'
            )
            return False, False

        # Check if target is available
        target_id = job.target_id
        target_lock = await get_target_lock(target_id, tenant_schema)

        if target_lock.locked():
            logger.info(
                f'Target {target_id} is locked, skipping job {job_id_str} for tenant {tenant_schema}'
            )
            return False, False

        # Try to acquire target lock non-blocking
        if target_lock.locked():
            logger.info(
                f'Could not acquire target lock for {target_id}, skipping job {job_id_str} for tenant {tenant_schema}'
            )
            return False, False

        await target_lock.acquire()

        try:
            # Update job status to RUNNING
            db_service.update_job_status(job_id_str, JobStatus.RUNNING.value)
            logger.info(
                f'Set job {job_id_str} to RUNNING status for tenant {tenant_schema}'
            )
            return True, True
        except Exception as e:
            logger.error(
                f'Failed to update job {job_id_str} status: {e} for tenant {tenant_schema}'
            )
            target_lock.release()
            return False, False
