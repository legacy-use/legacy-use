# Multi-stage build for frontend optimization
FROM node:20-slim as builder

ENV DEBIAN_FRONTEND=noninteractive

# Create user
ENV USERNAME=legacy-use-mgmt
ENV HOME=/home/$USERNAME
RUN useradd -m -s /bin/bash -d $HOME $USERNAME

USER $USERNAME
WORKDIR $HOME

# Copy package files first for better layer caching
COPY --chown=$USERNAME:$USERNAME package.json pnpm-lock.yaml $HOME/

# Install all dependencies (including dev dependencies for building)
RUN npm install --global corepack@latest && \
    corepack enable && \
    corepack use pnpm && \
    cd $HOME && pnpm install --frozen-lockfile

# Copy source code in correct structure
COPY --chown=$USERNAME:$USERNAME app/ $HOME/app/
COPY --chown=$USERNAME:$USERNAME public/ $HOME/public/
COPY --chown=$USERNAME:$USERNAME index.html vite.config.js $HOME/
COPY --chown=$USERNAME:$USERNAME tsconfig.json biome.json $HOME/

# Final runtime stage
FROM node:20-slim

ENV DEBIAN_FRONTEND=noninteractive

# Create user
ENV USERNAME=legacy-use-mgmt
ENV HOME=/home/$USERNAME
RUN useradd -m -s /bin/bash -d $HOME $USERNAME

USER $USERNAME
WORKDIR $HOME

# Copy all necessary files from builder stage
COPY --from=builder --chown=$USERNAME:$USERNAME $HOME/package.json $HOME/pnpm-lock.yaml $HOME/
COPY --from=builder --chown=$USERNAME:$USERNAME $HOME/node_modules $HOME/node_modules
COPY --from=builder --chown=$USERNAME:$USERNAME $HOME/app $HOME/app
COPY --from=builder --chown=$USERNAME:$USERNAME $HOME/public $HOME/public
COPY --from=builder --chown=$USERNAME:$USERNAME $HOME/index.html $HOME/vite.config.js $HOME/
COPY --from=builder --chown=$USERNAME:$USERNAME $HOME/tsconfig.json $HOME/biome.json $HOME/

# Create entrypoint script
RUN echo '#!/bin/bash\n\
set -e\n\
\n\
echo "Starting React app"\n\
\n\
# Check if debug mode is enabled\n\
if [ "${LEGACY_USE_DEBUG:-0}" = "1" ]; then\n\
    echo "Debug mode: Installing/updating node dependencies"\n\
    pnpm install --frozen-lockfile\n\
fi\n\
\
echo "Starting development server"\n\
exec pnpm start' > $HOME/entrypoint.sh && \
    chmod +x $HOME/entrypoint.sh

EXPOSE 5173

ENTRYPOINT ["./entrypoint.sh"]
