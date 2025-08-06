"""
Session monitoring service.

This module provides functionality to monitor session states and update them based on container status.
"""

import asyncio
import logging
import time
from datetime import datetime, timedelta

from server.database import db
from server.utils.docker_manager import (
    check_target_container_health,
    get_container_status,
)

logger = logging.getLogger(__name__)

# How often to check session states (in seconds)
INIT_CHECK_INTERVAL = 5  # Check every second during initialization
READY_CHECK_INTERVAL = 60  # Check every 60 seconds once ready
INACTIVE_SESSION_THRESHOLD = 60 * 60  # 60 minutes in seconds


async def monitor_session_states():
    """
    Monitor session states and update them based on container status.

    This function runs in a loop and periodically checks all active sessions.
    For each session, it:
    1. Checks if the container is running
    2. If the session is in 'initializing' state, checks if the API is ready
    3. Updates the session state accordingly
    4. Archives sessions that have been inactive for more than INACTIVE_SESSION_THRESHOLD

    The monitoring frequency is adaptive:
    - Sessions in 'initializing' state are checked every INIT_CHECK_INTERVAL seconds
    - Sessions in 'ready' state are checked every READY_CHECK_INTERVAL seconds
    """
    logger.info('Starting session state monitor')

    # Dictionary to track when each session was last checked
    last_checked = {}

    while True:
        try:
            # Get all non-archived sessions
            sessions = db.list_sessions(include_archived=False)
            current_time = time.time()
            current_datetime = datetime.now()

            for session in sessions:
                session_id = session.get('id')
                current_state = session.get('state', 'initializing')
                container_id = session.get('container_id')
                container_ip = session.get('container_ip')
                last_job_time = session.get('last_job_time')

                # Check for inactive sessions (no job in the last 60 minutes)
                if current_state == 'ready' and last_job_time:
                    # Convert last_job_time to datetime if it's a string
                    if isinstance(last_job_time, str):
                        try:
                            last_job_time = datetime.fromisoformat(
                                last_job_time.replace('Z', '+00:00')
                            )
                        except ValueError:
                            # If we can't parse the datetime, skip this check
                            logger.warning(
                                f'Could not parse last_job_time for session {session_id}'
                            )
                            last_job_time = None

                    # Check if the session has been inactive for too long
                    if last_job_time and (current_datetime - last_job_time) > timedelta(
                        seconds=INACTIVE_SESSION_THRESHOLD
                    ):
                        logger.info(
                            f'Session {session_id} has been inactive for more than {INACTIVE_SESSION_THRESHOLD / 60} minutes, archiving'
                        )

                        # Archive the session with reason 'auto-cleanup'
                        db.update_session(
                            session_id,
                            {
                                'is_archived': True,
                                'archive_reason': 'auto-cleanup',
                                'state': 'destroying',
                            },
                        )

                        # Stop the container if it exists
                        if container_id:
                            try:
                                from server.utils.docker_manager import (
                                    stop_container,
                                    stop_vpn_container,
                                )

                                stop_container(container_id)

                                # Stop VPN container if it exists
                                if session.get('vpn_container_id'):
                                    stop_vpn_container(
                                        session['vpn_container_id'], str(session_id)
                                    )

                            except Exception as e:
                                logger.error(
                                    f'Error stopping container for inactive session {session_id}: {str(e)}'
                                )

                        # Clean up tracking and continue to next session
                        if session_id in last_checked:
                            del last_checked[session_id]
                        continue

                # Skip sessions without container info
                if not container_id or not container_ip:
                    continue

                # Determine check interval based on session state
                check_interval = (
                    INIT_CHECK_INTERVAL
                    if current_state == 'initializing'
                    else READY_CHECK_INTERVAL
                )

                # Skip if not due for checking yet
                if (
                    session_id in last_checked
                    and current_time - last_checked[session_id] < check_interval
                ):
                    continue

                # Update last checked time
                last_checked[session_id] = current_time

                # Check container status
                container_status = await get_container_status(
                    container_id, state=current_state
                )
                is_running = container_status.get('state', {}).get('Running', False)

                # If container is not running but session is not in a terminal state,
                # update to 'destroyed'
                if not is_running and current_state not in ['destroying', 'destroyed']:
                    logger.info(
                        f"Container for session {session_id} is not running, updating state to 'destroyed'"
                    )
                    db.update_session(
                        session_id, {'state': 'destroyed', 'is_archived': True}
                    )
                    # Clean up tracking and continue to next session
                    if session_id in last_checked:
                        del last_checked[session_id]
                    continue

                # If session is initializing and container is running, check health
                if current_state == 'initializing' and is_running:
                    health_status = await check_target_container_health(container_ip)
                    if health_status['healthy']:
                        logger.info(
                            f"API for session {session_id} is ready, updating state to 'ready'"
                        )
                        db.update_session(session_id, {'state': 'ready'})

            # Clean up last_checked for sessions that no longer exist
            session_ids = {session.get('id') for session in sessions}
            for session_id in list(last_checked.keys()):
                if session_id not in session_ids:
                    del last_checked[session_id]

        except Exception as e:
            logger.error(f'Error in session state monitor: {str(e)}')

        # Wait a short time before next iteration
        # This is the minimum wait time - individual sessions may be checked less frequently
        await asyncio.sleep(INIT_CHECK_INTERVAL)


def start_session_monitor():
    """Start the session monitor in a background task."""
    asyncio.create_task(monitor_session_states())
