#!/bin/bash

# Start RustDesk in headless mode
# This script configures and starts RustDesk for remote access

echo "Starting RustDesk in headless mode..."

# Set RustDesk ID and password from environment variables
RUSTDESK_ID="${HOST_IP}"  # Using HOST_IP field for RustDesk ID
RUSTDESK_PASSWORD="${REMOTE_PASSWORD}"  # Using password field for one-time password

if [ -z "$RUSTDESK_ID" ] || [ -z "$RUSTDESK_PASSWORD" ]; then
    echo "Error: RustDesk ID and password must be provided"
    exit 1
fi

rustdesk --connect "$RUSTDESK_ID" --password "$RUSTDESK_PASSWORD"
