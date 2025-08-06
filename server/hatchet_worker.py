"""
Hatchet worker for registering and processing tasks.
"""

import logging

# Import the tasks to register them
from server.utils.hatchet_tasks import simple
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
    # The @hatchet.task decorator registers them with the Hatchet instance
    # Import the simple task to ensure it's registered

    logger.info('Tasks registered successfully')
    logger.info('Starting worker to process tasks...')

    # Start the Hatchet worker
    # This will register the tasks and start processing them
    hatchet.worker('test-worker', workflows=[simple]).start()


if __name__ == '__main__':
    main()
