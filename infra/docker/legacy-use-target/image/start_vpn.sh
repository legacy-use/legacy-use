#!/bin/bash
set -e

echo "Starting VPN..."

if [ "$REMOTE_VPN_TYPE" = 'wireguard' ]; then
    echo "Writing wireproxy config..."

    echo "$VPN_CONFIG" > wireproxy.toml && cat <<EOF >> wireproxy.toml
[Socks5]
BindAddress = 127.0.0.1:1080
EOF

    LOG_FILE=/tmp/wireproxy.log
    HANDSHAKE_PATTERN="Sending handshake initiation"

    echo "Starting wireproxy..."
    ~/go/bin/wireproxy -c wireproxy.toml >> "$LOG_FILE" 2>&1 &

    WIREPROXY_PID=$!

    echo "Watchdog started..."

    # Watchdog loop
    while true; do
        COUNT=$(tail -n 50 "$LOG_FILE" | grep "$HANDSHAKE_PATTERN" | tail -n 5 | wc -l)
        if [ "$COUNT" -ge 5 ]; then
            echo "$(date) - Detected $COUNT handshakes in a row, restarting wireproxy"
            kill "$WIREPROXY_PID"
            sleep 2
            ~/go/bin/wireproxy -c wireproxy.toml >> "$LOG_FILE" 2>&1 &
            WIREPROXY_PID=$!
        fi
        sleep 10
    done
elif [ "$REMOTE_VPN_TYPE" = 'tailscale' ]; then
    echo "Starting tailscale..."
    sudo tailscaled --tun=userspace-networking  --socks5-server=localhost:1080  &
    sudo tailscale up --authkey=${VPN_CONFIG}
elif [ "$REMOTE_VPN_TYPE" = 'openvpn' ]; then
    echo "Starting openvpn..."

    # Create authentication file for OpenVPN using VPN_CONFIG
    # Expects the following format:
    # <USER>\n<PASSWORD>
    AUTH_FILE="/tmp/openvpn_auth.txt"
    echo "$VPN_USERNAME" > "$AUTH_FILE"
    echo "$VPN_PASSWORD" >> "$AUTH_FILE"
    chmod 600 "$AUTH_FILE"

    # Create TUN device files and interface
    sudo mkdir -p /dev/net

    # Create /dev/net/tun device file if it doesn't exist
    if [ ! -c /dev/net/tun ]; then
        sudo mknod /dev/net/tun c 10 200
        sudo chmod 666 /dev/net/tun
    fi

    # Load TUN module
    echo "Loading TUN module..."
    if command -v modprobe >/dev/null 2>&1; then
        sudo modprobe tun 2>/dev/null || true
    fi

    if ip link show tun0 2>/dev/null; then
        sudo ip link delete tun0 2>/dev/null || true
    fi

    sudo ip tuntap add dev tun0 mode tun 2>/dev/null || true

    # Decode base64 config to temporary file
    CONFIG_FILE="/tmp/openvpn_config.ovpn"
    echo "$VPN_CONFIG" | base64 -d > "$CONFIG_FILE"
    chmod 600 "$CONFIG_FILE"

    # Create OpenVPN up script to handle DNS and routing
    cat > /tmp/openvpn-up.sh << 'EOF'
#!/bin/bash
echo "OpenVPN UP script called with:"
echo "Interface: $dev"
echo "Local IP: $ifconfig_local"
echo "Remote IP: $ifconfig_remote"
echo "Environment variables:"
env | grep -E "^(route_|dhcp_option_)" || echo "No route/dhcp options found"

# Backup original resolv.conf
cp /etc/resolv.conf /etc/resolv.conf.backup

