import select  # noqa: INP001 -- Implicit namespace doesn't matter here
import socket  # noqa: TCH003 -- Typing not a library within micropython, cant put into a typed block

import ujson  # type:ignore # ujson and machine are micropython libraries

from SSDPListener import SSDPListener
from TCPHandler import TCPHandler
from UDPListener import UDPListener


class AsyncManager:
    def __init__(self,
                 udpListener: UDPListener,
                 tcpListener: TCPHandler,
                 SSDPListener: SSDPListener,
                 configDict: dict) -> None:

        self.udpListener    = udpListener
        self.tcpListener    = tcpListener
        self.ssdpListener   = SSDPListener

        self.configDict = configDict
        self.running = False

        self.tcpAddressDict = {}  # Stores socket:address KVPs for TCP connections

        # Generating list of sockets to pass to select
        self.inputs: list[socket.socket] = [self.udpListener.udpSocket, self.tcpListener.tcpSocket]
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
                        print(f"New TCP connection from {clientAddress}. Socket assigned to {clientSocket}")
                        self.inputs.append(clientSocket) # Add socket to the list of sockets to monitor

                        # Store the address of the client socket
                        self.tcpAddressDict[clientSocket] = clientAddress

                        # Send the config file to the client
                        self.sendConfig(clientSocket, self.configDict)
                        print(f"Sent config file to {clientAddress}.")

                    # If the message comes in on a socket that is not the listener, it must be an established client socket so we
                    # pass any messages onto the handler with the socket information so that it can respond with the desired data.
                    else:
                        sockAddress = self.tcpAddressDict[sock] # Get the address of the socket
                        status, cmd = self.tcpListener.handleMessage(sock, sockAddress) # If a message comes in on a socket that is not the listener, pass it to the handler

                        if cmd == "STRM": # If the command is STRM, add the socket to the list of sockets to monitor for streaming
                            self.outputs.append(sock) # Add the socket to the list of sockets to monitor for streaming
                            print(f"Streaming data to {sockAddress}.")

                        elif cmd == "STOP": # If the command is STOP, remove the socket from the list of sockets to monitor for streaming
                            if sock in self.outputs: # Check if the socket is in streaming mode
                                self.outputs.remove(sock) # Remove the socket from the list of sockets to monitor for streaming
                                print(f"Stopped streaming data to {sockAddress}.")
                            else: # If the socket is not in streaming mode, do nothing
                                print(f"Socket {sockAddress} not in streaming list.")

                        if not status: # If the handler raises an error close the connection and remove all trace of the socket
                            print(f"Connection closed by {sockAddress}.")
                            self.inputs.remove(sock) # Remove from select read list
                            sock.close() # Close the socket
                            self.tcpAddressDict.pop(sock) # Remove from the address LUT

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

    def sendConfig(self, socket: socket.socket, config: dict) -> None:
        """Send the configuration file to the client."""
        try:
                # Convert the config file to a JSON string so it can have the encode method called on it
                jStringConfig = ujson.dumps(config)
                confString = "CONF" + jStringConfig + "\n" # Add a header to the config file so the client knows what it is receiving

                # Currently TCP block size is 1024 bytes, this can be changed if needed but config files are small right now.
                # This is meant as a warning block of code if we start having larger config files.
                if len(confString) > 1024:
                    raise ValueError("ERROR: Config file too large to send in one TCP block!!.")

                else: socket.send(confString.encode("utf-8")) # Send raw bytes over TCP

        except Exception as e:
            print(f"Error sending config file: {e}")

    def stop(self) -> None:
        print("Cleaning up sockets...")
        for sock in self.inputs: # Close all sockets that are currently in the select read list.
            try:
                sock.close()
            except Exception as e:
                print(f"Error closing socket: {e}")
        print("Server stopped.")
