"""
Default ports configuration for different target types.
"""

DEFAULT_PORTS = {
    'vnc': 5900,
    'vnc+tailscale': 5900,
    'rdp': 3389,
    'rdp_wireguard': 3389,
    'rdp+tailscale': 3389,
    'vnc+wireguard': 5900,
    'teamviewer': 5938,
    'generic': 8080,
    'rdp+openvpn': 3389,
}
