"""
Hatchet tasks for job execution with multi-tenancy and per-target queuing.
"""

import logging
from typing import Dict, Any

from hatchet_sdk import Context, ConcurrencyExpression, ConcurrencyLimitStrategy
from pydantic import BaseModel

from server.utils.hatchet_client import get_hatchet_client

logger = logging.getLogger(__name__)

# Get the shared Hatchet client instance
hatchet = get_hatchet_client()


class JobExecutionInput(BaseModel):
    """Input for job execution workflow."""

    job_id: str
    tenant_schema: str
    target_id: str


# Define the job execution as a task with per-target concurrency
@hatchet.task(
    name='execute_job',
    input_validator=JobExecutionInput,
    concurrency=ConcurrencyExpression(
        # Use tenant:target_id as the concurrency key to ensure
        # only one job runs per target per tenant
        expression="input.tenant_schema + ':' + input.target_id",
        max_runs=1,
        limit_strategy=ConcurrencyLimitStrategy.GROUP_ROUND_ROBIN,
    ),
)
async def execute_job(input: JobExecutionInput, ctx: Context) -> Dict[str, Any]:
    """Execute a job with tenant and target context."""
    from server.models.base import Job
    from server.database.multi_tenancy import with_db
    from server.utils.db_dependencies import TenantAwareDatabaseService
    from server.utils.job_execution import execute_api_in_background_with_tenant

    logger.info(
        f'Executing job {input.job_id} for tenant {input.tenant_schema} target {input.target_id}'
    )

    try:
        # Get job from database
        with with_db(input.tenant_schema) as db_session:
            db_service = TenantAwareDatabaseService(db_session)
            job_data = db_service.get_job(input.job_id)

            if not job_data:
                raise ValueError(f'Job {input.job_id} not found')

            job = Job(**job_data)

        # Execute the job using existing logic
        await execute_api_in_background_with_tenant(job, input.tenant_schema)

        logger.info(f'Successfully completed job {input.job_id}')
        return {'status': 'completed', 'job_id': input.job_id}

    except Exception as e:
        logger.error(f'Error executing job {input.job_id}: {str(e)}')
        raise
