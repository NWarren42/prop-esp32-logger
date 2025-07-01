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

def _createSSDPSocket(multicast_address: str = MULTICAST_ADDRESS, port: int = PORT) -> socket.socket:
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

    if not lines or len(lines[0].split(" ", 2)) < 3:
        raise ValueError("Malformed SSDP message: missing request line parts")

    method, _uri, _version = lines[0].split(" ", 2) # Looking for "M-SEARCH * HTTP/1.1" or similar

    headers = {}
    for line in lines[1:]:
        if not line:
            break

        if ": " not in line:
            continue

        name, val = line.split(":", 1)
        headers[name.lower().strip()] = val.strip()

    return method, headers

async def waitForDiscovery() -> None:
    r"""Continuously listens for SSDP M-SEARCH messages on the provided socket and respond to them.

    The expected message format is as follows:
        "M-SEARCH * HTTP/1.1\r\n"
        f"HOST: {MULTICAST_ADDRESS}:{MULTICAST_PORT}\r\n"
        'MAN: "ssdp:discover"\r\n'
        "MX: 2\r\n"                         # Maximum wait time in seconds
        "ST: urn:qretprop:espdevice:1\r\n"     # Search target - custom for your devices
        "USER-AGENT: QRET/1.0\r\n"          # Identify your application
        "\r\n"

    """

    listenerSock = _createSSDPSocket()  # Create the SSDP socket if not already created

    while True:
        try:
            data, address = listenerSock.recvfrom(1024) # Non-blocking only if the socket is set to non-blocking mode
            message = data.decode("utf-8")

            isValidMessage = all(required in message for required in [
                'MAN: "ssdp:discover"',
                "MX: 2",
                "ST: urn:qretprop:espdevice:1",
                "USER-AGENT: QRET/1.0",
                ])

            if isValidMessage:
                print(f"Received valid discovery packet from {address}")

                response = (
                    "HTTP/1.1 200 OK\r\n"                  # Standard HTTP OK response
                    "EXT:\r\n"                             # Required by SSDP spec but empty
                    "SERVER: ESP32/1.0 UPnP/1.0\r\n"       # Identify the device platform/version
                    "ST: urn:qretprop:espdevice:1\r\n"  # Search Target - must match what was searched for
                    "\r\n"                                 # Empty line to end headers
                )

                listenerSock.sendto(response.encode("utf-8"), address)  # Send response back to the sender
                print(f"Sent SSDP response to {address[0]}:{address[1]}")

        except OSError:
            # EAGAIN is raised when no data is available to read from the socket, just ignore this.
            await asyncio.sleep(0.1)
        except Exception as e:
            print(f"SSDPTools waitForDiscovery error: {e}")
            await asyncio.sleep(0.1)
