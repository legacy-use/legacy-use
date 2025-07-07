import logging
from contextvars import ContextVar
from typing import Any, Dict
from uuid import UUID

from fastapi import Request
from posthog import Posthog

from server.config import config
from server.models.base import (
    Job,
    JobStatus,
    SessionCreate,
    TargetCreate,
    TargetUpdate,
)

logger = logging.getLogger(__name__)

# Context variable to track distinct ID across async calls
distinct_id_context: ContextVar[str] = ContextVar('distinct_id', default='external')

posthog = Posthog(
    config.VITE_PUBLIC_POSTHOG_KEY or 'phc_i1lWRELFSWLrbwV8M8sddiFD83rVhWzyZhP27T3s6V8',
    host=config.VITE_PUBLIC_POSTHOG_HOST,
)


def capture_event(request: Request | None, event_name, properties):
    """
    Capture an event in Posthog.

    Args:
        distinct_id: The distinct ID of the user
        event_name: The name of the event
        properties: The properties of the event
    """
    if config.VITE_PUBLIC_DISABLE_TRACKING:
        return

    try:
        distinct_id = get_distinct_id(request)

        posthog.capture(
            distinct_id,
            event_name,
            {
                **properties,
                '$process_person_profile': 'always',
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event '{event_name}' failed: {e}")


def get_distinct_id(request: Request | None):
    """
    Get the distinct ID from the request headers.
    """
    if request is not None:
        return request.headers.get('X-Distinct-ID', 'external')
    else:
        return distinct_id_context.get()


async def posthog_middleware(request: Request, call_next):
    """
    HTTP middleware to capture API request events in PostHog.

    Args:
        request: The incoming request
        call_next: The next middleware/route handler in the chain
    """
    try:
        # Set distinct ID in context for downstream usage
        distinct_id = get_distinct_id(request)
        distinct_id_context.set(distinct_id)
    except Exception as e:
        logger.debug(f'Telemetry middleware failed: {e}')

    response = await call_next(request)

    # capture_event(
    #     distinct_id,
    #     'api_request_backend',
    #     {
    #         'url': request.url.path,
    #         'method': request.method,
    #     },
    # )
    return response


# Targets
def capture_target_created(request: Request, target_id: UUID, target: TargetCreate):
    """
    Capture a target create event in Posthog.
    """
    try:
        capture_event(
            request,
            'target_created',
            {
                'target_id': target_id,
                'name': target.name,  # TODO: relevant information or unneeded invasion of privacy?
                'width': target.width,
                'height': target.height,
                'type': str(target.type).replace('TargetType.', ''),
                'username': target.username
                != '',  # only capture if username is not empty
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'target_created' failed: {e}")


def capture_target_updated(request: Request, target_id: UUID, target: TargetUpdate):
    try:
        capture_event(
            request,
            'target_updated',
            {
                'target_id': target_id,
                'name': target.name,
                'width': target.width,
                'height': target.height,
                'type': str(target.type).replace(
                    'TargetType.', ''
                ),  # AFAIK this can't be changed after creation
                'username': target.username
                != '',  # only capture if username is not empty
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'target_updated' failed: {e}")


def capture_target_deleted(request: Request, target_id: UUID, hard_delete: bool):
    try:
        capture_event(
            request,
            'target_deleted',
            {
                'target_id': target_id,
                'hard_delete': hard_delete,
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'target_deleted' failed: {e}")


# APIs
def capture_api_created(
    request: Request, api_def: Dict[str, Any], api_id: UUID, version_number: str
):
    # This only captures the "import" event, meaning the only information added is the name of the API
    # Any additional information is added through the update event
    try:
        capture_event(
            request,
            'api_created',
            {
                'api_id': api_id,
                'name': api_def.get('name', ''),
                'version_number': version_number,
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'api_created' failed: {e}")


def capture_api_updated(
    request: Request, api_def: Dict[str, Any], api_id: UUID, version_number: str
):
    try:
        is_not_empty_description = (
            api_def.get('description', '') != ''
            and api_def.get('description', '') != 'New API'
        )

        capture_event(
            request,
            'api_updated',
            {
                'api_id': api_id,
                'name': api_def.get('name', ''),
                'version_number': version_number,
                'description_length': len(api_def.get('description', ''))
                if is_not_empty_description
                else 0,
                'parameters_count': len(api_def.get('parameters', {})),
                'prompt_length': len(api_def.get('prompt', '')),
                'prompt_cleanup_length': len(api_def.get('prompt_cleanup', '')),
                'response_example_count': len(api_def.get('response_example', {})),
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'api_updated' failed: {e}")


def capture_api_deleted(request: Request, api_id: UUID, api_name: str):
    try:
        capture_event(
            request,
            'api_deleted',
            {
                'api_id': api_id,
                'name': api_name,
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'api_deleted' failed: {e}")


# Sessions
def capture_session_created(request: Request | None, session: SessionCreate):
    try:
        capture_event(
            request,
            'session_created',
            {
                'session_id': session.get('id', ''),
                'target_id': session.get('target_id', ''),
                'name': session.get('name', ''),
                'description': session.get('description', ''),
                'status': session.get('status', ''),
                'container_id': session.get('container_id', ''),
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'session_created' failed: {e}")


def capture_session_deleted(request: Request, session_id: UUID, hard_delete: bool):
    try:
        capture_event(
            request,
            'session_deleted',
            {
                'session_id': session_id,
                'hard_delete': hard_delete,
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'session_deleted' failed: {e}")


# Jobs
def capture_job_created(request: Request, job: Job):
    try:
        capture_event(
            request,
            'job_created',
            {
                'job_id': job.get('id', ''),
                'session_id': job.get('session_id', ''),
                'target_id': job.get('target_id', ''),
                'api_name': job.get('api_name', ''),
                'parameters_count': len(job.get('parameters', {})),
                'api_definition_version_id': job.get('api_definition_version_id', ''),
                'status': job.get('status', ''),
                'created_at': job.get('created_at', ''),
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'job_created' failed: {e}")


def capture_job_interrupted(request: Request, job: Job, initial_status: JobStatus):
    try:
        capture_event(
            request,
            'job_interrupted',
            {
                'job_id': job.get('id', ''),
                'target_id': job.get('target_id', ''),
                'api_name': job.get('api_name', ''),
                'parameters_count': len(job.get('parameters', {})),
                'api_definition_version_id': job.get('api_definition_version_id', ''),
                'duration_seconds': job.get('duration_seconds', ''),
                'total_input_tokens': job.get('total_input_tokens', ''),
                'total_output_tokens': job.get('total_output_tokens', ''),
                'initial_status': initial_status,
                'created_at': job.get('created_at', ''),
                'updated_at': job.get('updated_at', ''),
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'job_interrupted' failed: {e}")


def capture_job_canceled(request: Request, job: Job):
    try:
        completion_time_seconds = (
            (job.get('completed_at') - job.get('created_at')).total_seconds()
            if job.get('completed_at') and job.get('created_at')
            else 0
        )
        completion_time_seconds = int(completion_time_seconds)
        capture_event(
            request,
            'job_canceled',
            {
                'job_id': job.get('id', ''),
                'target_id': job.get('target_id', ''),
                'api_name': job.get('api_name', ''),
                'parameters_count': len(job.get('parameters', {})),
                'api_definition_version_id': job.get('api_definition_version_id', ''),
                'duration_seconds': job.get('duration_seconds', ''),
                'total_input_tokens': job.get('total_input_tokens', ''),
                'total_output_tokens': job.get('total_output_tokens', ''),
                'created_at': job.get('created_at', ''),
                'updated_at': job.get('updated_at', ''),
                'completed_at': job.get('completed_at', ''),
                'completion_time_seconds': completion_time_seconds,
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'job_canceled' failed: {e}")


def capture_job_resolved(request: Request | None, job: Job, manual_resolution: bool):
    try:
        completion_time_seconds = (
            (job.get('completed_at') - job.get('created_at')).total_seconds()
            if job.get('completed_at') and job.get('created_at')
            else 0
        )
        completion_time_seconds = int(completion_time_seconds)
        capture_event(
            request,
            'job_resolved',
            {
                'job_id': job.get('id', ''),
                'target_id': job.get('target_id', ''),
                'api_name': job.get('api_name', ''),
                'parameters_count': len(job.get('parameters', {})),
                'api_definition_version_id': job.get('api_definition_version_id', ''),
                'duration_seconds': job.get(
                    'duration_seconds', '0'
                ),  # TODO: seems not to be included
                'total_input_tokens': job.get('total_input_tokens', 0),
                'total_output_tokens': job.get('total_output_tokens', 0),
                'result_length': len(job.get('result', {})) if job.get('result') else 0,
                'created_at': job.get('created_at', ''),
                'updated_at': job.get('updated_at', ''),
                'completed_at': job.get('completed_at', ''),
                'completion_time_seconds': completion_time_seconds,
                'manual_resolution': manual_resolution,
                'status': job.get('status', ''),
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'job_resolved' failed: {e}")


def capture_job_resumed(request: Request, job: Job):
    try:
        capture_event(
            request,
            'job_resumed',
            {
                'job_id': job.get('id', ''),
                'target_id': job.get('target_id', ''),
                'api_name': job.get('api_name', ''),
                'parameters_count': len(job.get('parameters', {})),
                'api_definition_version_id': job.get('api_definition_version_id', ''),
                'duration_seconds': job.get('duration_seconds', ''),
                'total_input_tokens': job.get('total_input_tokens', ''),
                'total_output_tokens': job.get('total_output_tokens', ''),
                'created_at': job.get('created_at', ''),
                'updated_at': job.get('updated_at', ''),
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'job_resumed' failed: {e}")


def capture_job_log_created(job_id: UUID, log: dict):
    try:
        capture_event(
            None,
            'job_log_created',
            {
                'job_id': job_id,
                'log_type': log.get('log_type', ''),
                'tool_id': log.get('content', {}).get('tool_id', ''),
                'has_image': log.get('content', {}).get('has_image', False),
            },
        )
    except Exception as e:
        logger.debug(f"Telemetry event 'job_log_created' failed: {e}")
