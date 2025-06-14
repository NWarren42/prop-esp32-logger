import select  # noqa: INP001 -- Implicit namespace doesn't matter here
import socket  # noqa: TCH003 -- Typing not a library within micropython, cant put into a typed block

import ujson  # type:ignore # ujson and machine are micropython libraries

from sensors.LoadCell import LoadCell  # type: ignore
from sensors.PressureTransducer import PressureTransducer  # type: ignore
from sensors.Thermocouple import Thermocouple  # type: ignore # don't need __init__ for micropython
from SSDPListener import SSDPListener
from TCPHandler import TCPHandler
from UDPListener import UDPListener


class AsyncManager:
    def __init__(self,
                 configDict: dict) -> None:

        self.sensors = self.setupDeviceFromConfig(configDict)  # Initialize sensors from the config file

        self.udpListener    = UDPListener()
        self.tcpListener    = TCPHandler(self.sensors) # SENSORS SHOULD NOT BE AN ARGUMENT TO THE TCP HANDLER. FIX LATER WITH A DATA COLLECTION CLASS
        self.ssdpListener   = SSDPListener(self._onSSDPDiscovery)  # Pass the discovery callback to the SSDPListener

        self.configDict = configDict
        self.running = False

        self.tcpAddressDict = {}  # Stores socket:address KVPs for TCP connections

        # Generating list of sockets to pass to select
        self.inputs: list[socket.socket] = [self.udpListener.udpSocket,
                                            self.tcpListener.tcpSocket,
                                            self.ssdpListener.ssdpSocket]
        self.outputs: list[socket.socket] = []  # Unused on startup, but used for establishing streaming sockets


    def run(self) -> None:
        print("Server is running...")
        self.running = True
        try:
            while self.running:
                # Monitor sockets for if they become readable
                readable, writeable, _ = select.select(self.inputs, self.outputs, [])
                for sock in readable:
                    # If a UDP message is received, handle it in the UDPListener
                    if sock == self.udpListener.udpSocket:
                        data, address = sock.recvfrom(1024)
                        print(f"Received UDP message: {data.decode('utf-8')} from {address}")
                        # Handle all UDP messages in the UDPListener.
                        self.udpListener.handleMessage(data, address, self.tcpListener.port) # Pass data to the listener

                    # If a message comes in on the TCP listener, accept it and add it to a list of sockets to monitor
                    elif sock == self.tcpListener.tcpSocket:
                        clientSocket, clientAddress = sock.accept() # Generate communication socket between listener and client
                        print(f"New TCP connection from {clientAddress}. Socket assigned and added to monitoring list.")
                        self.inputs.append(clientSocket) # Add socket to the list of sockets to monitor

                        self.tcpAddressDict[clientSocket] = clientAddress

                        # self.sendConfig(clientSocket, self.configDict)
                        # print(f"Sent config file to {clientAddress}.")

                    # This is the UDP Multicast SSDP socket, so we handle all SSDP search requests here.
                    elif sock == self.ssdpListener.ssdpSocket:
                        data, address = sock.recvfrom(1024)
                        self.ssdpListener.HandleSSDPMessage(data, address, sock)

                    # If the message comes in on a socket that is not the listener, it must be an established client socket so we
                    # pass any messages onto the handler with the socket information so that it can respond with the desired data.
                    else:
                        sockAddress = self.tcpAddressDict[sock] # Get the address of the socket
                        status, cmd = self.tcpListener.handleMessage(sock, sockAddress) # If a message comes in on a socket that is not the listener, pass it to the handler

                        if cmd == "STRM": # If the command is STRM, the device is "subscribing" to a data strean and we add it to the writeable list
                            self.outputs.append(sock)
                            print(f"Streaming data to {sockAddress}.")

                        elif cmd == "STOP": # If the command is STOP, remove the socket from the list of sockets to monitor for streaming
                            if sock in self.outputs:
                                self.outputs.remove(sock)
                                print(f"Stopped streaming data to {sockAddress}.")
                            else:
                                print(f"Socket {sockAddress} not in streaming list.")

                        if not status: # If the handler raises an error, close the connection and remove all trace of the socket
                            print(f"Connection closed by {sockAddress}.")
                            self.inputs.remove(sock)
                            sock.close()
                            self.tcpAddressDict.pop(sock)

                for sock in writeable: # If the socket is in streaming mode, try to write to it
                    try:
                        streamPacket = self.tcpListener.getStreamPacket() # Get the stream packet from the TCPHandler
                        sock.sendall(streamPacket) # Send the stream packet to the client
                    except Exception as e:
                        print(f"Error sending stream packet to {self.tcpAddressDict[sock]}: {e}")

        except KeyboardInterrupt:
            if self.running:
                print("\nStopping Server...")
                self.stop()
            else: # If the server is already stopped
                print("Server already stopped.")

    def setupDeviceFromConfig(self, config) -> list[Thermocouple | LoadCell | PressureTransducer]: # type: ignore  # noqa: ANN001 # Typing for the JSON object is impossible without the full Typing library
        """Initialize all devices and sensors from the config file.

        ADC index 0 indicates the sensor is connected directly to the ESP32. Any other index indicates
        connection to an external ADC.
        """
        sensors: list[Thermocouple | LoadCell | PressureTransducer] = []

        print(f"Initializing device: {config.get('deviceName', 'Unknown Device')}")
        deviceType = config.get("deviceType", "Unknown")

        if deviceType == "Sensor Monitor": # Sensor monitor is what I'm calling an ESP32 that reads sensors
            sensorInfo = config.get("sensorInfo", {})

            for name, details in sensorInfo.get("thermocouples", {}).items():
                sensors.append(Thermocouple(name=name,
                                            ADCIndex=details["ADCIndex"],
                                            highPin=details["highPin"],
                                            lowPin=details["lowPin"],
                                            thermoType=details["type"],
                                            units=details["units"],
                                            ))

            for name, details in sensorInfo.get("pressureTransducers", {}).items():
                sensors.append(PressureTransducer(name=name,
                                                ADCIndex=details["ADCIndex"],
                                                pinNumber=details["pin"],
                                                maxPressure_PSI=details["maxPressure_PSI"],
                                                units=details["units"],
                                                ))

            for name, details in sensorInfo.get("loadCells", {}).items():
                sensors.append(LoadCell(name=name,
                                        ADCIndex=details["ADCIndex"],
                                        highPin=details["highPin"],
                                        lowPin=details["lowPin"],
                                        loadRating_N=details["loadRating_N"],
                                        excitation_V=details["excitation_V"],
                                        sensitivity_vV=details["sensitivity_vV"],
                                        units=details["units"],
                                        ))

            return sensors

        if deviceType == "Unknown":
            raise ValueError("Device type not specified in config file")

        return []


    def sendConfig(self, socket: socket.socket, config: dict) -> None:
        """Send the configuration file to the client."""
        try:
                # Convert the config file to a JSON string so it can have the encode method called on it
                jStringConfig = ujson.dumps(config)
                confString = "CONF" + jStringConfig + "\n" # Add a header to the config file so the client knows what it is receiving

                # Currently TCP block size is 1024 bytes, this can be changed if needed but config files are small right now.
                # This is meant as a warning block of code if we start having larger config files.
                if len(confString) > 1024:
                    raise    ValueError("ERROR: Config file too large to send in one TCP block!!.")


                socket.send(confString.encode("utf-8"))
                print(f"Sent conf string: {confString}")

        except Exception as e:
            print(f"Error sending config file: {e}")

    def _onSSDPDiscovery(self, sock: socket.socket) -> None:
        """Handle SSDP discovery events.

        This function is a wrapper for the SSDPListener's discovery event. This avoids having to pass the config through
        to the SSDPListener and allows the AsyncManager to handle the event directly.
        """
        print("SSDP discovery event triggered. Sending config file to the sender.")
        self.sendConfig(sock, self.configDict)

    def stop(self) -> None:
        print("Cleaning up sockets...")
        for sock in self.inputs: # Close all sockets that are currently in the select read list.
            try:
                sock.close()
            except Exception as e:
                print(f"Error closing socket: {e}")
        print("Server stopped.")
