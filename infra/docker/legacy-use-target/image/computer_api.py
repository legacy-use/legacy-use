import logging
import os
import sys
from typing import Literal, Optional, Tuple, Union, get_args

from computer import (
    Action_20241022,
    Action_20250124,
    Action_20251124,
    ComputerTool20241022,
    ComputerTool20250124,
    ComputerTool20251124,
    ScrollDirection,
    ToolError,
    run,
)
from fastapi import FastAPI, HTTPException
from fastapi import Path as FastAPIPath
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from recording import router as recording_router

# Force logging to stdout, so easily visible in docker logs
logging.basicConfig(
    level=logging.INFO, handlers=[logging.StreamHandler(sys.stdout)], force=True
)

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


async def check_program_connection() -> bool:
    """Check if the appropriate program for the target type has an established connection and desktop is ready."""

    try:
        print(f'Checking for established connections for {REMOTE_CLIENT_TYPE}')

        # Check for established connections for the program
        _, stdout, _ = await run(
            f'netstat -tnp | grep {REMOTE_CLIENT_TYPE}', timeout=5.0
        )
        if 'ESTABLISHED' not in stdout:
            print(f'No established connections for {REMOTE_CLIENT_TYPE}')
            return False

        # Client-specific checks
        if REMOTE_CLIENT_TYPE == 'rdp':
            return await check_rdp_ready()
        elif REMOTE_CLIENT_TYPE == 'vnc':
            return await check_vnc_ready()
        else:
            raise ValueError(f'Invalid remote client type: {REMOTE_CLIENT_TYPE}')

    except TimeoutError:
        print(f'Error checking for established connections for {REMOTE_CLIENT_TYPE}')
        return False


async def check_vnc_ready() -> bool:
    """Check if VNC connection is fully ready including client availability, processes, windows, and display."""
    try:
        # Check for VNC client
        result = await run('which xtigervncviewer', timeout=2.0)
        if not (result[0] == 0 and result[1].strip()):
            print('VNC client xtigervncviewer not found')
            return False

        return True
    except TimeoutError as exc:
        print(f'VNC readiness check timed out: {exc}')
        return False
    except OSError as exc:
        print(f'VNC readiness check failed: {exc}')
        return False


async def check_rdp_ready() -> bool:
    """Check if RDP connection is fully ready including client availability, processes, windows, and display."""
    try:
        # Check if xfreerdp3 client is available
        _, stdout, _ = await run('xfreerdp3 --version', timeout=5.0)
        if not ('freerdp' in stdout.lower() or 'version' in stdout.lower()):
            print(f'xfreerdp3 returned unexpected output: {stdout}')
            return False

        # Check if xfreerdp3 processes are running
        _, stdout, _ = await run('pgrep -f xfreerdp3', timeout=2.0)
        if not stdout.strip():
            print('No xfreerdp3 process found')
            return False

        # Check for active RDP windows
        _, stdout, _ = await run(
            'timeout 3 xdotool search --name "FreeRDP" 2>/dev/null || echo "no-windows"',
            timeout=3.0,
        )
        if 'no-windows' in stdout:
            print('No RDP windows found')
            return False

        return True

    except TimeoutError as exc:
        print(f'RDP readiness check timed out: {exc}')
        return False
    except OSError as exc:
        print(f'RDP readiness check failed: {exc}')
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
    api_type: Optional[
        Literal['computer_20241022', 'computer_20250124', 'computer_20251124']
    ] = 'computer_20250124'


@app.post('/tool_use/{action}')
async def tool_use(
    action: Action_20251124 = FastAPIPath(..., description='The action to perform'),
    request: Optional[ToolUseRequest] = None,
):
    """Execute a specific computer action"""
    if request is None:
        request = ToolUseRequest()

    logger.info(
        f'Received tool_use request: action={action}, api_type={request.api_type}, '
        f'text={request.text}, coordinate={request.coordinate}, '
        f'scroll_direction={request.scroll_direction}, scroll_amount={request.scroll_amount}, '
        f'duration={request.duration}, key={request.key}'
    )

    # Validate action is supported by the selected api_type
    if request.api_type == 'computer_20241022':
        valid_actions = get_args(Action_20241022)
        computer_actions = ComputerTool20241022()
        params = {
            'action': action,
            'text': request.text,
            'coordinate': request.coordinate,
        }
    elif request.api_type == 'computer_20251124':
        valid_actions = [v for t in get_args(Action_20251124) for v in get_args(t)]
        computer_actions = ComputerTool20251124()
        params = {
            'action': action,
            'text': request.text,
            'coordinate': request.coordinate,
            'scroll_direction': request.scroll_direction,
            'scroll_amount': request.scroll_amount,
            'duration': request.duration,
            'key': request.key,
        }
    else:
        valid_actions = [v for t in get_args(Action_20250124) for v in get_args(t)]
        computer_actions = ComputerTool20250124()
        params = {
            'action': action,
            'text': request.text,
            'coordinate': request.coordinate,
            'scroll_direction': request.scroll_direction,
            'scroll_amount': request.scroll_amount,
            'duration': request.duration,
            'key': request.key,
        }

    if action not in valid_actions:
        logger.warning(f"Action '{action}' is not supported by {request.api_type}")
        return JSONResponse(
            status_code=400,
            content={
                'output': None,
                'error': f"Action '{action}' is not supported by {request.api_type}",
                'base64_image': None,
            },
        )

    try:
        logger.info(
            f'Dispatching to {type(computer_actions).__name__} for action={action}'
        )
        result = await computer_actions(**params)

        logger.info(f"tool_use action '{action}' completed successfully")
        return result
    except ToolError as exc:
        logger.error(f'ToolError during tool_use: {exc}')
        return JSONResponse(
            status_code=400,
            content={'output': None, 'error': exc.message, 'base64_image': None},
        )
    except Exception as exc:
        logger.exception(f'Unhandled exception during tool_use: {exc}')
        return JSONResponse(
            status_code=500,
            content={'output': None, 'error': str(exc), 'base64_image': None},
        )