# Handle pushed DNS servers
if [ -n "$foreign_option_1" ]; then
    echo "Processing foreign options:"
    env | grep foreign_option

    # Create new resolv.conf with VPN DNS servers
    > /etc/resolv.conf.openvpn

    for optname in $(env | grep '^foreign_option_' | cut -d= -f1); do
        option=$(env | grep "^$optname=" | cut -d= -f2-)
        echo "Processing: $option"

        if echo "$option" | grep -q "^dhcp-option DNS"; then
            dns_server=$(echo "$option" | sed 's/dhcp-option DNS //')
            echo "nameserver $dns_server" >> /etc/resolv.conf.openvpn
            echo "Added DNS server: $dns_server"
        fi

        if echo "$option" | grep -q "^dhcp-option DOMAIN"; then
            domain=$(echo "$option" | sed 's/dhcp-option DOMAIN //')
            echo "search $domain" >> /etc/resolv.conf.openvpn
            echo "domain $domain" >> /etc/resolv.conf.openvpn
            echo "Added domain: $domain"
        fi
    done

    # Use OpenVPN DNS if we found any, otherwise keep original
    if [ -s /etc/resolv.conf.openvpn ]; then
        cat /etc/resolv.conf.openvpn > /etc/resolv.conf
        echo "Updated /etc/resolv.conf with VPN DNS servers"
    else
        echo "No VPN DNS servers found, keeping original resolv.conf"
    fi
fi

# Add any additional routes if needed
echo "Current routes after OpenVPN connection:"
ip route
EOF

    chmod +x /tmp/openvpn-up.sh

    # Create OpenVPN down script to restore DNS
    cat > /tmp/openvpn-down.sh << 'EOF'
#!/bin/bash
echo "OpenVPN DOWN script called"

# Restore original resolv.conf
if [ -f /etc/resolv.conf.backup ]; then
    cp /etc/resolv.conf.backup /etc/resolv.conf
    echo "Restored original /etc/resolv.conf"
fi

