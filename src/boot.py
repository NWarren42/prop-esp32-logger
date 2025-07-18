# BASE MICROPYTHON BOOT.PY-----------------------------------------------|  # noqa: INP001
# # This is all micropython code to be executed on the esp32 system level and doesn't require a __init__.py file

# This file is executed on every boot (including wake-boot from deep sleep)
#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()
#------------------------------------------------------------------------|


import ujson  # type:ignore # noqa: I001# ujson and machine are micropython libraries
import uasyncio as asyncio  # type:ignore # uasyncio is the micropython asyncio library
import socket  # type:ignore # socket is a micropython library

import wifi_tools as wt
from machine import Pin  # type: ignore # machine is a micropython library
from machine import I2C  # type: ignore # machine is a micropython library

from sensors.LoadCell import LoadCell  # type: ignore
from sensors.PressureTransducer import PressureTransducer  # type: ignore
from sensors.Thermocouple import Thermocouple  # type: ignore # don't need __init__ for micropython
from Valve import Valve  # type: ignore # Importing the Valve class from Valve.py
import SSDPTools
import TCPTools
import commands


INIT = 0        # Device is initializing
WAITING = 1     # Device is waiting for a master to connect
READY = 2       # Device has a master connected and is waiting for commands
STREAMING = 3   # Device is streaming data to a master
ERROR = 4       # Device has encountered an error. Will default to WAITING state after error is resolved.

CONFIG_FILE = "ESPConfig.json"
TCP_PORT = 50000  # Port that I've chosen for the TCP server to listen on. This is the port that the master will connect to.

def readConfig(filePath: str):  # type: ignore  # noqa: ANN201
    try:
        with open(filePath, "r") as file:
            config = ujson.load(file)
            return config
    except Exception as e:
        print(f"Failed to read config file: {e}")
        return {}

def setupDeviceFromConfig(config) -> tuple[list[Thermocouple | LoadCell | PressureTransducer],
                                           dict[str, Valve]]: # type: ignore  # noqa: ANN001 # Typing for the JSON object is impossible without the full Typing library
        """Initialize all devices and sensors from the config file.

        ADC index 0 indicates the sensor is connected directly to the ESP32. Any other index indicates
        connection to an external ADC.
        """

        sensors: list[Thermocouple | LoadCell | PressureTransducer] = []
        valves: dict[str, Valve] = {}

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

            for name, details in config.get("valves", {}).items():
                pin = details.get("pin", None)
                defaultState = details.get("defaultState")

                valves[name.upper()] = (Valve(name=name.upper(),
                                              pin=pin,
                                              defaultState=defaultState,
                                              ))

            return sensors, valves

        if deviceType == "Unknown":
            raise ValueError("Device type not specified in config file")

        return [], {}  # Return empty lists if no sensors or valves are defined

# --------------------- #
#    I2C FUNCTIONS
# --------------------- #

def readRegister(i2cBus: I2C, address: int, register: int) -> bytes:
    """Read a 8-bit register from the ADS112C04.

    There are two parts to this call. The first part is the address of the device to read from, and the second part is the register to read from.
    The address section doesn't natively work with the I
    Address format:


    RREG format is as follows:
    [7:4] Base RREG command (0b0010)
    [3:2] Register number (0b00 for MUX_GAIN_PGA, 0b01 for DR_MODE_CM_VREF_TS, 0b10 for DRDY_DCNT_CRC_BCS_IDAC, 0b11 for IDAC1_IDAC2)
    [1:0] Reserved bits (should be 0)

    EXAMPLE for calling register 2:
    RREG = 0b0010
    Reg# = 0b10
    cmd = 0b0010 << 4 | 0b0010 << 2
    cmd = 0b00100000 | 0b1000
    cmd = 0b00101000 - Final command to request register 2s bits
    """


    rregCommand = 0b0010 # Read register command as defined in datasheet.

    # Shift the command to the left by 4 bits to put it in the first 4 bits of the write command
    # Shift the register number to the left by 2 bits to put it in the register number bits for the rreg call
    fullCmd = rregCommand << 4 | register << 2 # combine the command and register number with bw OR operator

    # Now write the command to the specified device address to query the register contents
    i2cBus.writeto(address, bytes([fullCmd]), stop=False)
    data = i2cBus.readfrom(address, 1)

    # The ADS1112 will respond with the contents of the 8 bit register so we read 1 byte.

    # The data is returned as a byte object, so we need to convert it to an integer. Use big scheme because MSB is first transmitted.
    return data

def setupI2C(): # Return an I2C bus object # noqa: ANN201
    """Set up the I2C bus with the correct pins and frequency.

    This function doesn't need input parameters because the pins and frequency are set by the hardware configuration,
    and will never need to change.
    The SCL pin is GPIO 6 on the ESP32, and the SDA pin is GPIO 7 on the ESP32.



    """

    # The Pins NEED to be set to OUT. For some reason the I2C bus doesn't automatically set this on initialization of the bus.
    sclPin = Pin(6, Pin.OUT) # SCL pin is GPIO 6 on the ESP32. This connects to pin 16 on the ADC
    sdaPin = Pin(7, Pin.OUT) # SDA pin is GPIO 7 on the ESP32. This connects to pin 15 on the ADC -- THIS MIGHT BE PROBLEMATIC, CANT READ SDA?

    # I2C bus 1, SCL pin 6, SDA pin 7, frequency 100kHz
    i2cBus = I2C(1, scl=sclPin, sda=sdaPin, freq=100000)
    return i2cBus

# --------------------- #
#    ASYNC FUNCTIONS
# --------------------- #

