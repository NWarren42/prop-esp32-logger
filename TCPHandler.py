import errno # need to import errno for OSError handling
import socket  # noqa: INP001 -- Implicit namespace doesn't matter for ESP32 filesystem


class TCPHandler:
    """A class to listen for incoming TCP messages on a specified port.

    Attributes
    ----------
        port (int): The port to listen on.
        tcpSocket (socket.socket): The socket object that is currently open for a new connection

    Methods
    -------
        handleMessage(clientSocket: socket.socket) -> None:
            Handles incoming TCP messages. This method should be overridden by the user to handle
            incoming messages.

        getSocket() -> socket.socket:
            Returns the socket object for the listener.

    Usage
    -----
    The TCPListener class handles all TCP requests, connection or command. There is only ever one
    socket available to connect to (the listener socket). When a connection is made, a new socket is
    created and assigned to be the new listener socket. This allows for multiple connections to be
    made to the ESP32 over TCP. The TCPHandler can process any incoming message to a socket

    """
    def __init__(self, sensors, port: int) -> None:
        self.sensors = sensors
        self.port = port

        self.tcpSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcpSocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1) # Allow rebinding to the same port
        self.tcpSocket.bind(("", self.port))
        self.tcpSocket.listen(1)  # Allow only 1 connection backlog
        print(f"TCP Listener initialized on port {self.port}")

    def getStreamPacket(self) -> list:
        readings = []
        for sensor in self.sensors:
            # Take a reading from each sensor and append it to the readings list
            sensorData = sensor.takeData('V')  # The sensor object handles the conversion. The only argument is the unit you want back.
            sensor.data.append(sensorData)  # Add the collected data to the sensor's internal data list.
            readings.append(sensorData)  # Append the data to the list to send back to the client

        # Generate the stream packet
        packet = "DATA" + f"{readings}".strip("[]") + "\n"  # Convert the list to a string for sending. We need to strip the brackets off the list so that it is a comma separated string.
        return packet.encode("utf-8")  # Return the packet as a byte string

    def handleMessage(self, clientSocket: socket.socket, clientAddress: str) -> tuple[bool, str | None]:
        """Handle incoming TCP messages. Return False if there is an error handling data."""

        try:
            cmd = clientSocket.recv(1024).decode("utf-8")
            if not cmd:
                print("Connection closed by client")
                return False, None

            # TCP Opcode handling is here.
            print(f"Received TCP message: {cmd} from {clientAddress}")

            # GETS is a command to get a single reading from each of the sensors
            if cmd == "GETS":
                allData = []
                print(self.sensors) # Debugging line to see in what order the sensors are being read
                for sensor in self.sensors:
                    # ONLY READING VOLTAGE FOR NOW WHILE NO DEVICES CONNECTED
                    sensorData = sensor.takeData('V') # The sensor object handles the conversion. The only argument is the unit you want back.
                    sensor.data.append(sensorData)  # Add the collected data to the sensor's internal data list.
                    print(f"Sensor {sensor.name} data: {sensorData} V") # Print the data for debugging FIXED IN VOLTS
                    allData.append(sensorData)  # Append the data to the list to send back to the client
                response = "DATA" + f"{allData}".strip("[]") + "\n" # Convert the list to a string for sending. We need to strip the brackets off the list so that it is a comma separated string.
                clientSocket.sendall(response.encode("utf-8"))  # Send the data back to the client

            # STRM is a command to start streaming data from the sensors
            if cmd == "STRM":
                return True, cmd  # Return True to indicate that the socket should be added to the list of sockets to monitor for streaming


        except OSError as e: # Handle any OSErrors. Micropython is different than Cpython and error codes need to be imported
            if e.args[0] == errno.ECONNRESET:  # Handle connection reset error
                print(f"Client {clientAddress} closed the connection: ECONNRESET")
            else:
                print(f"Unexpected OSError from {clientAddress}: {e}")
            return False, None

        except Exception as e:
            print(f"Error handling TCP client: {e}")
            return False, None

        return True, cmd # Return True if the message was handled successfully, and the command that was received for socket management by the AsyncManager

