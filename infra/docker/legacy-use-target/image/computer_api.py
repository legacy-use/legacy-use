import os
from fastapi import FastAPI, HTTPException, Path as FastAPIPath
from pydantic import BaseModel, Field
from typing import Literal, Optional, Tuple, Union, get_args, Annotated

from computer import (
    Action_20241022,
    Action_20250124,
    ScrollDirection,
    ComputerTool20241022,
    ComputerTool20250124,
    ToolError,
    ToolResult,
    run,
)
from recording import router as recording_router

import logging

logger = logging.getLogger('computer_api')

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

# API type registry for validation and tool instantiation
API_TYPE_REGISTRY = {
    'computer_20241022': (get_args(Action_20241022), ComputerTool20241022),
    'computer_20250124': (get_args(Action_20250124), ComputerTool20250124),
}


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


class ToolUseRequest20241022(BaseModel):
    """Request model for computer_20241022 API type."""
    api_type: Literal['computer_20241022'] = 'computer_20241022'
    text: Optional[str] = None
    coordinate: Optional[Tuple[int, int]] = None

    class Config:
        extra = 'forbid'


class ToolUseRequest20250124(BaseModel):
    """Request model for computer_20250124 API type."""
    api_type: Literal['computer_20250124'] = 'computer_20250124'
    text: Optional[str] = None
    coordinate: Optional[Tuple[int, int]] = None
    scroll_direction: Optional[ScrollDirection] = None
    scroll_amount: Optional[int] = None
    duration: Optional[Union[int, float]] = None
    key: Optional[str] = None

    class Config:
        extra = 'forbid'


# Discriminated union for request body
ToolUseBody = Annotated[
    Union[ToolUseRequest20241022, ToolUseRequest20250124], 
    Field(discriminator='api_type')
]


@app.post('/tool_use/{action}', response_model=ToolResult, response_model_exclude_none=True)
async def tool_use(
    action: Action_20250124 = FastAPIPath(..., description='The action to perform'),
    request: Optional[ToolUseBody] = None,
):
    """Execute a specific computer action"""
    if request is None:
        # Default to computer_20250124 when no body is provided
        request = ToolUseRequest20250124()

    logger.info(
        f'Received tool_use request: action={action}, api_type={request.api_type}, '
        f'text={request.text}, coordinate={request.coordinate}, '
        f'scroll_direction={request.scroll_direction}, scroll_amount={request.scroll_amount}, '
        f'duration={request.duration}, key={request.key}'
    )

    # Get valid actions and tool class from registry
    valid_actions, tool_class = API_TYPE_REGISTRY[request.api_type]
    
    # Validate action is supported by the selected api_type
    if action not in valid_actions:
        logger.warning(f"Action '{action}' is not supported by {request.api_type}")
        return ToolResult(
            output=None,
            error=f"Action '{action}' is not supported by {request.api_type}",
            base64_image=None,
        )

    try:
        # Build parameters generically from the validated model
        params = request.model_dump(exclude={'api_type'}, exclude_none=True)
        params['action'] = action
        
        logger.info(
            f'Dispatching to {tool_class.__name__} for action={action}'
        )
        computer_actions = tool_class()
        result = await computer_actions(**params)

        logger.info(f"tool_use action '{action}' completed successfully")
        return result
    except ToolError as exc:
        logger.error(f'ToolError during tool_use: {exc}')
        return ToolResult(
            output=None,
            error=exc.message,
            base64_image=None,
        )
    except Exception as exc:
        logger.exception(f'Unhandled exception during tool_use: {exc}')
        return ToolResult(
            output=None,
            error=str(exc),
            base64_image=None,
        )
