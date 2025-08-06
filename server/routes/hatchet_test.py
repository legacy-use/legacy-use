"""
Simple Hatchet test endpoint.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.utils.hatchet_tasks import SimpleInput, hatchet

logger = logging.getLogger(__name__)

# Create router
hatchet_test_router = APIRouter(tags=['Hatchet Testing'])


class TestRequest(BaseModel):
    message: str


class TestResponse(BaseModel):
    job_id: str
    message: str


@hatchet_test_router.post('/test/hatchet', response_model=TestResponse)
async def test_hatchet_task(request: TestRequest) -> TestResponse:
    """
    Test endpoint for Hatchet task execution.

    This endpoint enqueues a simple task that transforms the input message to lowercase.
    """
    try:
        # Create the input for the task
        task_input = SimpleInput(message=request.message)

        # Enqueue the task (non-blocking)
        logger.info(f'Enqueuing Hatchet task with message: {request.message}')

        # Use the workflow trigger instead of direct run
        # This will enqueue the task and return immediately
        workflow_run = hatchet.workflow('SimpleTask').trigger(task_input)

        logger.info(f'Hatchet task enqueued with run ID: {workflow_run.id}')

        return TestResponse(
            job_id=workflow_run.id, message='Task enqueued successfully'
        )

    except Exception as e:
        logger.error(f'Error executing Hatchet task: {e}')
        raise HTTPException(status_code=500, detail=f'Task execution failed: {str(e)}')
