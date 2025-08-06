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

# Create RustDesk config directory
mkdir -p ~/.config/rustdesk

# Configure RustDesk for headless operation
cat > ~/.config/rustdesk/RustDesk2.toml << EOF
[options]
custom-rendezvous-server = ""
relay-server = ""
api-server = ""
key = ""

[ui]
show_monitors_tip = false
EOF

echo "Configuring RustDesk with ID: $RUSTDESK_ID"

# Debug
echo "Binary path: $(which rustdesk)"
# Version
rustdesk --version
# User
whoami

# Start RustDesk in service mode (headless)
export DISPLAY=:${DISPLAY_NUM}
rustdesk --service &
RUSTDESK_PID=$!

# Wait for service to initialize
sleep 5

# Set the password for incoming connections
echo "Setting RustDesk password..."
rustdesk --password "$RUSTDESK_PASSWORD" || true

# Display connection information
echo "========================================="
echo "RustDesk is running in headless mode"
echo "ID: $RUSTDESK_ID"
echo "Password: $RUSTDESK_PASSWORD"
echo "Use these credentials to connect remotely"
echo "========================================="

# Monitor RustDesk process and restart if needed
while true; do
    if ! kill -0 $RUSTDESK_PID 2>/dev/null; then
        echo "RustDesk service died, restarting..."
        rustdesk --service &
        RUSTDESK_PID=$!
        sleep 5
        rustdesk --password "$RUSTDESK_PASSWORD" || true
    fi
    sleep 30
done
