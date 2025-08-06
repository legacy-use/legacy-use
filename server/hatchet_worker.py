#!/usr/bin/env python3
"""
Hatchet worker for processing job execution workflows.

This script runs a Hatchet worker that processes job execution requests
from the main application. It should be run as a separate process.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Add the server directory to the Python path
server_dir = Path(__file__).parent
sys.path.insert(0, str(server_dir.parent))

from server.utils.hatchet_client import hatchet_job_manager  # noqa: E402

# Set up logging
logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    """Main function to start the Hatchet worker."""
    logger.info('Starting Hatchet worker for job execution...')

    try:
        # Get the Hatchet client
        hatchet = hatchet_job_manager.hatchet

        # Create and start the worker
        worker = hatchet.worker('job-execution-worker')

        # Register the job execution workflow
        workflow = hatchet_job_manager.get_workflow()
        worker.register_workflow(workflow)

        logger.info('Hatchet worker registered and starting...')

        # Start the worker (this will block)
        await worker.async_start()

    except KeyboardInterrupt:
        logger.info('Hatchet worker interrupted by user')
    except Exception as e:
        logger.error(f'Hatchet worker failed: {str(e)}')
        raise
    finally:
        logger.info('Hatchet worker shutting down')


if __name__ == '__main__':
    # Check for required environment variables
    required_env_vars = ['HATCHET_CLIENT_TOKEN', 'DATABASE_URL']

    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(f'Missing required environment variables: {missing_vars}')
        sys.exit(1)

    # Run the worker
    asyncio.run(main())
