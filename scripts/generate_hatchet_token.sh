#!/bin/bash

# Script to generate Hatchet client token
# Run this after docker-compose up to get the token for your .env file

echo "Generating Hatchet client token..."

# Wait for Hatchet services to be ready
echo "Waiting for Hatchet services to start..."
sleep 10

# Generate token using the setup-config container
TOKEN=$(docker compose run --no-deps --rm hatchet-setup-config /hatchet/hatchet-admin token create --config /hatchet/config --tenant-id 707d0855-80ab-4e1f-a156-f1c4546cbf52 2>/dev/null | tail -1 | tr -d '\r\n')

if [ -n "$TOKEN" ]; then
    echo ""
    echo "✅ Hatchet client token generated successfully!"
    echo ""
    echo "Add this to your .env file:"
    echo "HATCHET_CLIENT_TOKEN=$TOKEN"
    echo ""
    echo "You can also run this command to add it automatically:"
    echo "echo 'HATCHET_CLIENT_TOKEN=$TOKEN' >> .env"
    echo ""
else
    echo "❌ Failed to generate token. Make sure Hatchet services are running."
    echo "Try: docker-compose up -d"
    exit 1
fi