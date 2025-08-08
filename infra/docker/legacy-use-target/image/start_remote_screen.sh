#!/bin/bash

# Determine the proxy command based on REMOTE_VPN_TYPE
PROXY_CMD=""
if [ "$REMOTE_VPN_TYPE" != 'direct' ]; then
    PROXY_CMD="proxychains"
fi

if [ "$REMOTE_CLIENT_TYPE" = 'rdp' ]; then
    echo "Starting RDP connection..."
    setxkbmap de # TODO: fix this, once we move to other countries
    while true; do
        # Always include host/username/password and allow params to override/add
        DEFAULT_RDP_PARAMS="/u:${REMOTE_USERNAME} /p:\"${REMOTE_PASSWORD}\" /v:${HOST_IP}:${HOST_PORT} /f +auto-reconnect +clipboard /cert-ignore"
        # If user provided params, append them (they can override duplicates)
        if [ -n "${RDP_PARAMS}" ]; then
            CMD_ARGS="${DEFAULT_RDP_PARAMS} ${RDP_PARAMS}"
        else
            CMD_ARGS="${DEFAULT_RDP_PARAMS}"
        fi
        # shellcheck disable=SC2086
        $PROXY_CMD xfreerdp ${CMD_ARGS}
        echo "RDP connection failed, retrying in 1 sec..."
        sleep 1  # wait before retrying in case of a crash or error
    done
elif [ "$REMOTE_CLIENT_TYPE" = 'vnc' ]; then
    echo "Starting VNC connection..."
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
