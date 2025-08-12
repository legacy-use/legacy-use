#!/bin/bash

# Function to wait for VPN DNS to be ready
wait_for_vpn_dns() {
    if [ "$REMOTE_VPN_TYPE" = 'openvpn' ]; then
        echo "Waiting for OpenVPN DNS to be configured..."
        # Wait up to 30 seconds for VPN DNS to be ready
        for i in {1..30}; do
            if [ -f /etc/resolv.conf ] && grep -q "nameserver" /etc/resolv.conf; then
                echo "DNS configuration found in /etc/resolv.conf"
                cat /etc/resolv.conf
                return 0
            fi
            echo "Waiting for DNS configuration... (attempt $i/30)"
            sleep 1
        done
        echo "Warning: DNS configuration not found, proceeding anyway"
    fi
}

# Function to test DNS resolution through VPN
test_vpn_dns() {
    local test_host="$1"
    if [ "$REMOTE_VPN_TYPE" = 'openvpn' ]; then
        echo "Testing DNS resolution for $test_host through VPN..."

        # Try to resolve using the VPN's DNS
        local resolved_ip=""
        if command -v nslookup >/dev/null 2>&1; then
            resolved_ip=$(nslookup "$test_host" 2>/dev/null | grep -A1 "Name:" | grep "Address:" | head -1 | awk '{print $2}')
        elif command -v dig >/dev/null 2>&1; then
            resolved_ip=$(dig +short "$test_host" 2>/dev/null | head -1)
        fi

        if [ -n "$resolved_ip" ]; then
            echo "Successfully resolved $test_host to $resolved_ip through VPN"
        else
            echo "Warning: Could not resolve $test_host through VPN DNS"
        fi
    fi
}

# Function to extract and test load balancer hostnames from RDP parameters
test_load_balancer_dns() {
    if [ "$REMOTE_VPN_TYPE" = 'openvpn' ] && [ -n "${RDP_PARAMS}" ]; then
        echo "Checking for load balancer hostnames in RDP parameters..."

        # Extract load-balance-info parameter if present
        local lb_info=$(echo "${RDP_PARAMS}" | grep -o '/load-balance-info:[^[:space:]]*' | sed 's|/load-balance-info:||' | tr -d '"')

        if [ -n "$lb_info" ]; then
            echo "Found load balancer info: $lb_info"

            # Extract hostname from various load balancer formats
            # Format: tsv://MS Terminal Services Plugin.1.HOSTNAME
            local lb_hostname=$(echo "$lb_info" | sed -n 's|.*Plugin\.1\.||p')

            if [ -n "$lb_hostname" ]; then
                echo "Extracted load balancer hostname: $lb_hostname"
                test_vpn_dns "$lb_hostname"
            fi
        fi
    fi
}

# Determine the proxy command based on REMOTE_VPN_TYPE
PROXY_CMD=""
if [ "$REMOTE_VPN_TYPE" != 'direct' ]; then
    if [ "$REMOTE_VPN_TYPE" = 'openvpn' ]; then
        # For OpenVPN, we don't use proxychains since traffic goes through TUN interface
        # DNS resolution will use the VPN's DNS servers configured in /etc/resolv.conf
        PROXY_CMD=""
        wait_for_vpn_dns
    else
        # For other VPN types (wireguard, tailscale), use proxychains
        PROXY_CMD="proxychains"
    fi
fi

if [ "$REMOTE_CLIENT_TYPE" = 'rdp' ]; then
    echo "Starting RDP connection..."

    # Test DNS resolution for the target host
    test_vpn_dns "$HOST_IP"

    # Test DNS resolution for load balancer hostnames in RDP parameters
    test_load_balancer_dns

    # Set keyboard layout with proper error handling
    setxkbmap de -option "" 2>/dev/null || {
        echo "Warning: Could not set keyboard layout to 'de', using default"
        setxkbmap us 2>/dev/null || true
    }

    while true; do
        # For OpenVPN, ensure FreeRDP uses system DNS resolution
        if [ "$REMOTE_VPN_TYPE" = 'openvpn' ]; then
            # Set environment variables to ensure proper DNS resolution
            export FREERDP_DNS_TIMEOUT=10
            export FREERDP_CONNECT_TIMEOUT=30
        fi

        # Build argv as array; no quotes after the colon
        ARGS=(/u:${REMOTE_USERNAME} /p:${REMOTE_PASSWORD} /v:${HOST_IP}:${HOST_PORT})

        if [ -n "${RDP_PARAMS}" ]; then
            # Parse RDP_PARAMS handling both quoted and unquoted parameters safely
            echo "Parsing RDP_PARAMS: ${RDP_PARAMS}"

            # Use eval with array assignment to properly handle quoted strings
            # This is safe because we control the input and only use it for array assignment
            declare -a EXTRA=()
            eval "EXTRA=(${RDP_PARAMS})"

            ARGS+=("${EXTRA[@]}")
            echo "Parsed RDP parameters: ${EXTRA[@]}"
        else
            ARGS+=(/f +auto-reconnect +clipboard /cert:ignore)
        fi

        # Show current DNS configuration for debugging
        if [ "$REMOTE_VPN_TYPE" = 'openvpn' ]; then
            echo "Current DNS configuration:"
            cat /etc/resolv.conf 2>/dev/null || echo "No /etc/resolv.conf found"
            echo "Current routes:"
            ip route 2>/dev/null | head -10 || echo "Could not show routes"
        fi

        $PROXY_CMD xfreerdp3 "${ARGS[@]}"

        echo "RDP connection failed, retrying in 3 sec..."
        sleep 3
    done
elif [ "$REMOTE_CLIENT_TYPE" = 'vnc' ]; then
    echo "Starting VNC connection..."

    # Test DNS resolution for the target host
    test_vpn_dns "$HOST_IP"

    mkdir ~/.vnc
    vncpasswd -f > ~/.vnc/passwd <<EOF
${REMOTE_PASSWORD}
${REMOTE_PASSWORD}
EOF
    chmod 600 ~/.vnc/passwd
    while true; do
        $PROXY_CMD xtigervncviewer -FullScreen -MenuKey=none -passwd ~/.vnc/passwd -ReconnectOnError=0 -AlertOnFatalError=0 ${HOST_IP}:${HOST_PORT}
        echo "VNC connection failed, retrying in 5 secs..."
        sleep 1  # wait before retrying in case of a crash or error
    done
elif [ "$REMOTE_CLIENT_TYPE" = 'teamviewer' ]; then
    echo "Teamviewer not supported yet"
    exit 1
else
    echo "Unsupported REMOTE_CLIENT_TYPE: $REMOTE_CLIENT_TYPE"
    exit 1
fi


# Notes about previous attempts have been moved to the troubleshooting guide.
