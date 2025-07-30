#!/bin/bash

set -e

# Default to debug mode if not specified
export LEGACY_USE_DEBUG=${LEGACY_USE_DEBUG:-0}

# Check if we're running in an AWS environment
# This checks for the EC2 metadata service
IS_AWS=0
if curl -s --connect-timeout 1 http://169.254.169.254/latest/meta-data/ > /dev/null 2>&1; then
    IS_AWS=1
    echo "Detected AWS environment"
fi

# Check if .env.local exists, else create empty file
if [ ! -f .env.local ]; then
    touch .env.local
fi

uv run python generate_api_key.py

# Base docker run command
DOCKER_CMD="docker run -u root \
    --env-file .env \
    --env-file .env.local \
    -v $HOME/.anthropic:/home/legacy-use-mgmt/.anthropic \
    -v /var/run/docker.sock:/var/run/docker.sock \
    -v $HOME/.config/gcloud/application_default_credentials.json:/home/legacy-use-mgmt/.config/gcloud/application_default_credentials.json \
    -p 8088:8088 \
    -p 5173:5173 \
    -e LEGACY_USE_DEBUG=$LEGACY_USE_DEBUG"

# Configure database connection if in AWS and production mode
if [ "$IS_AWS" = "1" ] && [ "$LEGACY_USE_DEBUG" = "0" ]; then
    echo "Retrieving DATABASE_URL from AWS Secrets Manager"
    # Get the complete DATABASE_URL from AWS Secrets Manager
    # Terraform should store the full connection string in this secret
    SECRET_NAME="legacy-use-mgmt-database-url"
    DATABASE_URL=$(aws secretsmanager get-secret-value --secret-id $SECRET_NAME --query SecretString --output text)

    # Add the DATABASE_URL to the docker command
    DOCKER_CMD="$DOCKER_CMD -e DATABASE_URL=\"${DATABASE_URL}\""
fi

# Add volume mounts for development if in debug mode
if [ "$LEGACY_USE_DEBUG" = "1" ]; then
    echo "Running in DEBUG mode with directory mounts for hot reloading"
    DOCKER_CMD="$DOCKER_CMD \
    -v $(pwd)/server:/home/legacy-use-mgmt/server/ \
    -v $(pwd)/app:/home/legacy-use-mgmt/app/ \
    -v $(pwd)/.env.local:/home/legacy-use-mgmt/.env.local"
else
    echo "Running in PRODUCTION mode without directory mounts"
    DOCKER_CMD="$DOCKER_CMD \
    -v $(pwd)/.env.local:/home/legacy-use-mgmt/.env.local"
fi

# Complete the docker command with appropriate flags based on mode
if [ "$LEGACY_USE_DEBUG" = "1" ]; then
    # Interactive mode for debugging
    DOCKER_CMD="$DOCKER_CMD \
    --name legacy-use-mgmt \
    --rm -it legacy-use-mgmt:local"
else
    # Detached mode for production
    DOCKER_CMD="$DOCKER_CMD \
    --name legacy-use-mgmt \
    --rm -d legacy-use-mgmt:local"
fi

# Execute the docker command
eval $DOCKER_CMD
