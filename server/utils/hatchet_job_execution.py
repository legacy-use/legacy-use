"""
Hatchet-based job execution logic.

This module provides the same interface as the original job_execution.py
but uses Hatchet for queue management and job processing.
"""

import asyncio
import logging
from typing import Dict, Any

from server.models.base import Job, JobStatus
from server.utils.hatchet_client import hatchet_job_manager
from server.utils.db_dependencies import TenantAwareDatabaseService

logger = logging.getLogger(__name__)

# Keep the same interface for compatibility
running_job_tasks = {}  # This will be managed by Hatchet now


async def initialize_job_queue():
    """Initialize job queues - now handled by Hatchet."""
    logger.info('Job queue initialization now handled by Hatchet')
    # Hatchet handles queue initialization automatically
    pass


async def initialize_job_queue_for_tenant(tenant_schema: str):
    """Initialize job queue for a specific tenant - now handled by Hatchet."""
    logger.info(f'Job queue initialization for tenant {tenant_schema} now handled by Hatchet')
    # Hatchet handles per-tenant queuing automatically
    pass


async def start_job_processor_for_tenant(tenant_schema: str):
    """Start job processor for a specific tenant - now handled by Hatchet workers."""
    logger.info(f'Job processor for tenant {tenant_schema} now handled by Hatchet workers')
    # Hatchet workers handle job processing automatically
    pass


async def process_job_queue_for_tenant(tenant_schema: str):
    """Process jobs for a specific tenant - deprecated in favor of Hatchet."""
    logger.warning(f'process_job_queue_for_tenant is deprecated - using Hatchet workers')
    raise NotImplementedError('Use Hatchet workers for job processing')


async def process_job_with_tenant(job: Job, tenant_schema: str):
    """Process a job using tenant-aware database service - deprecated."""
    logger.warning('process_job_with_tenant is deprecated - using Hatchet workflows')
    raise NotImplementedError('Use Hatchet workflows for job processing')


# Export the function to be used in the main FastAPI app startup
job_queue_initializer = initialize_job_queue


async def enqueue_job(job_obj: Job, tenant_schema: str):
    """
    Enqueue a job for execution via Hatchet.
    
    This function maintains the same interface as the original enqueue_job
    but uses Hatchet for job queuing and execution.
    
    Args:
        job_obj: The Job Pydantic model instance to enqueue.
        tenant_schema: The tenant schema for this job.
    """
    try:
        logger.info(f"Enqueuing job {job_obj.id} for tenant {tenant_schema} via Hatchet")
        
        # Use Hatchet to enqueue the job
        workflow_run_id = await hatchet_job_manager.enqueue_job(job_obj, tenant_schema)
        
        # Store the workflow run ID for tracking if needed
        # Note: This could be stored in the database if needed for monitoring
        running_job_tasks[str(job_obj.id)] = {
            'workflow_run_id': workflow_run_id,
            'tenant_schema': tenant_schema,
            'status': 'queued'
        }
        
        logger.info(f"Job {job_obj.id} successfully enqueued in Hatchet with run ID: {workflow_run_id}")
        
    except Exception as e:
        logger.error(f"Failed to enqueue job {job_obj.id} via Hatchet: {str(e)}")
        raise


# Keep these functions for compatibility but mark as deprecated
async def process_job_queue():
    """Deprecated: This function is no longer used. Use Hatchet workers."""
    logger.warning('process_job_queue is deprecated - use Hatchet workers')
    raise NotImplementedError('Use Hatchet workers')


async def process_next_job():
    """Deprecated: This function is no longer used. Use Hatchet workers."""
    logger.warning('process_next_job is deprecated - use Hatchet workers')
    raise NotImplementedError('Use Hatchet workers')


# Re-export functions that are still used from the original module
from server.utils.job_execution import (
    add_job_log,
    trim_base64_images,
    trim_http_body,
    execute_api_in_background_with_tenant,
    get_target_lock,
    clean_up_target_lock,
    TOKEN_LIMIT,
    # Keep these for backwards compatibility
    targets_with_pending_sessions,
    targets_with_pending_sessions_lock,
    target_locks,
    target_locks_lock,
)