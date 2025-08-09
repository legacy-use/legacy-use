"""
Docker container management utilities for session management.
"""

import json
import logging
import subprocess
import time
from typing import Dict, Optional, Tuple

import httpx
import base64

def _discover_current_network() -> Optional[str]:
    """Discover the current docker network name to attach spawned containers to.

    Returns the first non-bridge network name of the running backend container if available.
    """
    try:
        result = subprocess.run(
            [
                'docker',
                'inspect',
                'legacy-use-backend',
                '--format',
                '{{range $net, $conf := .NetworkSettings.Networks}}{{$net}}{{end}}',
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        current_networks = result.stdout.strip().split()
        for network in current_networks:
            if network != 'bridge':
                return network
    except Exception:
        # Best effort only
        return None
    return None

def _decode_ovpn_config(config_value: Optional[str]) -> Optional[bytes]:
    """Decode the provided vpn_config which may be base64 or plain text.

    Returns bytes content suitable for writing to a file, or None if not provided.
    """
    if not config_value:
        return None
    # Try base64 decode first (frontend may have sent base64)
    try:
        decoded = base64.b64decode(config_value, validate=True)
        # Heuristic: decoded should look like text
        if decoded.strip():
            return decoded
    except Exception:
        pass
    # Fallback: treat as plain text
    return config_value.encode('utf-8')

def _create_volume(name: str) -> bool:
    try:
        subprocess.run(['docker', 'volume', 'create', name], capture_output=True, text=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False

def _remove_volume(name: str) -> None:
    try:
        subprocess.run(['docker', 'volume', 'rm', '-f', name], capture_output=True, text=True, check=True)
    except subprocess.CalledProcessError:
        pass

def _populate_volume_with_ovpn(volume_name: str, file_path_in_volume: str, ovpn_bytes: bytes) -> bool:
    """Populate a docker volume with the provided .ovpn content using a helper container.

    We avoid host bind mounts since this service runs inside a container.
    """
    try:
        helper_cmd = [
            'docker', 'run', '--rm', '-i',
            '-v', f'{volume_name}:/gluetun:rw',
            'alpine:3.20',
            '/bin/sh', '-c',
            # Ensure path exists, set restrictive perms, write from stdin
            f'mkdir -p $(dirname /{file_path_in_volume}) && umask 077 && cat > /{file_path_in_volume}',
        ]
        subprocess.run(helper_cmd, input=ovpn_bytes, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError as e:
        logging.getLogger(__name__).error(f'Failed to populate volume {volume_name}: {e.stderr}')
        return False

def _get_container_name(container_id: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ['docker', 'inspect', '-f', '{{.Name}}', container_id],
            capture_output=True, text=True, check=True
        )
        name = result.stdout.strip()
        if name.startswith('/'):
            name = name[1:]
        return name or None
    except subprocess.CalledProcessError:
        return None

logger = logging.getLogger(__name__)

# Port to use for the computer API inside the container
CONTAINER_PORT = 8088


async def check_target_container_health(container_ip: str) -> dict:
    """
    Check the /health endpoint of a target container.

    Args:
        container_ip: The IP address of the container.
        session_id: The UUID or string ID of the session (optional, for logging).

    Returns:
        A dictionary with keys:
          'healthy': bool (True if health check passed, False otherwise)
          'reason': str (Details about the health status or error)
    """
    health_url = f'http://{container_ip}:8088/health'

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            health_response = await client.get(health_url)

            if health_response.status_code == 200:
                logger.info(f'Health check passed for target {container_ip}')
                return {'healthy': True, 'reason': 'Health check successful.'}
            else:
                reason = f'Target container at {container_ip} failed health check. Status: {health_response.status_code}'
                logger.warning(f'{reason}')
                return {'healthy': False, 'reason': reason}

    except httpx.TimeoutException:
        reason = f'Target container at {container_ip} failed health check: Timeout'
        logger.warning(f'{reason}')
        return {'healthy': False, 'reason': reason}
    except httpx.RequestError as e:
        reason = (
            f'Target container at {container_ip} failed health check: Request Error {e}'
        )
        logger.warning(f'{reason}')
        return {'healthy': False, 'reason': reason}
    except Exception as e:
        reason = f'Unexpected error during health check for {container_ip}: {str(e)}'
        logger.error(f'{reason}')
        return {'healthy': False, 'reason': reason}


def get_container_ip(container_id: str) -> Optional[str]:
    """
    Get the internal IP address of a Docker container.

    Args:
        container_id: ID or name of the container

    Returns:
        IP address as string or None if not found
    """
    try:
        result = subprocess.run(
            [
                'docker',
                'inspect',
                '-f',
                '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}',
                container_id,
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        ip_address = result.stdout.strip()
        if not ip_address:
            logger.error(f'No IP address found for container {container_id}')
            return None

        logger.info(f'Container {container_id} has IP address {ip_address}')
        return ip_address
    except subprocess.CalledProcessError as e:
        logger.error(f'Error getting container IP: {e.stderr}')
        return None
    except Exception as e:
        logger.error(f'Unexpected error getting container IP: {str(e)}')
        return None


def launch_container(
    target_type: str,
    session_id: Optional[str] = None,
    container_params: Optional[Dict[str, str]] = None,
    tenant_schema: Optional[str] = None,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Launch a Docker container for the specified target type.

    Args:
        target_type: Type of target (e.g., 'vnc', 'generic', 'vnc+tailscale')
        session_id: Optional session ID to use in container name
        container_params: Optional dictionary of parameters to pass as environment variables
                          to the container (e.g., HOST_IP, VNC_PASSWORD, TAILSCALE_AUTH_KEY, WIDTH, HEIGHT).
        tenant_schema: Optional tenant schema name to include in container name

    Returns:
        Tuple of (container_id, container_ip) or (None, None) if failed
    """
    try:
        # Construct container name
        if session_id:
            # Docker container names must be valid DNS names, so we'll use a shorter version of the UUID
            # and ensure it follows Docker's naming rules
            short_id = session_id.replace('-', '')[:12]  # First 12 chars without dashes
            if tenant_schema:
                # Include tenant schema in container name for better identification
                container_name = f'legacy-use-{tenant_schema}-session-{short_id}'
            else:
                container_name = f'legacy-use-session-{short_id}'
        else:
            # Use a timestamp-based name if no session ID
            if tenant_schema:
                container_name = (
                    f'legacy-use-{tenant_schema}-session-{int(time.time())}'
                )
            else:
                container_name = f'session-{int(time.time())}'

        if container_params is None:
            container_params = {}

        # Discover custom network (if any) to attach sidecar/app
        network = _discover_current_network()

        # If OpenVPN is requested, run a dedicated VPN sidecar (gluetun) and
        # attach the app container to its network namespace.
        if container_params.get('REMOTE_VPN_TYPE', '').lower() == 'openvpn':
            vpn_name = f'{container_name}-vpn'
            volume_name = f'{container_name}-ovpn'

            ovpn_bytes = _decode_ovpn_config(container_params.get('VPN_CONFIG'))
            if not ovpn_bytes:
                logger.error('OpenVPN selected but no VPN_CONFIG provided')
                return None, None

            # Create and populate docker volume with the .ovpn file
            if not _create_volume(volume_name):
                logger.error(f'Failed to create volume {volume_name}')
                return None, None
            try:
                # Write to /gluetun/openvpn/client.ovpn inside the volume
                if not _populate_volume_with_ovpn(volume_name, 'gluetun/openvpn/client.ovpn', ovpn_bytes):
                    _remove_volume(volume_name)
                    return None, None

                # Build and launch VPN container (gluetun) with kill switch
                vpn_cmd = [
                    'docker', 'run', '-d', '--name', vpn_name,
                    '--cap-drop=ALL', '--cap-add=NET_ADMIN',
                    '--device=/dev/net/tun:/dev/net/tun',
                    '--read-only',
                    '--tmpfs', '/tmp:rw,nosuid,nodev,noexec,size=16m',
                    '--tmpfs', '/run:rw,nosuid,nodev,noexec,size=8m',
                    '-v', f'{volume_name}:/gluetun:ro',
                    '-e', 'VPN_SERVICE_PROVIDER=custom',
                    '-e', 'OPENVPN_CUSTOM_CONFIG=/gluetun/openvpn/client.ovpn',
                    '-e', f'OPENVPN_USER={container_params.get("VPN_USERNAME", "") or ""}',
                    '-e', f'OPENVPN_PASSWORD={container_params.get("VPN_PASSWORD", "") or ""}',
                    '-e', 'FIREWALL_INPUT_PORTS=8088',
                    # Gluetun defaults to killswitch on
                    'qmcgaw/gluetun:latest',
                ]
                if network:
                    vpn_cmd.extend(['--network', network])

                logger.info(f'Launching VPN sidecar with command: {" ".join(vpn_cmd)}')
                vpn_result = subprocess.run(vpn_cmd, capture_output=True, text=True, check=True)
                vpn_container_id = vpn_result.stdout.strip()

                # Build the app container command, attached to the VPN container network namespace
                app_cmd = [
                    'docker', 'run', '-d', '--name', container_name,
                    '--network', f'container:{vpn_name}',
                ]

                # Prepare environment variables for the app container
                # Set REMOTE_VPN_TYPE to direct so the app does not try to manage VPN itself
                target_env = container_params.copy()
                target_env['REMOTE_VPN_TYPE'] = 'direct'
                # Remove any VPN_* secrets from the app container env
                for k in ['VPN_CONFIG', 'VPN_USERNAME', 'VPN_PASSWORD']:
                    target_env.pop(k, None)
                for key, value in target_env.items():
                    if value:
                        app_cmd.extend(['-e', f'{key}={value}'])

                # Image
                app_cmd.append('legacy-use-target:local')
                logger.info(f'Launching app container with command: {" ".join(app_cmd)}')
                app_result = subprocess.run(app_cmd, capture_output=True, text=True, check=True)
                app_container_id = app_result.stdout.strip()

                # Determine IP from the VPN container (since app shares its network namespace)
                container_ip = get_container_ip(vpn_container_id)
                if not container_ip:
                    logger.error(f'Could not get IP address for VPN container {vpn_container_id}')
                    stop_container(app_container_id)
                    # Stop sidecar and remove volume on failure
                    try:
                        subprocess.run(['docker', 'stop', vpn_container_id], capture_output=True, check=True)
                        subprocess.run(['docker', 'rm', vpn_container_id], capture_output=True, check=True)
                    except subprocess.CalledProcessError:
                        pass
                    _remove_volume(volume_name)
                    return None, None

                logger.info(f'Containers launched: app={app_container_id}, vpn={vpn_container_id}, ip={container_ip}')
                return app_container_id, container_ip
            except subprocess.CalledProcessError as e:
                logger.error(f'Error launching VPN/app containers: {e.stderr}')
                _remove_volume(volume_name)
                return None, None

        # Non-OpenVPN path: prepare docker run command for the app container as before
        docker_cmd = [
            'docker', 'run', '-d', '--name', container_name,
        ]
        if network:
            docker_cmd.extend(['--network', network])
            logger.info(f'Connecting target container to network: {network}')

        # Add environment variables from container_params
        for key, value in container_params.items():
            if value:  # Only add if the value is not None or empty
                docker_cmd.extend(['-e', f'{key}={value}'])

        # Add image name
        docker_cmd.append('legacy-use-target:local')
        logger.info(f'Launching docker container with command: {" ".join(docker_cmd)}')

        # Launch container
        result = subprocess.run(docker_cmd, capture_output=True, text=True, check=True)

        container_id = result.stdout.strip()
        logger.info(f'Launched container {container_id} for target type {target_type}')

        # Get container IP address
        container_ip = get_container_ip(container_id)
        if not container_ip:
            logger.error(f'Could not get IP address for container {container_id}')
            stop_container(container_id)
            return None, None

        logger.info(f'Container {container_id} running with IP {container_ip}')

        return container_id, container_ip
    except subprocess.CalledProcessError as e:
        logger.error(f'Error launching container: {e.stderr}')
        return None, None
    except Exception as e:
        logger.error(f'Unexpected error launching container: {str(e)}')
        return None, None


def stop_container(container_id: str) -> bool:
    """
    Stop and remove a Docker container.

    Args:
        container_id: ID or name of the container to stop

    Returns:
        True if successful, False otherwise
    """
    try:
        # Stop main container
        subprocess.run(['docker', 'stop', container_id], capture_output=True, check=True)
        # Identify companion VPN and volume by name convention and stop/cleanup
        container_name = _get_container_name(container_id)
        if container_name:
            vpn_name = f'{container_name}-vpn'
            volume_name = f'{container_name}-ovpn'
            try:
                subprocess.run(['docker', 'stop', vpn_name], capture_output=True, check=True)
            except subprocess.CalledProcessError:
                pass
            try:
                subprocess.run(['docker', 'rm', vpn_name], capture_output=True, check=True)
            except subprocess.CalledProcessError:
                pass
            _remove_volume(volume_name)

        # Remove main container
        subprocess.run(['docker', 'rm', container_id], capture_output=True, check=True)

        logger.info(f'Stopped and removed container {container_id}')
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f'Error stopping container {container_id}: {e.stderr}')
        return False
    except Exception as e:
        logger.error(f'Unexpected error stopping container {container_id}: {str(e)}')
        return False


async def get_container_status(container_id: str, state: str) -> Dict:
    """
    Get status information about a container.

    This function handles all errors internally and never throws exceptions.
    If there is an error, it returns a dictionary with error information.

    Args:
        container_id: ID of the container
        state: Optional state of the session for logging context

    Returns:
        Dictionary with container status information. If there is an error,
        the dictionary will contain an 'error' field with the error message.
    """
    try:
        log_msg = f'Getting status for container {container_id}'
        if state:
            log_msg += f' (session state: {state})'

        # Use debug level for ready containers, info level for initializing
        if state in ['destroying', 'destroyed']:
            return {'id': container_id, 'state': {'Status': 'unavailable'}}
        else:
            logger.info(log_msg)

        result = subprocess.run(
            ['docker', 'inspect', container_id],
            capture_output=True,
            text=True,
            check=True,
        )

        container_info = json.loads(result.stdout)[0]

        # Get basic container status
        status_data = {
            'id': container_id,
            'image': container_info.get('Config', {}).get('Image', 'unknown'),
            'state': container_info.get('State', {}),
            'network_settings': container_info.get('NetworkSettings', {}),
        }

        # Get container IP
        container_ip = get_container_ip(container_id)

        # Check health endpoint if container is running and we have an IP
        if container_ip and True:
            status_data['health'] = await check_target_container_health(container_ip)
            status_data['health']['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')

        # Get load average using docker exec
        try:
            # Execute cat /proc/loadavg in the container to get load average
            load_avg_result = subprocess.run(
                ['docker', 'exec', container_id, 'cat', '/proc/loadavg'],
                capture_output=True,
                text=True,
                check=True,
            )

            # Parse the load average values (first three values are 1min, 5min, 15min)
            load_avg_values = load_avg_result.stdout.strip().split()
            if len(load_avg_values) >= 3:
                status_data['load_average'] = {
                    'load_1': load_avg_values[0],
                    'load_5': load_avg_values[1],
                    'load_15': load_avg_values[2],
                    'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                }

        except Exception as e:
            logger.warning(
                f'Could not get load average for container {container_id}: {str(e)}'
            )
            # Add empty load average data if there's an error
            status_data['load_average'] = {'error': str(e)}

        return status_data
    except subprocess.CalledProcessError as e:
        logger.error(f'Error getting container status: {e.stderr}')
        return {'id': container_id, 'state': {'Status': 'not_found'}}
    except Exception as e:
        logger.error(f'Error getting container status: {str(e)}')
        return {'id': container_id, 'state': {'Status': 'error', 'Error': str(e)}}
