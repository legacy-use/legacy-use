import asyncio
import logging
from typing import Any, Dict, Optional, Set  # Added Optional and Dict for type hints
from uuid import UUID

# Imports copied from job_execution.py for these functions
from server.models.base import SessionCreate

# Remove the direct import that causes circular dependency
# from server.routes.sessions import (
#     create_session,
# )  # This might cause issues if routes imports utils

# Initialize logger and db (copied from job_execution.py - potential issue)
logger = logging.getLogger(__name__)

# Global state copied from job_execution.py (potential issue)
targets_with_pending_sessions: Set[str] = set()
targets_with_pending_sessions_lock = asyncio.Lock()


async def launch_session_for_target(target_id: str) -> Optional[Dict[str, Any]]:
    """Launch a new session for the given target."""
    try:
        logger.info(f'Launching session for target {target_id}')
        # Log the session launch - we don't have a job ID so we'll just log to the system logger
        logger.info(f'Launching new session for target {target_id}')

        # Create session object with required name field
        # Convert target_id to string before slicing
        target_id_str = str(target_id)
        session_name = f'Auto-created session for target {target_id_str[:8]}'
        session_create = SessionCreate(
            target_id=UUID(target_id), name=session_name
        )  # Ensure target_id is UUID

        # Launch session - use deferred import to avoid circular dependency
        from server.routes.sessions import create_session

        # create_session returns a Session object (Pydantic model), not a dict directly usually.
        # Assuming it returns something dict-like or has a .dict() method
        # Let's assume it returns a dict for now as used later.
        session_info: Optional[Dict[str, Any]] = await create_session(
            session_create, request=None
        )  # TODO: this is a bit hacky, we should not need to pass a request here -> wrapper around create_session endpoint and use child function instead?

        if session_info:
            # Log with prominent session ID
            session_id = session_info.get('id')
            logger.info(
                f'SUCCESS: Launched new session {session_id} for target {target_id}'
            )
            return session_info
        else:
            logger.error(
                f'Failed to launch session for target {target_id} - create_session returned None'
            )
            return None

    except Exception as e:
        logger.error(
            f'Error launching session for target {target_id}: {str(e)}', exc_info=True
        )
        # Don't raise here, let the finally block run, return None
        return None  # Indicate failure
    finally:
        # Remove target from pending sessions set only if it was added
        # Note: The original code adds it *before* calling this function.
        # This function might need the lock/set passed in if we refactor later.
        async with targets_with_pending_sessions_lock:
            if target_id in targets_with_pending_sessions:
                targets_with_pending_sessions.remove(target_id)
                logger.info(
                    f'Removed target {target_id} from pending sessions (in launch_session_for_target finally block)'
                )
