"""
Hatchet worker for registering and processing tasks.
"""

import logging

# Import the tasks to register them
from server.utils.hatchet_tasks import execute_job, orchestrate_target
from server.utils.hatchet_client import get_hatchet_client

# Get the shared Hatchet client instance
hatchet = get_hatchet_client()

logger = logging.getLogger(__name__)


def main():
    """Start the Hatchet worker."""
    logger.info('Starting Hatchet worker...')

    # Import and register all tasks
    logger.info('Registering tasks...')

    # The tasks are automatically registered when imported
    logger.info('Tasks registered successfully')
    logger.info('Starting worker to process tasks...')

    # Start the Hatchet worker with the job execution task
    hatchet.worker(
        'legacy-use-worker', workflows=[execute_job, orchestrate_target]
    ).start()


if __name__ == '__main__':
    main()
