"""
Hatchet client wrapper for job management.

This module provides a wrapper around the Hatchet SDK to manage job execution
while maintaining compatibility with the existing job system.
"""

import logging
from typing import Any, Dict

from hatchet_sdk import Hatchet, Context
from pydantic import BaseModel

from server.models.base import Job, JobStatus
from server.utils.db_dependencies import TenantAwareDatabaseService

logger = logging.getLogger(__name__)

# Initialize Hatchet client
hatchet = Hatchet()


class JobInput(BaseModel):
    """Input model for job execution workflow."""

    job_id: str
    tenant_schema: str


# Define the workflow
workflow = hatchet.workflow(name='job-execution', input_validator=JobInput)


@workflow.task()
async def execute_job(input: JobInput, ctx: Context) -> Dict[str, Any]:
    """Execute a job using the refactored job execution logic."""
    from server.database.multi_tenancy import with_db
    from server.models.base import Job
    from server.utils.job_execution import execute_api_in_background_with_tenant

    job_id = input.job_id
    tenant_schema = input.tenant_schema

    logger.info(f'Hatchet executing job {job_id} for tenant {tenant_schema}')

    try:
        # Get the job from the database
        with with_db(tenant_schema) as db_session:
            db_service = TenantAwareDatabaseService(db_session)
            job_data = db_service.get_job(job_id)

            if not job_data:
                raise ValueError(f'Job {job_id} not found')

            # Create Job object
            job = Job(**job_data)

        # Use the refactored job execution logic
        await execute_api_in_background_with_tenant(job, tenant_schema)

        logger.info(f'Hatchet completed job {job_id} for tenant {tenant_schema}')
        return {'status': 'completed', 'job_id': job_id}

    except Exception as e:
        logger.error(f'Hatchet job {job_id} failed: {str(e)}')
        # Update job status to ERROR in database
        try:
            with with_db(tenant_schema) as db_session:
                db_service = TenantAwareDatabaseService(db_session)
                db_service.update_job_status(job_id, JobStatus.ERROR.value)
        except Exception as db_error:
            logger.error(f'Failed to update job status: {db_error}')
        raise


async def enqueue_job(job: Job, tenant_schema: str) -> str:
    """
    Enqueue a job for execution via Hatchet.

    Args:
        job: The Job object to execute
        tenant_schema: The tenant schema for the job

    Returns:
        The Hatchet workflow run ID
    """
    try:
        # Update job status to QUEUED in database first
        from server.database.multi_tenancy import with_db

        with with_db(tenant_schema) as db_session:
            db_service = TenantAwareDatabaseService(db_session)
            db_service.update_job_status(str(job.id), JobStatus.QUEUED.value)
            logger.info(
                f'Job {job.id} status updated to QUEUED for tenant {tenant_schema}'
            )

        # Enqueue the job in Hatchet
        input_data = JobInput(job_id=str(job.id), tenant_schema=tenant_schema)

        # Run the workflow
        workflow_run = await workflow.aio_run(input_data)

        logger.info(
            f'Job {job.id} enqueued in Hatchet with run ID: {workflow_run.workflow_run_id}'
        )
        return workflow_run.workflow_run_id

    except Exception as e:
        logger.error(f'Failed to enqueue job {job.id} in Hatchet: {str(e)}')
        # Revert job status if enqueuing failed
        try:
            with with_db(tenant_schema) as db_session:
                db_service = TenantAwareDatabaseService(db_session)
                db_service.update_job_status(str(job.id), JobStatus.PENDING.value)
        except Exception as db_error:
            logger.error(f'Failed to revert job status: {db_error}')
        raise


def get_workflow():
    """Get the job execution workflow for worker registration."""
    return workflow
