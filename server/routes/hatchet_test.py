"""
Simple Hatchet test endpoint.
"""

import logging
from fastapi import APIRouter
from pydantic import BaseModel

from server.utils.hatchet_tasks import SimpleInput, simple

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
    # Create the input for the task
    task_input = SimpleInput(message=request.message)

    # Enqueue the task (non-blocking)
    logger.info(f'Enqueuing Hatchet task with message: {request.message}')

    # Use the workflow trigger instead of direct run
    # This will enqueue the task and return immediately

    result = simple.run(
        input=task_input,
    )

    logger.info(f'taks result {result}')

    return TestResponse(job_id='123', message='Task enqueued successfully')

    # except Exception as e:
    #    logger.error(f'Error executing Hatchet task: {e}')
    #    raise HTTPException(status_code=500, detail=f'Task execution failed: {str(e)}')
