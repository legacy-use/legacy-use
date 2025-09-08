FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1
ENV USERNAME=legacy-use-mgmt
ENV HOME=/home/$USERNAME

# Install all system dependencies and create user in one layer
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    procps && \
    # Install Docker CLI
    install -m 0755 -d /etc/apt/keyrings && \
    curl -fsSL https://download.docker.com/linux/debian/gpg | tee /etc/apt/keyrings/docker.asc > /dev/null && \
    chmod a+r /etc/apt/keyrings/docker.asc && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null && \
    apt-get update && \
    apt-get install -y docker-ce-cli && \
    # Create user
    useradd -m -s /bin/bash -d $HOME $USERNAME && \
    groupadd -f docker && \
    usermod -aG docker $USERNAME && \
    mkdir -p $HOME/.cache && \
    chown -R $USERNAME:$USERNAME $HOME/.cache && \
    # Install Tesseract
    apt-get install -y tesseract-ocr && \
    apt-get install -y libtesseract-dev && \
    # Clean up to reduce image size
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

USER $USERNAME
WORKDIR $HOME

# Copy and install Python requirements with uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY --chown=$USERNAME:$USERNAME pyproject.toml uv.lock $HOME/
RUN uv sync --locked --no-cache

# Copy backend application code
COPY --chown=$USERNAME:$USERNAME server/ $HOME/server/

# Create entrypoint script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
# Handle .env.local file persistence using mounted volume\n\
mkdir -p "$HOME/persistent-config"\n\
if [ ! -f "$HOME/persistent-config/.env.local" ]; then\n\
    touch "$HOME/persistent-config/.env.local"\n\
fi\n\
# Create symlink to the expected location (remove existing file/link first)\n\
rm -f "$HOME/.env.local"\n\
ln -sf "$HOME/persistent-config/.env.local" "$HOME/.env.local"\n\
\n\
echo "Running migrations"\n\
uv run alembic -c server/alembic.ini upgrade head\n\
\n\
echo "Starting FastAPI server"\n\
FASTAPI_SERVER_PORT=8088\n\
\n\
# Check if debug mode is enabled\n\
if [ "${LEGACY_USE_DEBUG:-0}" = "1" ]; then\n\
    echo "Debug mode enabled: Using hot reload"\n\
    exec uv run uvicorn server.server:app --host 0.0.0.0 --port $FASTAPI_SERVER_PORT --reload --reload-dir server\n\
else\n\
    echo "Production mode: Determining worker count"\n\
    if command -v nproc >/dev/null 2>&1; then\n\
        CPU_COUNT=$(nproc)\n\
    elif command -v getconf >/dev/null 2>&1; then\n\
        CPU_COUNT=$(getconf _NPROCESSORS_ONLN)\n\
    else\n\
        CPU_COUNT=1\n\
    fi\n\
    WORKERS="${GUNICORN_WORKERS:-$CPU_COUNT}"\n\
    echo "Using $WORKERS workers"\n\
    exec uv run gunicorn -w $WORKERS -k uvicorn.workers.UvicornWorker server.server:app --threads 1 --bind 0.0.0.0:$FASTAPI_SERVER_PORT --timeout 300 --graceful-timeout 300\n\
fi' > $HOME/entrypoint.sh && \
    chmod +x $HOME/entrypoint.sh

EXPOSE 8088

ENTRYPOINT ["./entrypoint.sh"]
