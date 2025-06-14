# BASE MICROPYTHON BOOT.PY-----------------------------------------------|  # noqa: INP001
# # This is all micropython code to be executed on the esp32 system level and doesn't require a __init__.py file

# This file is executed on every boot (including wake-boot from deep sleep)
#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()
#------------------------------------------------------------------------|


import ujson  # type:ignore # noqa: I001# ujson and machine are micropython libraries
import enum

import wifi_tools as wt
from AsyncManager import AsyncManager
from machine import Pin  # type: ignore # machine is a micropython library
from machine import I2C  # type: ignore # machine is a micropython library

class DeviceState(enum.Enum):
    """Enum for the state of the device."""
    INIT = 0        # Device is initializing
    WAITING = 1     # Device is waiting for a master to connect
    READY = 2       # Device has a master connected and is waiting for commands
    STREAMING = 3   # Device is streaming data to a master
    ERROR = 4       # Device has encountered an error. Will default to WAITING state after error is resolved.

CONFIG_FILE = "ESPConfig.json"

def readConfig(filePath: str):  # type: ignore  # noqa: ANN201
    try:
        with open(filePath, "r") as file:
            config = ujson.load(file)
            return config
    except Exception as e:
        print(f"Failed to read config file: {e}")
        return {}

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

def setupI2C() -> object: # Return object since I don't know the type of the I2C bus object in micropython
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


UDPRequests = ("SEARCH", # Message received when server is searching for client sensors
               )

TCPRequests = ("SREAD", # Reads a single value from all sensors
               "CREAD", # Continuously reads data from all sensors until STOP received
               "STOP", # Stops continuous reading
               "STAT", # Returns number of sensors and types
               )

state = DeviceState.INIT  # Device is initializing

# Internal setup methods
config = readConfig(CONFIG_FILE)
wlan = wt.connectWifi("Nolito", "6138201079")

## I2C Setup




devices = i2cBus.scan() # Scan the I2C bus for devices. This will return a list of addresses of devices on the bus.
print("I2C devices found at following addresses:", [hex(device) for device in devices]) # Print the addresses of the devices found on the bus

# The AsyncManager is the main server that handles all incoming requests and manages the sensors.
server = AsyncManager(config)

# Current state is that you must enter mpremote and run the main() function to start the server.
def main() -> None:
    server.run()
