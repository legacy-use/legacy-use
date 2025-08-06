"""
Docker container management utilities for session management.
"""

import json
import logging
import subprocess
import time
from typing import Dict, Optional, Tuple

import httpx

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


def launch_vpn_container(
    session_id: str,
    vpn_config: str,
    vpn_username: str,
    vpn_password: str,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Launch a VPN container using haugene/transmission-openvpn for OpenVPN connections.

    Args:
        session_id: Session ID to use in container name
        vpn_config: Base64 encoded OpenVPN configuration
        vpn_username: VPN username
        vpn_password: VPN password

    Returns:
        Tuple of (container_id, container_ip) or (None, None) if failed
    """
    try:
        # Construct VPN container name
        short_id = session_id.replace('-', '')[:12]
        vpn_container_name = f'legacy-use-vpn-{short_id}'

        # Create a temporary directory for VPN config
        import base64

        # Create persistent volume for VPN config
        config_volume = f'legacy-use-vpn-config-{short_id}'

        # Create docker volume for VPN configuration
        try:
            subprocess.run(
                ['docker', 'volume', 'create', config_volume],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.info(f'Created VPN config volume: {config_volume}')
        except subprocess.CalledProcessError as e:
            logger.error(f'Failed to create VPN config volume: {e.stderr}')
            return None, None

        # Decode and write VPN config to volume using a temporary container
        try:
            decoded_config = base64.b64decode(vpn_config).decode('utf-8')

            # Use a temporary container to write the config to the volume
            temp_container_cmd = [
                'docker',
                'run',
                '--rm',
                '-v',
                f'{config_volume}:/config',
                'alpine:latest',
                'sh',
                '-c',
                f'echo "{decoded_config}" > /config/openvpn.ovpn',
            ]

            subprocess.run(
                temp_container_cmd, capture_output=True, text=True, check=True
            )
            logger.info('VPN config written to volume')

        except Exception as e:
            logger.error(f'Failed to write VPN config: {e}')
            # Clean up volume on failure
            subprocess.run(
                ['docker', 'volume', 'rm', config_volume], capture_output=True
            )
            return None, None

        # Prepare docker run command for VPN container
        docker_cmd = [
            'docker',
            'run',
            '-d',
            '--name',
            vpn_container_name,
            '--cap-add=NET_ADMIN',
            '--device=/dev/net/tun:/dev/net/tun',
            '-e',
            'OPENVPN_PROVIDER=CUSTOM',
            '-e',
            f'OPENVPN_USERNAME={vpn_username}',
            '-e',
            f'OPENVPN_PASSWORD={vpn_password}',
            '-e',
            'OPENVPN_CONFIG=openvpn',
            '-e',
            'LOCAL_NETWORK=172.16.0.0/12,192.168.0.0/16,10.0.0.0/8',
            '-e',
            'TRANSMISSION_WEB_UI=no',  # Disable transmission since we only need VPN
            '-v',
            f'{config_volume}:/etc/openvpn/custom:ro',
            '--log-driver',
            'json-file',
            '--log-opt',
            'max-size=10m',
            'haugene/transmission-openvpn:latest',
        ]

        # Check if we're running inside a docker-compose setup
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

            # Connect VPN container to the same network
            for network in current_networks:
                if network != 'bridge':
                    docker_cmd.extend(['--network', network])
                    logger.info(f'Connecting VPN container to network: {network}')
                    break
        except Exception as e:
            logger.warning(
                f'Could not determine network configuration for VPN container: {e}'
            )

        logger.info(f'Launching VPN container with command: {" ".join(docker_cmd)}')

        # Launch VPN container
        result = subprocess.run(docker_cmd, capture_output=True, text=True, check=True)
        vpn_container_id = result.stdout.strip()

        # Wait for VPN container to be ready (up to 120 seconds for OpenVPN connection)
        logger.info('Waiting for VPN connection to establish...')
        for i in range(120):
            time.sleep(1)
            try:
                # Check if VPN is connected by looking at container logs
                log_result = subprocess.run(
                    ['docker', 'logs', '--tail', '20', vpn_container_id],
                    capture_output=True,
                    text=True,
                    check=True,
                )

                # Look for OpenVPN connection success indicators
                if any(
                    indicator in log_result.stdout
                    for indicator in [
                        'Initialization Sequence Completed',
                        'VPN is up',
                        'OpenVPN tunnel is up',
                        'Tunnel is up and running',
                    ]
                ):
                    logger.info(
                        f'VPN container {vpn_container_id} is ready and connected'
                    )
                    break

                # Check for connection errors
                if any(
                    error in log_result.stdout
                    for error in [
                        'AUTH_FAILED',
                        'Connection failed',
                        'RESOLVE: Cannot resolve host address',
                        'TLS Error',
                    ]
                ):
                    logger.error(f'VPN connection failed: {log_result.stdout}')
                    # Clean up on failure
                    subprocess.run(
                        ['docker', 'rm', '-f', vpn_container_id], capture_output=True
                    )
                    subprocess.run(
                        ['docker', 'volume', 'rm', config_volume], capture_output=True
                    )
                    return None, None

            except Exception:
                continue
        else:
            logger.warning(f'VPN container {vpn_container_id} may not be fully ready')

        # Get VPN container IP
        vpn_container_ip = get_container_ip(vpn_container_id)

        logger.info(
            f'VPN container launched successfully: {vpn_container_id} (IP: {vpn_container_ip})'
        )
        return vpn_container_id, vpn_container_ip

    except subprocess.CalledProcessError as e:
        logger.error(f'Failed to launch VPN container: {e.stderr}')
        # Clean up volume on failure if it was created
        if 'config_volume' in locals():
            try:
                subprocess.run(
                    ['docker', 'volume', 'rm', config_volume], capture_output=True
                )
            except:
                pass
        return None, None
    except Exception as e:
        logger.error(f'Unexpected error launching VPN container: {str(e)}')
        return None, None


def launch_container(
    target_type: str,
    session_id: Optional[str] = None,
    container_params: Optional[Dict[str, str]] = None,
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Launch a Docker container for the specified target type.

    Args:
        target_type: Type of target (e.g., 'vnc', 'generic', 'vnc+tailscale')
        session_id: Optional session ID to use in container name
        container_params: Optional dictionary of parameters to pass as environment variables
                          to the container (e.g., HOST_IP, VNC_PASSWORD, TAILSCALE_AUTH_KEY, WIDTH, HEIGHT).

    Returns:
        Tuple of (container_id, container_ip, vpn_container_id) or (None, None, None) if failed
    """
    try:
        # Construct container name
        if session_id:
            # Docker container names must be valid DNS names, so we'll use a shorter version of the UUID
            # and ensure it follows Docker's naming rules
            short_id = session_id.replace('-', '')[:12]  # First 12 chars without dashes
            container_name = f'legacy-use-session-{short_id}'
        else:
            # Use a timestamp-based name if no session ID
            container_name = f'session-{int(time.time())}'

        if container_params is None:
            container_params = {}

        # Prepare docker run command
        docker_cmd = [
            'docker',
            'run',
            '-d',  # Run in detached mode
            '--name',
            container_name,  # Name container based on session ID
        ]

        # Check if we're running inside a docker-compose setup
        # by checking if we're connected to a custom network
        # and if so, extend the docker_cmd with the network name
        import subprocess

        try:
            # Get current container's network info
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

            # If we're on a custom network (not just 'bridge'), join the target container to it
            for network in current_networks:
                if network != 'bridge':
                    docker_cmd.extend(['--network', network])
                    logger.info(f'Connecting target container to network: {network}')
                    break
        except Exception as e:
            logger.warning(
                f'Could not determine network configuration, using default: {e}'
            )

        # Handle VPN configuration - launch separate VPN container for OpenVPN
        vpn_container_id = None
        if container_params.get('REMOTE_VPN_TYPE', '').lower() == 'openvpn':
            vpn_config = container_params.get('VPN_CONFIG')
            vpn_username = container_params.get('VPN_USERNAME')
            vpn_password = container_params.get('VPN_PASSWORD')

            if vpn_config and vpn_username and vpn_password and session_id:
                logger.info('Launching separate VPN container for OpenVPN')
                vpn_container_id, _ = launch_vpn_container(
                    session_id, vpn_config, vpn_username, vpn_password
                )

                if vpn_container_id:
                    # Use VPN container's network for target container
                    docker_cmd.extend(['--network', f'container:{vpn_container_id}'])
                    logger.info(
                        f'Target container will use VPN container network: {vpn_container_id}'
                    )
                else:
                    logger.error(
                        'Failed to launch VPN container, falling back to direct connection'
                    )
            else:
                logger.warning(
                    'OpenVPN type specified but missing VPN configuration, using direct connection'
                )

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
            # Clean up VPN container if it was created
            if vpn_container_id and session_id:
                stop_vpn_container(vpn_container_id, session_id)
            return None, None, None

        logger.info(f'Container {container_id} running with IP {container_ip}')

        return container_id, container_ip, vpn_container_id
    except subprocess.CalledProcessError as e:
        logger.error(f'Error launching container: {e.stderr}')
        # Clean up VPN container if it was created
        if vpn_container_id and session_id:
            stop_vpn_container(vpn_container_id, session_id)
        return None, None, None
    except Exception as e:
        logger.error(f'Unexpected error launching container: {str(e)}')
        # Clean up VPN container if it was created
        if vpn_container_id and session_id:
            stop_vpn_container(vpn_container_id, session_id)
        return None, None, None


def stop_vpn_container(vpn_container_id: str, session_id: str) -> bool:
    """
    Stop and remove a VPN container and its associated volume.

    Args:
        vpn_container_id: ID of the VPN container to stop
        session_id: Session ID to determine volume name

    Returns:
        True if successful, False otherwise
    """
    try:
        short_id = session_id.replace('-', '')[:12]
        config_volume = f'legacy-use-vpn-config-{short_id}'

        # Stop and remove VPN container
        subprocess.run(
            ['docker', 'stop', vpn_container_id], capture_output=True, check=True
        )
        subprocess.run(
            ['docker', 'rm', vpn_container_id], capture_output=True, check=True
        )

        # Remove the config volume
        subprocess.run(['docker', 'volume', 'rm', config_volume], capture_output=True)

        logger.info(
            f'VPN container {vpn_container_id} and volume {config_volume} removed'
        )
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f'Error stopping VPN container {vpn_container_id}: {e.stderr}')
        return False
    except Exception as e:
        logger.error(
            f'Unexpected error stopping VPN container {vpn_container_id}: {str(e)}'
        )
        return False


def stop_container(container_id: str) -> bool:
    """
    Stop and remove a Docker container.

    Args:
        container_id: ID or name of the container to stop

    Returns:
        True if successful, False otherwise
    """
    try:
        # Stop container
        subprocess.run(
            ['docker', 'stop', container_id], capture_output=True, check=True
        )

        # Remove container
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
