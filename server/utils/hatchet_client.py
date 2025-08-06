"""
Hatchet client wrapper for job management.

This module provides a wrapper around the Hatchet SDK to manage job execution
while maintaining compatibility with the existing job system.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

from hatchet_sdk import Hatchet, Context
from pydantic import BaseModel

from server.models.base import Job, JobStatus
from server.utils.db_dependencies import TenantAwareDatabaseService

logger = logging.getLogger(__name__)

# Global Hatchet client instance
_hatchet_client: Optional[Hatchet] = None
_hatchet_job_manager: Optional['HatchetJobManager'] = None


def get_hatchet_client() -> Hatchet:
    """Get or create the global Hatchet client instance."""
    global _hatchet_client

    if _hatchet_client is None:
        # Initialize Hatchet client with environment variables
        _hatchet_client = Hatchet()
        logger.info('Initialized Hatchet client')

    return _hatchet_client


class JobExecutionInput(BaseModel):
    """Input model for job execution workflow."""

    job_id: str
    tenant_schema: str


class HatchetJobManager:
    """Manager class for Hatchet job operations."""

    _workflow: Optional[Any] = None

    def __init__(self):
        self._hatchet: Optional[Hatchet] = None

    @property
    def hatchet(self) -> Hatchet:
        if not self._hatchet:
            self._hatchet = get_hatchet_client()
        return self._hatchet

    @property
    def workflow(self):
        if self._workflow is None:
            self._setup_workflow()
        return self._workflow

    def _setup_workflow(self):
        """Set up the job execution workflow."""
        # Create the workflow for job execution
        self._workflow = self.hatchet.workflow(
            name='job-execution', input_validator=JobExecutionInput
        )

        @self._workflow.task(timeout='30m')  # 30 minute timeout
        async def execute_job(input: JobExecutionInput, ctx: Context) -> Dict[str, Any]:
            """Execute a job using the existing job execution logic."""
            from server.core import APIGatewayCore
            from server.database.multi_tenancy import with_db
            from server.models.base import Job
            from server.utils.db_dependencies import TenantAwareDatabaseService

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

                # This logic is adapted from the original execute_api_in_background_with_tenant
                core = APIGatewayCore(tenant_schema=tenant_schema, db_tenant=db_service)
                api_response = await core.execute_api(
                    job_id=str(job.id),
                    session_id=str(job.session_id),
                )

                with with_db(tenant_schema) as db_session:
                    db_service = TenantAwareDatabaseService(db_session)
                    db_service.update_job(
                        job.id,
                        {
                            'status': api_response.status,
                            'result': api_response.extraction,
                            'completed_at': datetime.now(),
                            'updated_at': datetime.now(),
                        },
                    )

                logger.info(
                    f'Hatchet completed job {job_id} for tenant {tenant_schema}'
                )
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

    async def enqueue_job(self, job: Job, tenant_schema: str) -> str:
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
            input_data = JobExecutionInput(
                job_id=str(job.id), tenant_schema=tenant_schema
            )

            # Run the workflow
            workflow_run = await self.workflow.aio_run(input_data)

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

    def get_workflow(self):
        """Get the job execution workflow for worker registration."""
        return self.workflow


def get_hatchet_job_manager() -> HatchetJobManager:
    """Get the singleton HatchetJobManager instance."""
    global _hatchet_job_manager
    if _hatchet_job_manager is None:
        _hatchet_job_manager = HatchetJobManager()
    return _hatchet_job_manager


# Global instance (lazy loaded)
hatchet_job_manager = get_hatchet_job_manager()
