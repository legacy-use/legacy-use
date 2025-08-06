"""
Minimal Hatchet client for job queue management.
"""

import logging
from typing import Optional, Dict, Any
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


def enqueue_job_with_hatchet(
    job_id: str, tenant_schema: str, job_data: Dict[str, Any]
) -> str:
    """
    Enqueue a job using Hatchet.

    Args:
        job_id: The job ID
        tenant_schema: The tenant schema
        job_data: Job data to enqueue

    Returns:
        The Hatchet job ID
    """
    client = get_hatchet_client()

    # Create a simple job with the job data
    job = client.job(
        name=f'legacy-use-job-{job_id}',
        data={'job_id': job_id, 'tenant_schema': tenant_schema, **job_data},
    )

    # Enqueue the job
    result = job.enqueue()
    logger.info(f'Enqueued job {job_id} with Hatchet job ID: {result.id}')

    return result.id
