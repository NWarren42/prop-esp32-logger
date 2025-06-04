import socket
import struct

import ujson  # type: ignore # This is the micropython JSON library


def inet_aton(ip: str) -> bytes: return struct.pack("BBBB", *[int(x) for x in ip.split(".")])

class SSDPListener:
    """A class to create an SSDP listener socket."""

    def __init__(self, multicastAddress: str = "239.255.255.250"):
        self.multicastAddress = multicastAddress
        self.port = 1900
        self.ssdpSocket = self._createSSDPSocket()

    def HandleSSDPMessage(self, data: bytes, address: tuple, activeServerPort: int) -> None:
        """Handle incoming SSDP messages.

        Respond to M-SEARCH requests by sending the config
        directly to the sender's address and port via UDP unicast.
        :param data: The received UDP datagram.
        :param address: The (ip, port) tuple of the sender.
        :param activeServerPort: The port your main server is running on.
        """
        message = data.decode("utf-8")

        if message.startswith("M-SEARCH"):
            print(f"Received M-SEARCH from {address}: {message}")

            # Prepare the config response
            jStringConfig = ujson.dumps({"activeServerPort": activeServerPort})
            confString = "CONF" + jStringConfig + "\n"

            # Send the config directly to the sender's address and port via UDP
            self.ssdpSocket.sendto(confString.encode("utf-8"), address)
            print(f"Sent config to {address}")
        else:
            print(f"Received unknown message on SSDP port from {address}: {message}")


    def _createSSDPSocket(self) -> socket.socket:
        """Create and return a UDP socket bound to the SSDP multicast group."""
        sock: socket.socket = socket.socket(socket.AF_INET,
                           socket.SOCK_DGRAM,
                           socket.IPPROTO_UDP)

        sock.setsockopt(socket.SOL_SOCKET,   # SOL_SOCKET is the socket level for options
                        socket.SO_REUSEADDR, # SO_REUSEADDR allows the socket to be bound to an address that is already in use
                        1,                   # Set the option value to 1 (true)
                        )

        sock.bind((self.multicastAddress, self.port))

        # Joining the multicast group
        membershipRequest: bytes = struct.pack(
            "4s4s",                                     # Pack the multicast address and interface address
            inet_aton(self.multicastAddress),           # inet_aton converts the IP address from string to binary format
            inet_aton("0.0.0.0"),                       # ESP32 has only one interface so bind to all for simplicity.
            )

        sock.setsockopt(socket.IPPROTO_IP,          # Specifies option is for IP protocol layer
                        socket.IP_ADD_MEMBERSHIP,   # Join the multicast group
                        membershipRequest,          # The packed membership request containing the multicast address and interface address
                        )


        print(f"SSDP Listener socket initialized on {self.multicastAddress}:{self.port}")
        return sock



