"""
Simple Hatchet test endpoint.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from server.utils.hatchet_tasks import simple, SimpleInput

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

        # Run the task (this will enqueue it)
        logger.info(f'Enqueuing Hatchet task with message: {request.message}')

        # Note: This will wait for the task to be executed by a worker
        # In a real scenario, you'd want to enqueue and return immediately
        result = simple.run(task_input)

        logger.info(f'Hatchet task completed with result: {result}')

        return TestResponse(
            job_id='test-job', message=result.get('transformed_message', 'No result')
        )

    except Exception as e:
        logger.error(f'Error executing Hatchet task: {e}')
        raise HTTPException(status_code=500, detail=f'Task execution failed: {str(e)}')