async def sendConfig(socket: socket.socket,
                     address: str,
                     config: dict) -> None:
    """Send the configuration file to the client."""
    try:
            # Convert the config file to a JSON string so it can have the encode method called on it
            jStringConfig = ujson.dumps(config)
            confString = "CONF" + jStringConfig + "\n" # Add a header to the config file so the client knows what it is receiving

            # Currently TCP block size is 2048 bytes, this can be changed if needed but config files are small right now.
            # This is meant as a warning block of code if we start having larger config files.
            if len(confString) > 2048:
                raise ValueError("ERROR: Config file too large to send in one TCP block!!.")


            socket.sendto(confString.encode("utf-8"), address)
            print(f"Sent conf string: {confString}")

    except Exception as e:
        print(f"Error sending config file: {e}")

UDPRequests = ("SEARCH", # Message received when server is searching for client sensors
               )

TCPRequests = ("SREAD", # Reads a single value from all sensors
               "CREAD", # Continuously reads data from all sensors until STOP received
               "STOP", # Stops continuous reading
               "STAT", # Returns number of sensors and types
               )


# -------------------- #
#   SETUP THE DEVICE
# -------------------- #
state = INIT  # Device is initializing
print("State = INIT")

# Internal setup methods
config = readConfig(CONFIG_FILE)
sensors, valves = setupDeviceFromConfig(config)  # Initialize sensors from config file

# Networking setup
wlan        = wt.connectWifi("Nolito", "6138201079")
ipAddress   = wlan.ifconfig()[0]  # Get the IP address of the ESP32
tcpListenerSocket   = TCPTools.createListenerTCPSocket()

# I2C Setup
i2cBus = setupI2C()
devices = i2cBus.scan() # Scan the I2C bus for devices. This will return a list of addresses of devices on the bus.

print("I2C devices found at following addresses:", [hex(device) for device in devices]) # Print the addresses of the devices found on the bus


state = WAITING  # Device is waiting for a master to connect
print("State = WAITING")

def run() -> None:
    """Run the main event loop."""

    try:
        # Start the main event loop with the initial state
        asyncio.run(main(state))
    except KeyboardInterrupt:
        print("Server stopped gracefully...")


async def main(state: int) -> None:
    global tcpListenerSocket

    # Set up some variables for the server state
    clientSock = None

    # Fire off the SSDP listener task to send out pings if it receives a discovery message.
    ssdpTask = asyncio.create_task(SSDPTools.waitForDiscovery())

    # Let whatever tripped an error state set an error message for the error state event loop to catch.
    errorMessage = ""

    print("Starting server...")

    while True:

        try:

            # ------------- #
            # WAITING STATE #
            # ------------- #
            if state == WAITING:
                print("Waiting for a master to connect...")

                # Ensure we have a listening socket
                if tcpListenerSocket is None:
                    tcpListenerSocket = TCPTools.createListenerTCPSocket()

                try:
                    # Wait for incoming TCP connection
                    clientSock, clientAddr = await TCPTools.waitForConnection(tcpListenerSocket)

                    # Send config to newly connected client
                    jStringConfig = ujson.dumps(config)
                    confString = "CONF" + jStringConfig + "\n"
                    clientSock.sendall(confString.encode("utf-8"))
                    print(f"Sent config to client at {clientAddr}")

                    state = READY
                    print("State = READY")

                except OSError as e:
                    errorMessage = f"Network error: {e}"
                    state = ERROR
                    continue
                except Exception as e:
                    errorMessage = f"Error in WAITING state: {e}"
                    state = ERROR
                    continue

            # ------------- #
            #  READY STATE  #
            # ------------- #
            if state == READY and clientSock is not None:

                try:
                    cmd = await TCPTools.waitForCommand(clientSock)

                    if not cmd:
                        errorMessage = "Empty message received. Server closed connection or there was an error."
                        state = ERROR
                        continue

                    print(f"Received command: {cmd}")

                    response: str = ""  # Reset response for each command

                    cmdParts = cmd.split(" ")
                    print(f"Command parts: {cmdParts}")
                    if cmdParts[0] == "GETS": response = await commands.gets(sensors)  # Get a single reading from each sensor and return it as a formatted string
                    if cmdParts[0] == "STREAM": commands.strm(sensors, clientSock, cmdParts[1:])  # Start streaming data from sensors
                    if cmdParts[0] == "STOP": response = commands.stopStrm()  # Stop streaming data from sensors
                    if cmdParts[0] == "VALVE": response = commands.actuateValve(valves, cmdParts[1:])  # Open or close a valve

                    if response:
                        message = f"{cmdParts[0]} {response}\n"
                        clientSock.sendall(message.encode("utf-8"))
                        print(f"Sent response: {message}")

                except TCPTools.ConnectionClosedError:
                    state = ERROR
                    errorMessage = "Connection closed by client."
                    continue

            # ------------- #
            #  ERROR STATE  #
            # ------------- #

            # The error state will handle all the potential cleanup so we can just reset the state to WAITING afterwards.
            # Any error that we are catching should probably trigger an error state, so we can reset the device and try again.
            if state == ERROR:
                print(f"ERROR STATE: {errorMessage}\nResetting to WAITING state.")
                if clientSock:
                    clientSock.close()
                    clientSock = None

                # Reset the sockets and variables to kill any existing connections or attempts to connect.
                clientSock = None

                # Kill stream task if it exists
                commands.stopStrm()

                state = WAITING
                errorMessage = ""  # Reset the error message

            await asyncio.sleep(0)  # Yield to event loop
        except KeyboardInterrupt:
            print("Server stopped by user.")
            if clientSock:
                clientSock.close()
            break
