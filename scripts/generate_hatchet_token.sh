#!/bin/bash

# Script to generate Hatchet client token for Hatchet Lite
# Run this after docker-compose up to get the token for your .env file

echo "Generating Hatchet client token..."


# Generate token using the hatchet container
TOKEN=$(docker compose exec -T hatchet /hatchet/hatchet-admin token create --config /config --tenant-id 707d0855-80ab-4e1f-a156-f1c4546cbf52 2>/dev/null | tail -1 | tr -d '\r\n')

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
    echo "❌ Failed to generate token. Make sure Hatchet Lite is running."
    echo "Try: docker-compose up -d hatchet"
    exit 1
fi