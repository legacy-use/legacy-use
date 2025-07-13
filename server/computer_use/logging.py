"""
Logging setup for the Computer Use API Gateway.
"""

import logging
from datetime import datetime
from pathlib import Path

# Setup logging - replace the existing logging setup
LOG_DIR = Path('logs')
LOG_DIR.mkdir(exist_ok=True)

# Use a fixed filename instead of timestamp-based name
log_file = LOG_DIR / 'api_debug.log'

# Create a formatter that includes timestamp
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Create file handler with mode='a' to append instead of overwrite
file_handler = logging.FileHandler(log_file, mode='a')
file_handler.setFormatter(formatter)

# Setup logger
logger = logging.getLogger('server')
logger.setLevel(logging.DEBUG)
logger.addHandler(file_handler)

# Add a startup message to separate runs
logger.info('=' * 80)
logger.info(f'New API Gateway session started at {datetime.utcnow().isoformat()}')
logger.info('=' * 80)
