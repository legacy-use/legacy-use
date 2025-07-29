"""
Utility functions for job-related computations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List

from server.models.base import JobStatus


def compute_job_metrics(
    job: Dict[str, Any], http_exchanges: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Compute job metrics including duration and token usage.

    Args:
        job: The job dictionary containing job data
        http_exchanges: Optional list of HTTP exchanges for the job

    Returns:
        Dict containing computed metrics (duration_seconds, total_input_tokens, total_output_tokens)
    """
    # Calculate duration
    created_at = datetime.fromisoformat(str(job['created_at']))

    # Ensure timezone consistency - make naive datetimes timezone-aware if needed
    if created_at.tzinfo is None:
        # Make naive datetimes timezone-aware
        now = datetime.now(timezone.utc)
    else:
        # PostgreSQL datetimes are timezone-aware, so we need to make datetime.now() aware too
        now = datetime.now(timezone.utc)

    if job['status'] in [JobStatus.SUCCESS, JobStatus.ERROR]:
        # For completed jobs, use completed_at if available, otherwise duration is null
        if job.get('completed_at'):
            completed_at = datetime.fromisoformat(str(job['completed_at']))
            # Ensure both datetimes have consistent timezone information
            if created_at.tzinfo is not None and completed_at.tzinfo is None:
                completed_at = completed_at.replace(tzinfo=created_at.tzinfo)
            elif created_at.tzinfo is None and completed_at.tzinfo is not None:
                created_at = created_at.replace(tzinfo=completed_at.tzinfo)

            duration = (completed_at - created_at).total_seconds()
        else:
            # For legacy jobs without completed_at timestamp
            duration = None
    else:
        # For running jobs, use current time
        duration = (now - created_at).total_seconds()

    # Calculate token usage from HTTP exchanges if provided
    total_input = 0
    total_output = 0

    if http_exchanges:
        for exchange in http_exchanges:
            # Prefer to use content_trimmed for token counting if available
            # This should contain the token usage info without the heavy image data
            content = exchange.get('content_trimmed', exchange.get('content', {}))

            # Check for token usage directly in the exchange (new format)
            if 'input_tokens' in content:
                total_input += content['input_tokens']
            if 'output_tokens' in content:
                total_output += content['output_tokens']
            if 'cache_creation_tokens' in content:
                total_input += content['cache_creation_tokens']
            if 'cache_read_tokens' in content:
                total_input += content['cache_read_tokens']

    return {
        'duration_seconds': duration,
        'total_input_tokens': total_input,
        'total_output_tokens': total_output,
    }
