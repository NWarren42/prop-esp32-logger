import socket
import struct

import uasyncio as asyncio  # type: ignore


MULTICAST_ADDRESS = "239.255.255.250"
PORT = 1900

def _inet_aton(ip: str) -> bytes:
    """Convert an IPv4 address from string format to packed binary format.

    This function is a clone of the inet_aton function from the socket module, which is not available in the micropython
    socket module.

    """
    return struct.pack("BBBB", *[int(x) for x in ip.split(".")])

def createSSDPSocket(multicast_address: str = MULTICAST_ADDRESS, port: int = PORT) -> socket.socket:
    sock = socket.socket(socket.AF_INET,        # create a socket using IPv4
                         socket.SOCK_DGRAM,     # create a UDP socket
                         socket.IPPROTO_UDP)    # use UDP protocol

    sock.setsockopt(socket.SOL_SOCKET,      # set socket options at the socket level
                    socket.SO_REUSEADDR,    # allow reuse of the address
                    1)                      # enable the option

    sock.setblocking(False)  # set the socket to non-blocking mode. Throws error if no data is available instead of blocking

    sock.bind(("0.0.0.0", port))

    # Join the multicast group with this socket
    membershipRequest = struct.pack(
        "4s4s",
        _inet_aton(multicast_address),
        _inet_aton("0.0.0.0"),
    )
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, membershipRequest)
    sock.setblocking(False)
    return sock

def _parseSSDPMessage(search_message: str) -> tuple[str, dict[str, str]]:
    lines = search_message.split("\r\n")
    method, _uri, _version = lines[0].split(" ", 2)
    headers = {}
    for line in lines[1:]:
        if not line:
            break
        name, val = line.split(":", 1)
        headers[name.lower().strip()] = val.strip()
    return method, headers

async def waitForDiscovery(sock: socket.socket) -> str:
    """Wait for a valid SSDP discovery message and return the sender's ip address."""
    loop = asyncio.get_event_loop() # get_running_loop() is not available in micropython so we use get_event_loop()

    while True:
        try:
            data, address = sock.recvfrom(1024) # Non-blocking only if the socket is set to non-blocking mode
            message = data.decode("utf-8")
            method, headers = _parseSSDPMessage(message)

            isMSearch       = method == "M-SEARCH"
            isDiscover      = headers.get("man") == '"ssdp:discover"'
            isForPropESP32  = headers.get("st") == "urn:qretprop:service:espdevice:1"

            if isMSearch and isDiscover and isForPropESP32:
                print(f"Received valid M-SEARCH from {address}:\n{message}")
                return address[0]  # Return the sender's IP address
        except OSError:
            # EAGAIN is raised when no data is available to read from the socket, just ignore this.
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"SSDPTools waitForDiscovery error: {e}")
            await asyncio.sleep(0.1)
