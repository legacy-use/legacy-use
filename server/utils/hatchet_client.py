"""
Minimal Hatchet client for job queue management.
"""

import logging
from typing import Optional
from hatchet_sdk import Hatchet

logger = logging.getLogger(__name__)

# Global Hatchet client instance
_hatchet_client: Optional[Hatchet] = None


def get_hatchet_client() -> Hatchet:
    """Get or create the Hatchet client instance."""
    global _hatchet_client

    if _hatchet_client is None:
        # Initialize with minimal configuration
        # Hatchet will use default settings if not configured
        _hatchet_client = Hatchet()
        logger.info('Initialized Hatchet client')

    return _hatchet_client


def enqueue_job_with_hatchet(job_id: str, tenant_schema: str, target_id: str) -> str:
    """
    Enqueue a job using Hatchet with the execute_job task.

    Args:
        job_id: The job ID
        tenant_schema: The tenant schema
        target_id: The target ID for concurrency control

    Returns:
        The Hatchet task run ID
    """
    from server.utils.hatchet_tasks import execute_job, JobExecutionInput

    # Create input for the job execution task
    task_input = JobExecutionInput(
        job_id=job_id, tenant_schema=tenant_schema, target_id=target_id
    )

    # Trigger the task
    result = execute_job.run(input=task_input)

    logger.info(
        f'Enqueued job {job_id} for tenant {tenant_schema} target {target_id} '
        f'with Hatchet task result: {result}'
    )

    return str(result)
