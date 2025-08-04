import socket

import uasyncio as asyncio  # type: ignore


TCP_PORT = 50000  # Standard TCP port for ESP32 devices

class ConnectionClosedError(Exception):
    """Raised when the remote peer closes the connection."""
    pass


def createListenerTCPSocket() -> socket.socket:
    """Create a TCP socket and bind it to the TCP port."""
    tcpSocket = socket.socket(socket.AF_INET,       # IPv4 socket
                              socket.SOCK_STREAM)   # TCP socket
    tcpSocket.setsockopt(socket.SOL_SOCKET,     # Socket level
                         socket.SO_REUSEADDR,   # Reuseable option
                         1)                     # Set to true
    tcpSocket.setblocking(False)
    tcpSocket.bind(("", TCP_PORT))  # Bind to all interfaces
    tcpSocket.listen(1)  # Listen for incoming connections
    return tcpSocket

def createClientTCPSocket() -> socket.socket:
    """Create a TCP socket and bind it to the TCP port."""
    tcpSocket = socket.socket(socket.AF_INET,       # IPv4 socket
                              socket.SOCK_STREAM)   # TCP socket
    tcpSocket.setsockopt(socket.SOL_SOCKET,     # Socket level
                         socket.SO_REUSEADDR,   # Reuseable option
                         1)                     # Set to true

    tcpSocket.setblocking(False)

    return tcpSocket

async def waitForConnection(listenerSock: socket.socket) -> tuple[socket.socket, tuple[str, int]]:
    """Wait for a TCP connection and return the client socket and address.

    Returns:
        tuple: (client_socket, address)
            - client_socket: Socket for communication with the connected client
            - address: Tuple of (ip_address, port) of the connected client

    """
    while True:
        try:
            # Accept returns (client_socket, address)
            # where address is (ip, port)
            client_socket, address = listenerSock.accept()
            print(f"Connection accepted from {address[0]}:{address[1]}")

            # Set client socket to non-blocking for async operations
            client_socket.setblocking(False)

            return client_socket, address

        except OSError:
            # EAGAIN is raised when no data is available
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"TCPTools waitForConnection error: {e}")
            await asyncio.sleep(0.1)



async def waitForCommand(serverSock: socket.socket) -> str:
    """Wait for a command to come in on the TCP socket and yields the command as a string."""
    while True:
        try:
            data = serverSock.recv(1024)
            if not data:  # Socket was closed by peer
                serverSock.close()
                raise ConnectionClosedError("Connection closed by peer")
            return data.decode("utf-8").strip()

        except OSError:
            # No data available yet, yield to other tasks
            await asyncio.sleep(0.1)
        except Exception as e:
            if not isinstance(e, ConnectionClosedError):
                print(f"Error in waitForCommand: {e}")
            raise
