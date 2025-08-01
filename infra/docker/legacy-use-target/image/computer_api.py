import os
from fastapi import FastAPI, HTTPException, Path as FastAPIPath
from pydantic import BaseModel
from typing import Literal, Optional, Tuple, Union

from computer import (
    Action_20250124,
    ScrollDirection,
    ComputerTool20241022,
    ComputerTool20250124,
    run,
)
from recording import router as recording_router

# Create FastAPI app
app = FastAPI(
    title='Computer Actions API',
    description='API for interacting with the computer (mouse, keyboard, screen)',
    version='1.0.0',
)

# Include recording router
app.include_router(recording_router)

# Get target type from environment variable, defaulting to "generic"
REMOTE_CLIENT_TYPE = os.getenv('REMOTE_CLIENT_TYPE', 'generic')


async def check_program_connection() -> bool:
    """Check if the appropriate program for the target type has an established connection."""

    try:
        # Check for established connections for the program
        _, stdout, _ = await run(
            f'netstat -tnp | grep {REMOTE_CLIENT_TYPE}', timeout=5.0
        )
        return 'ESTABLISHED' in stdout
    except (TimeoutError, Exception):
        return False


@app.get('/health')
async def health_check():
    """Health check endpoint."""
    # Check if the appropriate program has an established connection
    is_healthy = await check_program_connection()
    if not is_healthy:
        raise HTTPException(
            status_code=503,
            detail=f'Remote screen sharing solution is not running ({REMOTE_CLIENT_TYPE})',
        )

    return {'status': 'ok', 'target_type': REMOTE_CLIENT_TYPE}


class ToolUseRequest(BaseModel):
    text: Optional[str] = None
    coordinate: Optional[Tuple[int, int]] = None
    scroll_direction: Optional[ScrollDirection] = None
    scroll_amount: Optional[int] = None
    duration: Optional[Union[int, float]] = None
    key: Optional[str] = None
    api_type: Optional[Literal['computer_20241022', 'computer_20250124']] = (
        'computer_20250124'
    )


@app.post('/tool_use/{action}')
async def tool_use(
    action: Action_20250124 = FastAPIPath(..., description='The action to perform'),
    request: ToolUseRequest = None,
):
    """Execute a specific computer action"""
    if request is None:
        request = ToolUseRequest()

    # Instantiate the appropriate computer actions class based on api_type
    if request.api_type == 'computer_20241022':
        computer_actions = ComputerTool20241022()
    else:
        # Default to the newer version
        computer_actions = ComputerTool20250124()

    print(f'action: {action}')
    print(f'request: {request}')

    return await computer_actions(
        action=action,
        text=request.text,
        coordinate=request.coordinate,
        scroll_direction=request.scroll_direction,
        scroll_amount=request.scroll_amount,
        duration=request.duration,
        key=request.key,
    )
