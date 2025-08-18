# BASE MICROPYTHON BOOT.PY-----------------------------------------------|
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
from machine import SoftI2C  # type: ignore # SoftI2C is a micropython library for I2C communication

from sensors.LoadCell import LoadCell  # type: ignore
from sensors.PressureTransducer import PressureTransducer  # type: ignore
from sensors.Thermocouple import Thermocouple  # type: ignore # don't need __init__ for micropython
from Control import Control  # type: ignore # Importing the Valve class from Valve.py
from ADS112C04 import ADS112C04  # type: ignore # Importing the ADS112 class from ADS112
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

WIFI_INDICATOR_PIN = Pin(8, Pin.OUT)
SAFE24_PIN: Pin | None = None  # Pin for the SAFE24 switch, if used. Set to None if not used.
IGNITOR_PIN: Pin | None = None  # Pin for the ignitor switch, if used. Set to None if not used.

def readConfig(filePath: str):  # type: ignore  # noqa: ANN201
    try:
        with open(filePath, "r") as file:
            config = ujson.load(file)
            return config
    except Exception as e:
        print(f"Failed to read config file: {e}")
        return {}

def setupDeviceFromConfig(config: dict,
                          adcs: list[ADS112C04]) -> tuple[dict[str, Thermocouple | LoadCell | PressureTransducer],
                                           dict[str, Control]]: # type: ignore  # Typing for the JSON object is impossible without the full Typing library
        """Initialize all devices and sensors from the config file.

        ADC index 0 indicates the sensor is connected directly to the ESP32. Any other index indicates
        connection to an external ADC.
        """

        sensors: dict[str, Thermocouple | LoadCell | PressureTransducer] = {}
        controls: dict[str, Control] = {}

        print(f"Initializing device: {config.get('deviceName', 'Unknown Device')}")
        deviceType = config.get("deviceType", "Unknown")

        if deviceType == "Sensor Monitor": # Sensor monitor is what I'm calling an ESP32 that reads sensors
            sensorInfo = config.get("sensorInfo", {})

            for name, details in sensorInfo.get("thermocouples", {}).items():

                # Find the corresponding ADC for the thermocouple
                adc = None
                if details["ADCIndex"] > 0 and details["ADCIndex"] <= 4:
                    adc = adcs[details["ADCIndex"] - 1]

                sensors[name] = Thermocouple(
                    name=name,
                    ADCIndex=details["ADCIndex"],
                    ADC=adc,  # Optional ADC for external ADCs
                    highPin=details["highPin"],
                    lowPin=details["lowPin"],
                    units=details["units"],
                    thermoType=details["type"],
                )

            for name, details in sensorInfo.get("pressureTransducers", {}).items():
                # Find the corresponding ADC for the pressure transducer
                adc = None
                if details["ADCIndex"] > 0 and details["ADCIndex"] <= 4:
                    adc = adcs[details["ADCIndex"] - 1]

                sensors[name] = PressureTransducer(
                    name=name,
                    ADCIndex=details["ADCIndex"],
                    ADC=adc,  # Optional ADC for external ADCs
                    pinNumber=details["pin"],
                    maxPressure_PSI=details["maxPressure_PSI"],
                    units=details["units"],
                )

            for name, details in sensorInfo.get("loadCells", {}).items():

                # Find the corresponding ADC for the load cell
                adc = None
                if details["ADCIndex"] > 0 and details["ADCIndex"] <= 4:
                    adc = adcs[details["ADCIndex"] - 1]

                sensors[name] = LoadCell(
                    name=name,
                    ADCIndex=details["ADCIndex"],
                    ADC=adc,  # Optional ADC for external ADCs
                    highPin=details["highPin"],
                    lowPin=details["lowPin"],
                    loadRating_N=details["loadRating_N"],
                    excitation_V=details["excitation_V"],
                    sensitivity_vV=details["sensitivity_vV"],
                    units=details["units"],
                )

            for name, details in config.get("controls", {}).items():
                pin = details.get("pin", None)
                defaultState = details.get("defaultState")

                controls[name.upper()] = (Control(name=name.upper(),
                                                controlType=details.get("type").upper(),  # Normalize type to upper case
                                                pin=pin,
                                                defaultState=defaultState,
                                                ))





            return sensors, controls

        if deviceType == "Unknown":
            raise ValueError("Device type not specified in config file")

        return {}, {}  # Return empty dicts if no sensors or valves are defined

