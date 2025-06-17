import socket

import uasyncio as asyncio  # type: ignore


TCP_PORT = 50000  # Standard TCP port for ESP32 devices

def createTCPSocket() -> socket.socket:
    """Create a TCP socket and bind it to the TCP port."""
    tcpSocket = socket.socket(socket.AF_INET,       # IPv4 socket
                              socket.SOCK_STREAM)   # TCP socket
    tcpSocket.setsockopt(socket.SOL_SOCKET,     # Socket level
                         socket.SO_REUSEADDR,   # Reuseable option
                         1)                     # Set to true
    tcpSocket.bind(("", TCP_PORT))  # Bind to all interfaces on the standard TCP port for ESP32 devices
    return tcpSocket

async def waitForCommand(serverSock: socket.socket) -> str:
    """Wait for a command to come in on the TCP socket and yields the command as a string."""
    loop = asyncio.get_event_loop() # get_running_loop() is not available in micropython so we use get_event_loop()

    try:
        data = await loop.sock_recv(serverSock, 1024)  # Receive up to 1024 bytes
        return data.decode("utf-8").strip()  # Decode bytes to string and strip whitespace
    except Exception as e:
        print(f"Error in waitForCommand: {e}")
        return ""