# Clean up
rm -f /etc/resolv.conf.openvpn /etc/resolv.conf.backup
EOF

    chmod +x /tmp/openvpn-down.sh

    # Start OpenVPN using the temporary config file
    OPENVPN_LOG="/tmp/openvpn.log"
    echo "Starting OpenVPN with logging to $OPENVPN_LOG..."
    sudo openvpn --config "$CONFIG_FILE" \
        --auth-user-pass "$AUTH_FILE" \
        --verb 4 \
        --log "$OPENVPN_LOG" \
        --data-ciphers "AES-256-GCM:AES-128-GCM:AES-128-CBC:CHACHA20-POLY1305" \
        --cipher AES-128-CBC \
        --dev tun0 \
        --script-security 2 \
        --up "/tmp/openvpn-up.sh" \
        --down "/tmp/openvpn-down.sh" \
        --daemon

    # Wait for OpenVPN connection
    for i in {1..30}; do
        if ip addr show tun0 2>/dev/null | grep -q "inet "; then
            echo "OpenVPN connected"
            break
        fi
        echo "Waiting for OpenVPN connection... (attempt $i/30)"
        sleep 2
    done

    # Additional connection verification
    if ! ip addr show tun0 2>/dev/null | grep -q "inet "; then
        echo "ERROR: OpenVPN failed to establish connection - tun0 has no IP"
        echo "OpenVPN log:"
        tail -20 "$OPENVPN_LOG"
        exit 1
    fi

    # Wait a bit more for routes and DNS to be fully configured
    echo "Waiting for OpenVPN to finish route configuration..."
    sleep 5

    # Check if we need to manually add routes for internal networks
    # This is often needed when OpenVPN doesn't push all necessary routes
    TUN0_IP=$(ip addr show tun0 | grep "inet " | awk '{print $2}' | cut -d/ -f1)
    TUN0_GW=$(ip route | grep "dev tun0" | grep -v "$TUN0_IP" | head -1 | awk '{print $1}' | cut -d/ -f1)

    echo "TUN0 IP: $TUN0_IP"
    echo "TUN0 Gateway/Network: $TUN0_GW"

    # Try to detect internal network ranges and add routes if missing
    # Common corporate internal networks
    INTERNAL_NETWORKS="10.0.0.0/8 172.16.0.0/12 192.168.0.0/16"

    for network in $INTERNAL_NETWORKS; do
        # Check if route to this internal network exists
        if ! ip route get $(echo $network | cut -d/ -f1) 2>/dev/null | grep -q "dev tun0"; then
            # Check if this network might be reachable via VPN by testing if target is in range
            if echo "$HOST_IP" | grep -qE "^(10\.|172\.(1[6-9]|2[0-9]|3[01])\.|192\.168\.)"; then
                echo "Adding route for internal network $network via tun0"
                sudo ip route add $network dev tun0 2>/dev/null || echo "Failed to add route for $network"
            fi
        fi
    done

    # Ensure specific route to target host goes via VPN
    if [ -n "$HOST_IP" ] && echo "$HOST_IP" | grep -qE "^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$"; then
        echo "Ensuring route to target $HOST_IP goes via VPN..."
        # Remove any existing route to the host via default gateway
        sudo ip route del "$HOST_IP" 2>/dev/null || true
        # Add explicit route via tun0
        sudo ip route add "$HOST_IP" dev tun0 2>/dev/null || echo "Note: Could not add specific route for $HOST_IP"
    elif [ -n "$HOST_IP" ] && ! echo "$HOST_IP" | grep -qE "^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$"; then
        echo "HOST_IP is a hostname: $HOST_IP - will rely on DNS resolution through VPN"
    fi

    # Show the status of the VPN
    echo "=== OpenVPN Connection Status ==="
    ip addr show tun0
    echo ""
    echo "=== Routing Table ==="
    ip route
    echo ""
    echo "=== DNS Configuration ==="
    cat /etc/resolv.conf
    echo ""
    echo "=== Testing DNS resolution ==="
    nslookup google.com || echo "Google DNS lookup failed"
    nslookup $HOST_IP || echo "HOST_IP DNS lookup failed"
    dig $HOST_IP || echo "dig failed"
    echo ""
    echo "=== Testing connectivity ==="
    echo "Testing ping to google.com (should work via default route)"
    ping -c 1 -W 5 google.com || echo "Google ping failed"

    echo "Testing ping to $HOST_IP via default route"
    ping -c 1 -W 5 $HOST_IP || echo "HOST_IP ping via default failed"

    echo "Testing ping to $HOST_IP via tun0 interface"
    ping -I tun0 -c 1 -W 5 $HOST_IP || echo "HOST_IP ping via tun0 failed"

    # If hostname resolution fails, try manual DNS resolution through VPN
    if [ -n "$HOST_IP" ] && ! echo "$HOST_IP" | grep -qE "^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$"; then
        echo "Attempting DNS resolution of $HOST_IP through VPN..."

        # Get VPN DNS servers from resolv.conf
        VPN_DNS=$(grep nameserver /etc/resolv.conf | head -1 | awk '{print $2}')
        if [ -n "$VPN_DNS" ]; then
            echo "Using VPN DNS server: $VPN_DNS"
            RESOLVED_IP=$(nslookup "$HOST_IP" "$VPN_DNS" 2>/dev/null | grep -A1 "Name:" | grep "Address:" | awk '{print $2}' | head -1)
            if [ -n "$RESOLVED_IP" ]; then
                echo "Resolved $HOST_IP to $RESOLVED_IP via VPN DNS"
                echo "Testing ping to resolved IP via tun0:"
                ping -I tun0 -c 1 -W 5 "$RESOLVED_IP" || echo "Ping to resolved IP failed"
            else
                echo "Failed to resolve $HOST_IP via VPN DNS $VPN_DNS"
            fi
        else
            echo "No VPN DNS server found in /etc/resolv.conf"
        fi
    fi
    echo ""

    # Start SOCKS proxy that routes through OpenVPN TUN interface
    if ip addr show tun0 2>/dev/null | grep -q "inet "; then
        echo "Starting SOCKS proxy on 127.0.0.1:1080 that routes through OpenVPN..."

        # Start the Python SOCKS proxy server
        python3 /socks_proxy.py &

        SOCKS_PID=$!
        echo "SOCKS proxy started with PID: $SOCKS_PID"

        # Give proxy a moment to start
        sleep 2
    else
        echo "OpenVPN connection failed - tun0 interface not available"
        exit 1
    fi

    # Clean up temporary config file and authentication file
    rm -f "$CONFIG_FILE"
    rm -f "$AUTH_FILE"

elif [ "$REMOTE_VPN_TYPE" = 'direct' ]; then
    echo "Direct connection selected. No VPN action will be taken."
else
    echo "Unsupported REMOTE_VPN_TYPE: $REMOTE_VPN_TYPE"
    exit 1
fi