# --------------------- #
#    I2C FUNCTIONS
# --------------------- #

def setupI2C(): # Return an I2C bus object # noqa: ANN201
    """Set up the I2C bus with the correct pins and frequency.

    This function doesn't need input parameters because the pins and frequency are set by the hardware configuration,
    and will never need to change.
    The SCL pin is GPIO 6 on the ESP32, and the SDA pin is GPIO 7 on the ESP32.
    """

    # I2C bus 1, SCL pin 16, SDA pin 15, frequency 100kHz
    i2cBus = SoftI2C(scl=Pin(16), sda=Pin(15), freq=100_000)
    return i2cBus

def makeI2CDevices(softI2CBus: SoftI2C.SoftI2C, addresses: list[int]) -> list[ADS112C04]:
    """Create a list of ADS112 devices on the I2C bus."""
    devices = []
    for addr in addresses:  # Create 4 devices
        device = ADS112C04(softI2CBus, addr)
        devices.append(device)
    return devices

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

# I2C Setup - Need to establish
i2cBus = setupI2C()
devices = i2cBus.scan() # Scan the I2C bus for devices. This will return a list of addresses of devices on the bus.
adcs = makeI2CDevices(i2cBus, devices)  # Create a list of ADS112 devices on the I2C bus

# Internal setup methods
config = readConfig(CONFIG_FILE)
sensors, controls = setupDeviceFromConfig(config, adcs)  # Initialize sensors from config file


print("I2C devices found at following addresses:", [hex(device) for device in devices]) # Print the addresses of the devices found on the bus

# Networking setup
wlan = wt.connectWifi("propnet", "propteambestteam")
if wlan:
    WIFI_INDICATOR_PIN.on()

ipAddress   = wlan.ifconfig()[0]  # Get the IP address of the ESP32
tcpListenerSocket   = TCPTools.createListenerTCPSocket()

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
    global tcpListenerSocket  # noqa: PLW0603

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
            try:
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
            except Exception as e:
                state = ERROR
                errorMessage = f"Unexpected error in waiting state: {e}"
                continue

            # ------------- #
            #  READY STATE  #
            # ------------- #
            if state == READY and clientSock is not None:

                try:
                    cmds = await TCPTools.waitForCommand(clientSock)

                    for cmd in cmds:
                        if not cmd:
                            errorMessage = "Empty message received. Server closed connection or there was an error."
                            state = ERROR
                            continue

                        response: str = ""  # Reset response for each command

                        print(f"Received command: {cmd}")
                        cmdParts = cmd.split(" ")
                        print(f"Command parts: {cmdParts}")
                        if cmdParts[0] == "GETS": response = await commands.gets(sensors)  # Get a single reading from each sensor
                        if cmdParts[0] == "STREAM": commands.strm(sensors, clientSock, cmdParts[1:])  # Start streaming data from sensors
                        if cmdParts[0] == "STOP": response = commands.stopStrm()  # Stop streaming data from sensors
                        if cmdParts[0] == "CONTROL": response = commands.actuateControl(controls, cmdParts[1:])  # Open or close a control
                        if cmdParts[0] == "STATUS" : response = commands.getStatus(controls)

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
            ssdpTask.cancel()  # Cancel the SSDP task
            if tcpListenerSocket:
                tcpListenerSocket.close()  # Close the TCP listener socket
            break
