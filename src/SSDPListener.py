import socket
import struct

import ujson  # type: ignore # This is the micropython JSON library


def inet_aton(ip: str) -> bytes: return struct.pack("BBBB", *[int(x) for x in ip.split(".")])

class SSDPListener:
    """A class to create an SSDP listener socket."""

    def __init__(self,
                 onDiscovery,  # noqa: ANN001 # Callback not typed due to micropython limitations
                 ):
        self.multicastAddress = "239.255.255.250"
        self.port = 1900
        self.ssdpSocket = self._createSSDPSocket()

        self.onDiscovery = onDiscovery  # Callback function that


    def HandleSSDPMessage(self, data: bytes, address: str, sock: socket.socket) -> None:
        """Handle incoming SSDP messages.

        Respond to M-SEARCH requests by sending the config
        directly to the sender's address and port via UDP unicast.
        :param data: The received UDP datagram.
        :param address: The (ip, port) tuple of the sender.
        :param activeServerPort: The port your main server is running on.
        """
        message = data.decode("utf-8")

        method, headers = self._parseMSearch(message)  # Parse the M-SEARCH message, but we don't use the result here

        isMSearch = method == "M-SEARCH"

        if isMSearch: # First check if the message is an M-SEARCH request
            # Now that we know it will have M-SEARCH headers, we can check for the specific headers we care about
            isDiscover      = headers["man"]    == '"ssdp:discover"'
            isForPropESP32  = headers.get("st") == "urn:qretprop:service:espdevice:1"

            if isDiscover and isForPropESP32:
                print(f"Received M-SEARCH from {address}:\n{message}")
                self.onDiscovery(sock) # The callback function needs only the socket to send the response back to the client.

    def _createSSDPSocket(self) -> socket.socket:
        """Create and return a UDP socket bound to the SSDP multicast group."""
        sock: socket.socket = socket.socket(socket.AF_INET,
                           socket.SOCK_DGRAM,
                           socket.IPPROTO_UDP)

        sock.setsockopt(socket.SOL_SOCKET,   # SOL_SOCKET is the socket level for options
                        socket.SO_REUSEADDR, # SO_REUSEADDR allows the socket to be bound to an address that is already in use
                        1,                   # Set the option value to 1 (true)
                        )

        sock.bind(("0.0.0.0", self.port))

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

    def _parseMSearch(self, searchMessage: str) -> (str, dict): # type: ignore
        """Parse the M-SEARCH message and return a dictionary of parameters."""
        lines = searchMessage.split("\r\n")
        method, _uri, _version = lines[0].split(" ", 2) # First line is formatted as <"M-SEARCH * HTTP/1.1">
        headers = {}
        for line in lines[1:]:
            if not line:
                break
            name, val = line.split(":", 1)
            headers[name.lower().strip()] = val.strip()
        return method, headers


