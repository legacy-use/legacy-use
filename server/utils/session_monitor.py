"""
Session monitoring service.

This module provides functionality to monitor session states and update them based on container status.
"""

import asyncio
import logging
from datetime import datetime, timedelta

from server.database.multi_tenancy import with_db
from server.utils.docker_manager import (
    check_target_container_health,
    get_container_status,
)
from server.utils.tenant_utils import get_active_tenants

logger = logging.getLogger(__name__)

# How often to check session states (in seconds)
INIT_CHECK_INTERVAL = 5  # Check every second during initialization
READY_CHECK_INTERVAL = 60  # Check every 60 seconds once ready
INACTIVE_SESSION_THRESHOLD = 60 * 60  # 60 minutes in seconds


async def monitor_sessions_for_tenant(tenant_schema: str):
    """
    Monitor session states for a specific tenant.

    Args:
        tenant_schema: The tenant schema to monitor
    """
    try:
        with with_db(tenant_schema) as db_session:
            # Create a tenant-aware database service
            from server.utils.db_dependencies import TenantAwareDatabaseService

            db_service = TenantAwareDatabaseService(db_session)

            # Get all non-archived sessions for this tenant
            sessions = db_service.list_sessions(include_archived=False)
            current_datetime = datetime.now()

            for session in sessions:
                session_id = session.get('id')
                current_state = session.get('state', 'initializing')
                container_id = session.get('container_id')
                container_ip = session.get('container_ip')
                last_job_time = session.get('last_job_time')

                # Check for inactive sessions (no job in the last 60 minutes)
                if current_state == 'ready':
                    # Handle sessions that have never had a job run on them
                    if last_job_time is None:
                        # Use the session's created_at time as the last activity time
                        created_at = session.get('created_at')
                        if isinstance(created_at, str):
                            try:
                                last_job_time = datetime.fromisoformat(
                                    created_at.replace('Z', '+00:00')
                                )
                            except ValueError:
                                logger.warning(
                                    f'Could not parse created_at for session {session_id}'
                                )
                                last_job_time = None
                        elif isinstance(created_at, datetime):
                            last_job_time = created_at
                        else:
                            last_job_time = None
                    else:
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
                        # Check if there are any running jobs on this session
                        running_jobs = db_service.list_session_jobs(
                            session_id, status='running'
                        )

                        if running_jobs:
                            logger.info(
                                f'Session {session_id} has been inactive but has {len(running_jobs)} running job(s), skipping termination'
                            )
                            continue
                        logger.info(
                            f'Session {session_id} has been inactive for more than {INACTIVE_SESSION_THRESHOLD / 60} minutes, archiving'
                        )

                        # Archive the session with reason 'auto-cleanup'
                        db_service.update_session(
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
                                )

                                stop_container(container_id)
                            except Exception as e:
                                logger.error(
                                    f'Error stopping container for inactive session {session_id}: {str(e)}'
                                )

                        continue

                # Skip sessions without container info
                if not container_id or not container_ip:
                    continue

                # Check container status
                container_status = await get_container_status(
                    container_id, session_state=current_state
                )
                is_running = container_status.get('state', {}).get('Running', False)

                # If container is not running but session is not in a terminal state,
                # check for running jobs before destroying
                if not is_running and current_state not in ['destroying', 'destroyed']:
                    # Check if there are any running jobs on this session
                    running_jobs = db_service.list_session_jobs(
                        session_id, status='running'
                    )

                    if running_jobs:
                        logger.info(
                            f'Container for session {session_id} is not running but has {len(running_jobs)} running job(s), skipping destruction'
                        )
                        continue

                    logger.info(
                        f"Container for session {session_id} is not running, updating state to 'destroyed'"
                    )
                    db_service.update_session(
                        session_id,
                        {
                            'state': 'destroyed',
                            'is_archived': True,
                            'archive_reason': 'container-not-running',
                        },
                    )
                    continue

                # If session is initializing and container is running, check health
                if current_state == 'initializing' and is_running:
                    health_status = await check_target_container_health(container_ip)
                    if health_status['healthy']:
                        logger.info(
                            f"API for session {session_id} is ready, updating state to 'ready'"
                        )
                        db_service.update_session(session_id, {'state': 'ready'})

    except Exception as e:
        logger.error(f'Error monitoring sessions for tenant {tenant_schema}: {str(e)}')


async def monitor_session_states():
    """
    Monitor session states and update them based on container status.

    This function runs in a loop and periodically checks all active sessions across all tenants.
    For each session, it:
    1. Checks if the container is running
    2. If the session is in 'initializing' state, checks if the API is ready
    3. Updates the session state accordingly
    4. Archives sessions that have been inactive for more than INACTIVE_SESSION_THRESHOLD
    """
    logger.info('Starting session state monitor')

    while True:
        try:
            # Get all active tenants
            tenants = get_active_tenants()

            # Monitor sessions for each tenant
            for tenant in tenants:
                tenant_schema = tenant.get('schema')
                if not tenant_schema:
                    continue

                # Monitor sessions for this tenant
                await monitor_sessions_for_tenant(tenant_schema)

        except Exception as e:
            logger.error(f'Error in session state monitor: {str(e)}')

        # Wait before next iteration
        await asyncio.sleep(READY_CHECK_INTERVAL)


def start_session_monitor():
    """Start the session monitor in a background task."""
    asyncio.create_task(monitor_session_states())
