"""
Docker container management utilities for session management.
"""

import logging
import time
from subprocess import CalledProcessError
from typing import Dict, Optional, Tuple

import docker as docker_sdk
import httpx

docker = docker_sdk.from_env()

logger = logging.getLogger(__name__)


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
    container = docker.containers.get(container_id)
    networks = container.attrs['NetworkSettings']['Networks']
    for network in networks.values():
        ip_address = network['IPAddress']
        if ip_address:
            logger.info(f'Container {container_id} has IP address {ip_address}')
            return ip_address
    logger.error(f'Could not get IP address for container {container_id}')
    return None


def get_docker_network_mode() -> Optional[str]:
    """Check if we are running in docker and get network info."""
    import re

    # Find container by regex pattern - handles both legacy-use-backend and app-backend-\d+
    try:
        containers = docker.containers.list()
        for container in containers:
            if re.search(r'(legacy-use-backend|app-backend-\d+)', container.name):
                networks = container.attrs['NetworkSettings']['Networks']
                for network_name in networks.keys():
                    if network_name != 'bridge':
                        logger.info(
                            f'Found backend container {container.name}, connecting target container to network: {network_name}'
                        )
                        return network_name
    except Exception as e:
        logger.warning(f'Could not determine network configuration, using default: {e}')

    return None


def launch_container(
    target_type: str,
    session_id: Optional[str] = None,
    container_params: Optional[Dict[str, str]] = None,
    tenant_schema: str = 'default',
) -> Tuple[Optional[str], Optional[str]]:
    """
    Launch a Docker container for the specified target type.

    Args:
        target_type: Type of target (e.g., 'vnc', 'generic', 'vnc+tailscale')
        session_id: Optional session ID to use in container name
        container_params: Optional dictionary of parameters to pass as environment variables
                          to the container (e.g., HOST_IP, VNC_PASSWORD, TAILSCALE_AUTH_KEY, WIDTH, HEIGHT).
        tenant_schema: Optional tenant schema name to include in container name, fallback to 'default'

    Returns:
        Tuple of (container_id, container_ip) or (None, None) if failed
    """
    # Construct container name
    timestamp = int(time.time())
    identifier = session_id.replace('-', '')[:12] if session_id else timestamp
    container_name = f'legacy-use-session-{tenant_schema}-{identifier}'

    if container_params is None:
        container_params = {}

    # Check if we're running inside a docker-compose setup
    # by checking if we're connected to a custom network
    # and if so, extend the docker_cmd with the network name
    network_mode = get_docker_network_mode()

    try:
        devices = []
        cap_add = []
        # add options for openvpn
        if container_params.get('REMOTE_VPN_TYPE', '').lower() == 'openvpn':
            cap_add.append('NET_ADMIN')  # Required for VPN/TUN interface management
            cap_add.append('NET_RAW')  # Required for network interface configuration
            devices.append('/dev/net/tun:/dev/net/tun')  # Required for VPN tunneling

        logger.info(f'Launching docker container {container_name}')

        container = docker.containers.run(
            'legacy-use-target:local',
            name=container_name,
            detach=True,
            network=network_mode,
            environment=container_params,
            devices=devices,
            cap_add=cap_add,
        )

        if not container or not container.id:
            logger.error(f'Failed to launch container {container_name}')
            return None, None

        logger.info(f'Launched container {container.id} for target type {target_type}')

        # Get container IP address
        container_ip = get_container_ip(container.id)
        if not container_ip:
            stop_container(container.id)
            return None, None

        logger.info(f'Container {container.id} running with IP {container_ip}')

        return container.id, container_ip
    except CalledProcessError as e:
        logger.error(f'Error launching container: {e.stderr}')
        return None, None


def stop_container(container_id: str) -> bool:
    """
    Stop and remove a Docker container.

    Args:
        container_id: ID or name of the container to stop

    Returns:
        True if successful, False otherwise
    """
    logger.info(f'Stopping and removing container {container_id}')
    docker.containers.get(container_id).stop(timeout=1)
    docker.containers.get(container_id).remove()
    logger.info(f'Stopped and removed container {container_id}')
    return True


async def get_container_status(container_id: str, session_state: str) -> Dict:
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

    if session_state in ['destroying', 'destroyed']:
        return {'id': container_id, 'state': {'Status': 'unavailable'}}

    logger.info(
        f'Getting status for container {container_id} (session state: {session_state})'
    )

    try:
        container = docker.containers.get(container_id)
    except Exception as e:
        logger.error(f'Container {container_id} not found or unavailable: {str(e)}')
        return {
            'id': container_id,
            'state': {'Status': 'not_found', 'Running': False},
            'error': str(e),
        }

    if not container:
        logger.error(f'Container {container_id} not found')
        return {'id': container_id, 'state': {'Status': 'not_found', 'Running': False}}

    # Status information
    state = container.attrs.get('State', {})
    status_data = {
        'id': container_id,
        'image': container.attrs.get('Config', {}).get('Image', 'unknown'),
        'state': state,
        'network_settings': container.attrs.get('NetworkSettings', {}),
    }

    is_running = state.get('Running', False)

    # Only attempt health checks if running and IP is available
    if is_running:
        try:
            container_ip = get_container_ip(container_id)
        except Exception as e:
            logger.warning(f'Error getting IP for container {container_id}: {str(e)}')
            container_ip = None

        if container_ip:
            status_data['health'] = await check_target_container_health(container_ip)
            status_data['health']['timestamp'] = time.strftime('%Y-%m-%dT%H:%M:%S%z')

        # Get load average using docker exec only if running
        try:
            loadavg = container.exec_run(['cat', '/proc/loadavg'])
            if loadavg.exit_code != 0:
                logger.warning(
                    f'Failed to get load average for {container_id}: {loadavg.output}'
                )
                status_data['load_average'] = {'error': str(loadavg.output)}
            else:
                try:
                    loadavg_values = loadavg.output.strip().split()
                    if len(loadavg_values) >= 3:
                        status_data['load_average'] = {
                            'load_1': loadavg_values[0],
                            'load_5': loadavg_values[1],
                            'load_15': loadavg_values[2],
                            'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                        }
                except Exception as e:
                    logger.warning(
                        f'Could not parse load average for container {container_id}: {str(e)}'
                    )
                    status_data['load_average'] = {'error': str(e)}
        except Exception as e:
            # If the container stopped between checks, don't raise
            logger.warning(
                f'Could not exec into container {container_id} to get load average: {str(e)}'
            )
            status_data.setdefault('load_average', {'error': str(e)})

    return status_data
