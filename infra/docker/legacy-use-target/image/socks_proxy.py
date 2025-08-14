#!/usr/bin/env python3

import logging
import select
import socket
import struct
import sys
import threading

logging.basicConfig(
    level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s'
)


def handle_client(client_socket):
    try:
        # SOCKS5 handshake
        data = client_socket.recv(1024)
        if data[0:1] != b'\x05':
            logging.warning('Invalid SOCKS version')
            client_socket.close()
            return

        # Send auth method (no auth)
        client_socket.send(b'\x05\x00')

        # Get connection request
        data = client_socket.recv(1024)
        if data[0:1] != b'\x05' or data[1:2] != b'\x01':
            logging.warning('Invalid SOCKS request')
            client_socket.close()
            return

        # Extract target address and port
        addr_type = data[3:4]
        if addr_type == b'\x01':  # IPv4
            addr = socket.inet_ntoa(data[4:8])
            port = struct.unpack('>H', data[8:10])[0]
        elif addr_type == b'\x03':  # Domain name
            domain_len = data[4]
            addr = data[5 : 5 + domain_len].decode()
            port = struct.unpack('>H', data[5 + domain_len : 7 + domain_len])[0]
        else:
            logging.warning(f'Unsupported address type: {addr_type}')
            client_socket.close()
            return

        logging.info(f'Connecting to {addr}:{port}')

        # Create connection through tun0 interface (simplified routing)
        target_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        target_socket.connect((addr, port))

        # Send success response
        client_socket.send(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')

        # Relay data
        while True:
            ready = select.select([client_socket, target_socket], [], [], 1.0)
            if client_socket in ready[0]:
                data = client_socket.recv(4096)
                if not data:
                    break
                target_socket.send(data)
            if target_socket in ready[0]:
                data = target_socket.recv(4096)
                if not data:
                    break
                client_socket.send(data)
    except Exception as e:
        logging.error(f'Error handling client: {e}')
    finally:
        client_socket.close()
        try:
            target_socket.close()
        except Exception:
            pass


def main():
    try:
        # Get port from command line or use default
        port = int(sys.argv[1]) if len(sys.argv) > 1 else 1080

        # Start SOCKS5 server
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', port))
        server.listen(5)

        logging.info(f'SOCKS5 proxy server started on 127.0.0.1:{port}')

        while True:
            client, addr = server.accept()
            logging.info(f'Accepted connection from {addr}')
            client_thread = threading.Thread(target=handle_client, args=(client,))
            client_thread.daemon = True
            client_thread.start()

    except KeyboardInterrupt:
        logging.info('Server shutting down')
        server.close()
    except Exception as e:
        logging.error(f'Server error: {e}')
        sys.exit(1)


if __name__ == '__main__':
    main()
