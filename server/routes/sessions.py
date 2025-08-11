"""
Session management routes.
"""

import asyncio
import logging
import re
from subprocess import CalledProcessError
from typing import Any, Dict, List
from uuid import UUID

import httpx
import requests
import websockets
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.websockets import WebSocket, WebSocketDisconnect

from server.config.default_ports import DEFAULT_PORTS
from server.models.base import (
    RecordingRequest,
    RecordingResultResponse,
    RecordingStatusResponse,
    Session,
    SessionContainerLogs,
    SessionCreate,
    SessionUpdate,
)
from server.utils.db_dependencies import get_tenant_db, get_tenant_db_websocket
from server.utils.tenant_utils import get_tenant_from_request
from server.utils.docker_manager import (
    get_container_status,
    launch_container,
    stop_container,
)
from server.utils.telemetry import (
    capture_session_created,
    capture_session_deleted,
)

logger = logging.getLogger(__name__)

# Create router
session_router = APIRouter(prefix='/sessions', tags=['Session Management'])

# Create a separate router for WebSocket endpoints (no API key required)
# TODO: Move the websocket to a different prefix -> e.g. /ws/sessions/
websocket_router = APIRouter(prefix='/sessions', tags=['WebSocket Endpoints'])


@session_router.get('/', response_model=List[Session])
async def list_sessions(
    include_archived: bool = False, db_tenant=Depends(get_tenant_db)
):
    """List all active sessions."""
    sessions = db_tenant.list_sessions(include_archived)

    # Add container status to each session with a container_id
    for session in sessions:
        if container_id := session.get('container_id'):
            container_status = await get_container_status(
                container_id, state=session.get('state')
            )
            session['container_status'] = container_status

    return sessions


@session_router.post('/', response_model=Session)
async def create_session(
    session: SessionCreate,
    request: Request,
    get_or_create: bool = False,
    db_tenant=Depends(get_tenant_db),
    tenant=Depends(get_tenant_from_request),
):
    """
    Create a new session for a target.

    If get_or_create is True, will return an existing ready session for the target if one exists.
    """
    # Check if target exists
    target = db_tenant.get_target(session.target_id)
    if not target:
        raise HTTPException(status_code=404, detail='Target not found')

    # Check for existing active sessions for this target (unless get_or_create is True)
    if not get_or_create:
        active_session_info = db_tenant.has_active_session_for_target(session.target_id)
        if active_session_info['has_active_session']:
            existing_session = active_session_info['session']
            raise HTTPException(
                status_code=409,
                detail={
                    'message': 'An active session already exists for this target',
                    'existing_session': {
                        # converting to non json serializable types
                        'id': str(existing_session['id']),
                        'name': existing_session['name'],
                        'state': existing_session['state'],
                        'status': existing_session['status'],
                        'created_at': existing_session['created_at'].isoformat()
                        if existing_session['created_at']
                        else None,
                    },
                },
            )

    # If get_or_create is True, check for existing active sessions for this target
    if get_or_create:
        target_sessions = db_tenant.list_target_sessions(
            session.target_id, include_archived=False
        )

        # Filter for sessions in "ready" state
        ready_sessions = [s for s in target_sessions if s.get('state') == 'ready']

        if ready_sessions:
            # Return the first ready session
            session_data = ready_sessions[0]

            # Add container status
            if container_id := session_data.get('container_id'):
                container_status = await get_container_status(
                    container_id, state=session_data.get('state')
                )
                session_data['container_status'] = container_status

            return session_data

    # No ready session found or get_or_create is False, create a new one
    session_data = session.dict()
    session_data['state'] = 'initializing'  # Set initial state
    db_session = db_tenant.create_session(session_data)

    # Prepare container parameters
    session_target_type = target.get('type')
    # Split by the first occurrence of either '_' or '+'
    parts = re.split(r'[_+]', session_target_type, maxsplit=1)
    if len(parts) == 2:
        client_type, vpn_type = parts
    else:
        client_type = session_target_type
        vpn_type = 'direct'

    container_params = {
        'REMOTE_CLIENT_TYPE': client_type,
        'REMOTE_VPN_TYPE': vpn_type,
        'HOST_IP': target.get('host'),
        'HOST_PORT': target.get('port')
        or str(DEFAULT_PORTS.get(target.get('type'), 'unknown')),
        'VPN_CONFIG': target.get('vpn_config'),
        'VPN_USERNAME': target.get('vpn_username'),
        'VPN_PASSWORD': target.get('vpn_password'),
        'REMOTE_USERNAME': target.get('username'),
        'REMOTE_PASSWORD': target.get('password'),
        'WIDTH': str(target.get('width', 1024)),
        'HEIGHT': str(target.get('height', 768)),
        # RDP customization
        'RDP_PARAMS': target.get('rdp_params'),
    }

    # Launch Docker container for the session
    container_id, container_ip = launch_container(
        target['type'],
        str(db_session['id']),
        container_params=container_params,
        tenant_schema=tenant['schema'],
    )

    if container_id and container_ip:
        # Update session with container info
        db_tenant.update_session(
            db_session['id'],
            {
                'container_id': container_id,
                'container_ip': container_ip,
                'status': 'running',
                'state': 'initializing',  # Ensure state is set
            },
        )
        # Get updated session
        db_session = db_tenant.get_session(db_session['id'])

        # Add container status
        if container_id := db_session.get('container_id'):
            container_status = await get_container_status(
                container_id, state=db_session.get('state')
            )
            db_session['container_status'] = container_status
    else:
        # Update session status to error if container launch failed
        db_tenant.update_session(
            db_session['id'], {'status': 'error', 'state': 'initializing'}
        )

    capture_session_created(request, db_session)

    return db_session


