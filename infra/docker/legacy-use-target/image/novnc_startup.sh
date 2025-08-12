#!/bin/bash
echo "starting noVNC"

# Start noVNC with explicit websocket settings
/opt/noVNC/utils/novnc_proxy \
    --vnc 127.0.0.1:5900 \
    --listen 6080 \
    --web /opt/noVNC \
    > /tmp/novnc.log 2>&1 &

##--vnc 192.168.64.2:5900 \
# Wait for noVNC to start
timeout=10
while [ "$timeout" -gt 0 ]; do
    if netstat -tuln | grep -q ":6080 "; then
        break
    fi
    sleep 1
    ((timeout--))
done

echo "noVNC started successfully"
