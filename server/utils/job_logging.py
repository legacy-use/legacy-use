"""
Job logging utilities.
"""

import json
import logging
from typing import Any

from server.utils.db_dependencies import TenantAwareDatabaseService

logger = logging.getLogger(__name__)


def trim_base64_images(data):
    """
    Recursively search and trim base64 image data in content structure.

    This function traverses a nested dictionary/list structure and replaces
    base64 image data with "..." to reduce log size.
    """
    if isinstance(data, dict):
        # Check if this is an image content entry with base64 data
        if (
            data.get('type') == 'image'
            and isinstance(data.get('source'), dict)
            and data['source'].get('type') == 'base64'
            and 'data' in data['source']
        ):
            # Replace the base64 data with "..."
            data['source']['data'] = '...'
        else:
            # Recursively process all dictionary values
            for key, value in data.items():
                data[key] = trim_base64_images(value)
    elif isinstance(data, list):
        # Recursively process all list items
        for i, item in enumerate(data):
            data[i] = trim_base64_images(item)

    return data


def trim_http_body(body):
    """
    Process an HTTP body (request or response) to trim base64 image data.

    Handles both string (JSON) and dictionary body formats.
    Returns the trimmed body.
    """
    try:
        # If body is a string that might be JSON, parse it
        if isinstance(body, str):
            try:
                body_json = json.loads(body)
                return json.dumps(trim_base64_images(body_json))
            except json.JSONDecodeError:
                # Not valid JSON, keep as is or set to empty if too large
                if len(body) > 1000:
                    return '<trimmed>'
                return body
        elif isinstance(body, dict):
            return trim_base64_images(body)
        else:
            return body
    except Exception as e:
        logger.error(f'Error trimming HTTP body: {str(e)}')
        return '<trim error>'


def add_job_log(job_id: str, log_type: str, content: Any, tenant_schema: str):
    """Add a log entry for a job with tenant context."""
    from server.database.multi_tenancy import with_db

    with with_db(tenant_schema) as db_session:
        db_service = TenantAwareDatabaseService(db_session)

        # Trim base64 images from content for storage
        trimmed_content = trim_base64_images(content)

        log_data = {
            'job_id': job_id,
            'log_type': log_type,
            'content': content,
            'content_trimmed': trimmed_content,
        }

        db_service.create_job_log(log_data)
        logger.info(f'Added {log_type} log for job {job_id} in tenant {tenant_schema}')