@session_router.get('/{session_id}')
async def get_session(session_id: UUID, db_tenant=Depends(get_tenant_db)):
    """Get details of a specific session."""
    if session := db_tenant.get_session(session_id):
        # If the session has a container_id, get container status
        if container_id := session.get('container_id'):
            container_status = await get_container_status(
                container_id, state=session.get('state')
            )
            # Add container status to session data
            session['container_status'] = container_status

        return session
    raise HTTPException(status_code=404, detail='Session not found')


@session_router.put('/{session_id}')
async def update_session(
    session_id: UUID, session: SessionUpdate, db_tenant=Depends(get_tenant_db)
):
    """Update a session's configuration."""
    if not db_tenant.get_session(session_id):
        raise HTTPException(status_code=404, detail='Session not found')

    # Update session
    updated_session = db_tenant.update_session(
        session_id, session.dict(exclude_unset=True)
    )

    # Add container status if container_id exists
    if container_id := updated_session.get('container_id'):
        container_status = await get_container_status(
            container_id, state=updated_session.get('state')
        )
        updated_session['container_status'] = container_status

    return updated_session


@session_router.delete('/{session_id}')
async def delete_session(
    session_id: UUID, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Archive a session."""
    # Check if session exists
    session = db_tenant.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    # Update session state to destroying and set archive reason
    db_tenant.update_session(
        session_id,
        {
            'state': 'destroying',
            'is_archived': True,
            'archive_reason': 'user-initiated',
        },
    )

    # Stop the container if it exists
    if container_id := session.get('container_id'):
        try:
            stop_container(container_id)
        except Exception as e:
            logger.error(f'Error stopping container: {str(e)}')

    capture_session_deleted(request, session_id, False)

    # Return success message
    return {'message': 'Session archived successfully'}


@session_router.delete('/{session_id}/hard')
async def hard_delete_session(
    session_id: UUID, request: Request, db_tenant=Depends(get_tenant_db)
):
    """Permanently delete a session and stop its container (hard delete)."""
    # Get session
    session = db_tenant.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    # Stop container if it exists
    if session.get('container_id'):
        stop_container(session['container_id'])

    # Delete session from database
    db_tenant.hard_delete_session(session_id)

    capture_session_deleted(request, session_id, True)

    return {'message': 'Session permanently deleted'}


@session_router.post('/{session_id}/execute', response_model=Dict[str, Any])
async def execute_api_on_session(
    session_id: UUID,
    api_request: Dict[str, Any],
    request: Request,
    db_tenant=Depends(get_tenant_db),
):
    """
    Execute an API call on the session's container.

    This endpoint forwards API requests to the container running the session.
    """
    # Get session
    session = db_tenant.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    # Check if container is running
    if not session.get('container_id') or not session.get('container_ip'):
        raise HTTPException(status_code=400, detail='Session has no active container')

    # Forward request to container
    try:
        container_url = f'http://{session["container_ip"]}:8088/api/execute'
        response = requests.post(container_url, json=api_request, timeout=30)

        # Return response from container
        return response.json()
    except requests.RequestException as e:
        logger.error(f'Error communicating with container: {str(e)}')
        raise HTTPException(
            status_code=502, detail=f'Error communicating with container: {str(e)}'
        ) from e


@session_router.get('/{session_id}/vnc/{path:path}', include_in_schema=True)
async def proxy_vnc(
    session_id: UUID, path: str, request: Request, db_tenant=Depends(get_tenant_db)
):
    """
    Proxy VNC viewer requests to the container running the session.

    This endpoint forwards VNC viewer requests to the container's VNC server running on port 6080.
    """
    # Get session
    session = db_tenant.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    # Check if container is running
    if not session.get('container_id') or not session.get('container_ip'):
        raise HTTPException(status_code=400, detail='Session has no active container')

    # Construct the target URL
    container_ip = session.get('container_ip')
    target_url = f'http://{container_ip}:6080/{path}'

    # Get query parameters from the request
    params = dict(request.query_params)

    # Get headers from the request, excluding host
    headers = dict(request.headers)
    headers.pop('host', None)

    try:
        # Get the method from the request
        method = request.method

        # Get the request body if it exists
        body = await request.body() if method in ['POST', 'PUT', 'PATCH'] else None

        # Make the request to the container # TODO: Add auth to the request, but not critical
        client_response = requests.request(
            method=method,
            url=target_url,
            params=params,
            headers=headers,
            data=body,
            stream=True,
            timeout=60,
        )

        # Create a function to close the response when done
        def close_response():
            client_response.close()

        # Return a streaming response
        return StreamingResponse(
            content=client_response.iter_content(chunk_size=8192),
            status_code=client_response.status_code,
            headers=dict(client_response.headers),
            background=BackgroundTask(close_response),
        )
    except requests.RequestException as e:
        logger.error(f'Error proxying VNC request: {str(e)}')
        raise HTTPException(
            status_code=502, detail=f'Error proxying VNC request: {str(e)}'
        ) from e


# Move the WebSocket endpoint to the websocket_router
@websocket_router.websocket('/{session_id}/vnc/websockify')
async def proxy_vnc_websocket(
    websocket: WebSocket, session_id: UUID, db_tenant=Depends(get_tenant_db_websocket)
):
    """
    Proxy WebSocket connections for the VNC viewer.

    This endpoint forwards WebSocket connections to the container's VNC server.
    """
    logger.info(f'[VNC-WS] New WebSocket connection for session {session_id}')
    logger.info(
        '[VNC-WS] Clipboard monitor active (looking for message types 0x06/0x03 and prefix "Clipboard:")'
    )

    # Get session
    session = db_tenant.get_session(session_id)
    if not session:
        logger.warning(f'[VNC-WS] Session {session_id} not found')
        await websocket.close(code=1008, reason='Session not found')
        return

    # Check if session is in ready state
    if session.get('state') != 'ready':
        logger.warning(
            f'[VNC-WS] Session {session_id} not ready (state: {session.get("state")})'
        )
        await websocket.close(
            code=1008,
            reason=f'Session is not ready (current state: {session.get("state")})',
        )
        return

    # Construct the target WebSocket URL
    container_ip = session.get('container_ip')
    target_ws_url = f'ws://{container_ip}:6080/websockify'
    logger.info(f'[VNC-WS] Connecting to container: {target_ws_url}')

    # Accept the WebSocket connection
    await websocket.accept()

    def check_clipboard_content(data, direction_label):
        """Check if data contains clipboard filter string and log accordingly."""

        # Try to decode and check for filter string
        contains_filter = False
        try:
            text = None
            if isinstance(data, bytes):
                try:
                    text = data.decode('latin-1', errors='ignore')
                except Exception:
                    pass
            elif isinstance(data, str):
                text = data

            if text and 'Clipboard:' in text:
                contains_filter = True
                logger.info(f'[VNC-WS] 📋 Clipboard {direction_label} text="{text}"')
        except Exception:
            pass

        return contains_filter

    try:
        # Connect to the target WebSocket
        async with websockets.connect(target_ws_url) as ws_client:
            logger.info(f'[VNC-WS] Connected to container for session {session_id}')

            # Create tasks for bidirectional communication
            async def forward_to_target():
                try:
                    while True:
                        # Receive message from client
                        data = await websocket.receive_bytes()
                        check_clipboard_content(data, '⬆️')

                        # Forward message to target
                        await ws_client.send(data)
                except WebSocketDisconnect:
                    logger.info(
                        f'[VNC-WS] Client disconnected for session {session_id}'
                    )
                    return
                except websockets.exceptions.ConnectionClosed as e:
                    if e.code == 1001:
                        logger.info(
                            f'[VNC-WS] Target container going away for session {session_id} (normal shutdown)'
                        )
                    elif e.code == 1000:
                        logger.info(
                            f'[VNC-WS] Normal closure from target for session {session_id}'
                        )
                    else:
                        logger.warning(
                            f'[VNC-WS] Target connection closed with code {e.code}: {e.reason} for session {session_id}'
                        )
                    return
                except Exception as e:
                    logger.error(f'[VNC-WS] Error forwarding to target: {str(e)}')
                    return

            async def forward_to_client():
                try:
                    while True:
                        # Receive message from target
                        data = await ws_client.recv()
                        check_clipboard_content(data, '⬇️')

                        # Forward message to client
                        if isinstance(data, str):
                            await websocket.send_text(data)
                        else:
                            await websocket.send_bytes(data)
                except WebSocketDisconnect:
                    logger.info(
                        f'[VNC-WS] Client disconnected for session {session_id}'
                    )
                    return
                except websockets.exceptions.ConnectionClosed as e:
                    if e.code == 1001:
                        logger.info(
                            f'[VNC-WS] Target container going away for session {session_id} (normal shutdown)'
                        )
                    elif e.code == 1000:
                        logger.info(
                            f'[VNC-WS] Normal closure from target for session {session_id}'
                        )
                    else:
                        logger.warning(
                            f'[VNC-WS] Target connection closed with code {e.code}: {e.reason} for session {session_id}'
                        )
                    return
                except Exception as e:
                    logger.error(f'[VNC-WS] Error forwarding to client: {str(e)}')
                    return

            # Run both forwarding tasks concurrently
            forward_client_task = asyncio.create_task(forward_to_target())
            forward_target_task = asyncio.create_task(forward_to_client())

            # Wait for either task to complete (which means a connection was closed)
            done, pending = await asyncio.wait(
                [forward_client_task, forward_target_task],
                return_when=asyncio.FIRST_COMPLETED,
            )

            # Cancel the pending task
            for task in pending:
                task.cancel()

    except websockets.exceptions.ConnectionClosed:
        logger.info(f'[VNC-WS] WebSocket connection closed for session {session_id}')
    except Exception as e:
        logger.error(
            f'[VNC-WS] Error in WebSocket proxy for session {session_id}: {str(e)}'
        )
    finally:
        # Only try to close the WebSocket if it's still connected
        try:
            if websocket.client_state.CONNECTED:
                await websocket.close()
                logger.info(f'[VNC-WS] WebSocket closed for session {session_id}')
        except Exception as e:
            # Log but don't raise the error since this is cleanup code
            logger.debug(f'[VNC-WS] Error closing WebSocket in cleanup: {str(e)}')


# Add a new endpoint to update session state
@session_router.put('/{session_id}/state')
async def update_session_state(
    session_id: UUID, state: str, db_tenant=Depends(get_tenant_db)
):
    """Update the state of a session."""
    # Check if session exists
    session = db_tenant.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    # Validate state
    valid_states = [
        'initializing',
        'authenticating',
        'ready',
        'destroying',
        'destroyed',
    ]
    if state not in valid_states:
        raise HTTPException(
            status_code=400,
            detail=f'Invalid state. Must be one of: {", ".join(valid_states)}',
        )

    # Update session state
    db_tenant.update_session(session_id, {'state': state})

    # If state is "destroying", also mark the session as archived
    if state == 'destroying':
        db_tenant.update_session(session_id, {'is_archived': True})

    # Return updated session
    return db_tenant.get_session(session_id)


# Recording Control Endpoints
@session_router.post(
    '/{session_id}/recording/start',
    response_model=RecordingStatusResponse,
)
async def start_session_recording(
    session_id: UUID,
    request: RecordingRequest = RecordingRequest(),
    db_tenant=Depends(get_tenant_db),
) -> RecordingStatusResponse:
    """Start screen recording on a session"""
    session = db_tenant.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    if not session.get('container_ip'):
        raise HTTPException(status_code=400, detail='Session container not running')

    try:
        async with httpx.AsyncClient() as client:
            target_url = f'http://{session["container_ip"]}:8088/recording/start'
            request_data = request.model_dump()
            response = await client.post(target_url, json=request_data, timeout=30.0)

            if response.status_code == 200:
                return RecordingStatusResponse(**response.json())
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f'Recording start failed: {response.text}',
                )

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503, detail=f'Failed to connect to session container: {str(e)}'
        )


@session_router.post(
    '/{session_id}/recording/stop',
    response_model=RecordingResultResponse,
)
async def stop_session_recording(
    session_id: UUID, db_tenant=Depends(get_tenant_db)
) -> RecordingResultResponse:
    """Stop screen recording on a session and get the video"""
    session = db_tenant.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    if not session.get('container_ip'):
        raise HTTPException(status_code=400, detail='Session container not running')

    try:
        async with httpx.AsyncClient() as client:
            target_url = f'http://{session["container_ip"]}:8088/recording/stop'
            response = await client.post(
                target_url, timeout=60.0
            )  # Longer timeout for video processing

            if response.status_code == 200:
                return RecordingResultResponse(**response.json())
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f'Recording stop failed: {response.text}',
                )

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503, detail=f'Failed to connect to session container: {str(e)}'
        )


@session_router.get(
    '/{session_id}/recording/status',
    response_model=RecordingStatusResponse,
)
async def get_session_recording_status(
    session_id: UUID, db_tenant=Depends(get_tenant_db)
) -> RecordingStatusResponse:
    """Get recording status from a session"""
    session = db_tenant.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    if not session.get('container_ip'):
        raise HTTPException(status_code=400, detail='Session container not running')

    try:
        async with httpx.AsyncClient() as client:
            target_url = f'http://{session["container_ip"]}:8088/recording/status'
            response = await client.get(target_url, timeout=10.0)

            if response.status_code == 200:
                return RecordingStatusResponse(**response.json())
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f'Recording status failed: {response.text}',
                )

    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503, detail=f'Failed to connect to session container: {str(e)}'
        )


@session_router.get('/{session_id}/container_logs', response_model=SessionContainerLogs)
async def get_session_container_logs(
    session_id: UUID, lines: int = 1000, db_tenant=Depends(get_tenant_db)
) -> SessionContainerLogs:
    """Get Docker logs for a session's container."""
    session = db_tenant.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail='Session not found')

    if not session.get('container_id'):
        raise HTTPException(status_code=400, detail='Session has no container')

    try:
        import subprocess

        # Get Docker logs using subprocess
        result = subprocess.run(
            ['docker', 'logs', '--tail', str(lines), session['container_id']],
            capture_output=True,
            text=True,
            check=True,
        )

        logs = result.stdout
        if not logs:
            logs = 'No logs available for this container.'

        return SessionContainerLogs(
            session_id=str(session_id),
            container_id=session['container_id'],
            logs=logs,
            lines_retrieved=len(logs.splitlines()),
            max_lines_requested=lines,
        )
    except CalledProcessError as e:
        logger.error(f'Error getting Docker logs for session {session_id}: {e.stderr}')
        raise HTTPException(
            status_code=500, detail=f'Failed to retrieve Docker logs: {e.stderr}'
        )
    except Exception as e:
        # Handle CalledProcessError and other exceptions uniformly
        try:
            stderr = e.stderr  # type: ignore[attr-defined]
        except Exception:
            stderr = str(e)
        logger.error(f'Error getting Docker logs for session {session_id}: {stderr}')
        raise HTTPException(
            status_code=500, detail=f'Failed to retrieve Docker logs: {stderr}'
        )
