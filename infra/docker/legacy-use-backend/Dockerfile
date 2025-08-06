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
    gnupg  && \
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

# Copy entrypoint script
COPY --chown=$USERNAME:$USERNAME infra/docker/legacy-use-backend/entrypoint.sh $HOME/entrypoint.sh
RUN chmod +x $HOME/entrypoint.sh

EXPOSE 8088

ENTRYPOINT ["./entrypoint.sh"]
