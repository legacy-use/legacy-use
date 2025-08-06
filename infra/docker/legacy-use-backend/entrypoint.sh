#!/bin/bash
set -e

# Handle .env.local file persistence using mounted volume
mkdir -p "$HOME/persistent-config"
if [ ! -f "$HOME/persistent-config/.env.local" ]; then
    touch "$HOME/persistent-config/.env.local"
fi
# Create symlink to the expected location (remove existing file/link first)
rm -f "$HOME/.env.local"
ln -sf "$HOME/persistent-config/.env.local" "$HOME/.env.local"

# Default to "api" if CONTAINER_TYPE is not set
CONTAINER_TYPE="${CONTAINER_TYPE:-api}"

if [ "$CONTAINER_TYPE" = "api" ]; then
    echo "Running as API server"
    echo "Running migrations"
    uv run alembic -c server/alembic.ini upgrade head

    echo "Starting FastAPI server"
    FASTAPI_SERVER_PORT=8088

    # Check if debug mode is enabled
    if [ "${LEGACY_USE_DEBUG:-0}" = "1" ]; then
        echo "Debug mode enabled: Using hot reload"
        exec uv run uvicorn server.server:app --host 0.0.0.0 --port $FASTAPI_SERVER_PORT --reload --reload-dir server
    else
        echo "Production mode: Using workers without reload"
        exec uv run gunicorn -w 1 -k uvicorn.workers.UvicornH11Worker server.server:app --threads 4 --bind 0.0.0.0:$FASTAPI_SERVER_PORT
    fi
elif [ "$CONTAINER_TYPE" = "worker" ]; then
    echo "Running as Hatchet worker (boom)"
    cd /home/legacy-use-mgmt
    export PYTHONPATH="/home/legacy-use-mgmt:$PYTHONPATH"
    exec uv run python -m server.hatchet_worker
else
    echo "Error: Invalid CONTAINER_TYPE: $CONTAINER_TYPE. Must be 'api' or 'worker'."
    exit 1
fi
