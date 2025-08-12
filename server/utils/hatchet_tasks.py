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
        # Get job from database (offload sync DB to thread)
        import asyncio as _asyncio

        def _fetch_job_sync():
            with with_db(input.tenant_schema) as db_session:
                db_service = TenantAwareDatabaseService(db_session)
                data = db_service.get_job(input.job_id)
                return data

        job_data = await _asyncio.to_thread(_fetch_job_sync)

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


class TargetOrchestratorInput(BaseModel):
    tenant_schema: str
    target_id: str


@hatchet.task(
    name='orchestrate_target',
    input_validator=TargetOrchestratorInput,
    concurrency=ConcurrencyExpression(
        # One orchestrator per tenant:target, but on a distinct key so it doesn't
        # occupy the execution slot used by execute_job
        expression="input.tenant_schema + ':' + input.target_id + ':orchestrator'",
        max_runs=1,
        limit_strategy=ConcurrencyLimitStrategy.GROUP_ROUND_ROBIN,
    ),
)
async def orchestrate_target(
    input: TargetOrchestratorInput, ctx: Context
) -> Dict[str, Any]:
    """Per-target orchestrator: pulls next runnable job (FIFO) and runs it.

    It exits when there is nothing runnable; callers can re-trigger on demand.
    """
    from server.database.multi_tenancy import with_db
    from server.utils.db_dependencies import TenantAwareDatabaseService
    from server.models.base import JobStatus
    from server.utils.hatchet_client import enqueue_job_with_hatchet

    import asyncio as _asyncio

    def _select_next_job_sync():
        with with_db(input.tenant_schema) as db_session:
            db = TenantAwareDatabaseService(db_session)
            blocking = db.is_target_queue_paused(input.target_id)
            if blocking and blocking.get('is_paused'):
                return {'blocked': True, 'job': None}
            queued_desc = db.list_jobs_by_status_and_target(
                input.target_id, [JobStatus.QUEUED.value], limit=1000, offset=0
            )
            if not queued_desc:
                return {'blocked': False, 'job': None}
            return {'blocked': False, 'job': queued_desc[-1]}

    sel = await _asyncio.to_thread(_select_next_job_sync)
    if sel['blocked']:
        return {'status': 'blocked'}
    if not sel['job']:
        return {'status': 'idle'}
    next_job = sel['job']

    # Run the head-of-line job via existing execute_job task
    # Offload task trigger to avoid blocking
    await _asyncio.to_thread(
        enqueue_job_with_hatchet,
        str(next_job['id']),
        input.tenant_schema,
        input.target_id,
    )

    return {'status': 'dispatched', 'job_id': str(next_job['id'])}
