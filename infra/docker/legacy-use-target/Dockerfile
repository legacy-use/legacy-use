FROM docker.io/ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
ENV DEBIAN_PRIORITY=high

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    wget \
    gnupg \
    ca-certificates \
    # UI Requirements
    xvfb \
    xdotool \
    scrot \
    sudo \
    x11vnc \
    autocutsel \
    # Network tools
    net-tools \
    netcat-openbsd \
    iputils-ping \
    openvpn \
    proxychains \
    # Remote clients
    freerdp2-x11 \
    tigervnc-viewer \
    # Python
    python3 \
    python3-pip \
    python3-venv \
    tightvncserver \
    # Video recording
    ffmpeg && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* && \
    rm -rf /tmp/* /var/tmp/*

# Install git temporarily for cloning operations
RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    # Install noVNC
    git clone --branch v1.5.0 https://github.com/novnc/noVNC.git /opt/noVNC && \
    git clone --branch v0.12.0 https://github.com/novnc/websockify /opt/noVNC/utils/websockify && \
    ln -s /opt/noVNC/vnc.html /opt/noVNC/index.html && \
    # Remove git after use
    apt-get remove -y git && \
    apt-get autoremove -y && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Install Tailscale using official package repository
RUN curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg | tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null && \
    curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list | tee /etc/apt/sources.list.d/tailscale.list && \
    apt-get update && \
    apt-get install -y tailscale && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# setup user
ENV USERNAME=legacy-use
ENV HOME=/home/$USERNAME
RUN useradd -m -s /bin/bash -d $HOME $USERNAME && \
    echo "${USERNAME} ALL=(ALL) NOPASSWD: ALL" >> /etc/sudoers && \
    mkdir -p $HOME/.cache && \
    chown -R $USERNAME:$USERNAME $HOME/.cache
USER legacy-use
WORKDIR $HOME

# Detect architecture and download appropriate wireproxy binary
ARG TARGETARCH
ARG TARGETOS=linux
RUN case "$TARGETARCH" in \
        amd64) ARCH=amd64 ;; \
        arm64) ARCH=arm64 ;; \
        arm) ARCH=armv7 ;; \
        *) echo "Unsupported architecture: $TARGETARCH" && exit 1 ;; \
    esac && \
    curl -L -o /tmp/wireproxy.tar.gz "https://github.com/whyvl/wireproxy/releases/download/v1.0.9/wireproxy_${TARGETOS}_${ARCH}.tar.gz" && \
    tar -xzf /tmp/wireproxy.tar.gz -C /tmp && \
    sudo mv /tmp/wireproxy /usr/local/bin/wireproxy && \
    sudo chmod +x /usr/local/bin/wireproxy && \
    rm /tmp/wireproxy.tar.gz

# Copy SOCKS proxy server script
COPY infra/docker/legacy-use-target/image/socks_proxy.py /socks_proxy.py

# Copy requirements.txt and install dependencies
COPY --chown=$USERNAME:$USERNAME infra/docker/legacy-use-target/requirements.txt $HOME/
# Create virtual environment
RUN python3 -m venv .venv
RUN .venv/bin/pip3 install --no-cache-dir -r requirements.txt

# setup desktop env & app
COPY --chown=$USERNAME:$USERNAME infra/docker/legacy-use-target/image/proxychains.conf /etc/proxychains.conf
COPY --chown=$USERNAME:$USERNAME infra/docker/legacy-use-target/image/ $HOME

ARG HOST_IP=unknown
ARG HOST_PORT=unknown
ARG REMOTE_USERNAME=unknown
ARG REMOTE_PASSWORD=unknown
ARG REMOTE_CLIENT_TYPE=unknown
ARG REMOTE_VPN_TYPE=unknown
ARG VPN_CONFIG=unknown
ARG VPN_USERNAME=unknown
ARG VPN_PASSWORD=unknown
ARG DISPLAY_NUM=1
ARG HEIGHT=768
ARG WIDTH=1024

ENV DISPLAY_NUM=$DISPLAY_NUM
ENV HEIGHT=$HEIGHT
ENV WIDTH=$WIDTH
ENV VPN_CONFIG=$VPN_CONFIG
ENV VPN_USERNAME=$VPN_USERNAME
ENV VPN_PASSWORD=$VPN_PASSWORD
ENV REMOTE_PASSWORD=$REMOTE_PASSWORD
ENV REMOTE_USERNAME=$REMOTE_USERNAME
ENV REMOTE_CLIENT_TYPE=$REMOTE_CLIENT_TYPE
ENV REMOTE_VPN_TYPE=$REMOTE_VPN_TYPE
ENV HOST_PORT=$HOST_PORT
ENV HOST_IP=$HOST_IP

ENTRYPOINT [ "./entrypoint.sh" ]
