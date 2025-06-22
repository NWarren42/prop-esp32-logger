import socket

import uasyncio as asyncio  # type: ignore


TCP_PORT = 50000  # Standard TCP port for ESP32 devices

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
    tcpSocket.bind(("", TCP_PORT))  # Bind to all interfaces
    return tcpSocket

async def waitForConnection(listenerSock: socket.socket) -> str:
    """Wait for a connection on the TCP socket and returns the address the server that sent the search out.

    The device supports both TCP and SSDP discovery and it is assumed that if anything comes in directly to this TCP
    socket it already knows that it is talking to the device and does not need to send a discovery message.

    """
    while True:
        try:
            # Accept a connection and return only the address of the client. The device will reach out to the client
            # directly after this to make a connection.

            _, address = listenerSock.accept()

            print(f"Connection accepted from {address}")

            # This socket is only meant to be used for discovery, so we close it after accepting the connection.
            listenerSock.close()

            return address[0]  # Return only the IP address of the client
        except OSError:
            # EAGAIN is raised when no data is available to read from the socket, just ignore this.
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"TCPTools waitForDiscovery error: {e}")
            await asyncio.sleep(0.1)



async def waitForCommand(serverSock: socket.socket) -> str:
    """Wait for a command to come in on the TCP socket and yields the command as a string."""
    loop = asyncio.get_event_loop() # get_running_loop() is not available in micropython so we use get_event_loop()

    try:
        data = await loop.sock_recv(serverSock, 1024)  # Receive up to 1024 bytes
        return data.decode("utf-8").strip()  # Decode bytes to string and strip whitespace
    except Exception as e:
        print(f"Error in waitForCommand: {e}")
        return ""
