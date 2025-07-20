from machine import SoftI2C  # type: ignore


MUX_CODES = {
    0: 0b1000,   # AIN0→GND
    1: 0b1001,   # AIN1→GND
    2: 0b1010,   # AIN2→GND
    3: 0b1011,   # AIN3→GND
}

class ADS112:
    """ADS1112 I2C ADC driver for ESP32."""
    def __init__(self,
                 i2c: SoftI2C.SoftI2C,
                 address: int):
        """:param address: I2C address of the ADS1112 device (can be specified as hex, e.g., 0x48)"""

        self.i2c = i2c
        self.address = address
        self.addressI2C  = bytes([self.address << 1 | 0])  # Shift address for I2C read/write operations

        self.mode = "SINGLE"  # Default mode is single conversion
        self.activePin: int | None = None  # Initialize activePin to None

        # Initialize the device
        self.resetDevice()



    def resetDevice(self) -> None:
        """Reset the ADS1112 device."""
        resetCommand = bytes([0x06]) # Reset command is 0000 011x
        self._sendSimpleCommand(resetCommand)

    def start(self) -> None:
        """Start continuous conversion mode or start a single conversion depending on mode."""
        startCommand = bytes([0x08]) # Start command is 0000 100x
        self._sendSimpleCommand(startCommand)

    def powerDown(self) -> None:
        """Power down the ADS1112 device."""
        powerDownCommand = bytes([0x02])  # Power down command is 0000 001x
        self._sendSimpleCommand(powerDownCommand)

    def setContinuousMode(self) -> None:
        """Set the ADS1112 to continuous conversion mode.

        This tells the device to continuously run a conversion at the specified rate. Data rate and sampling mode are
        set using register 1.

        [7:5] DR[2:0] = 0b110 - Sets data rate to 1000 SPS in Normal Mode. 2kSPS in turbo mode.
        [4]   MODE = 0b0 - Normal mode. 0b1 for turbo mode.
        [3]   CONTINUOUS = 0b1 - Sets the device to continuous conversion mode.
        [2:1] VREF = 0b00 - Sets the reference voltage to the internal reference.
        [0]   TS = 0b0 - Temperature sensor disabled. 0b1 to enable.

        """

        # Create the command to set continuous mode
        dataRate = 0b110  # Data rate 1000 SPS in Normal Mode
        speedMode = 0b0  # Normal mode
        sampleMode = 0b1  # Continuous mode
        refVoltage = 0b00  # Internal reference
        tempSensor = 0b0  # Temperature sensor disabled

        continuousModeCommand = bytes([(dataRate << 5) |
                                       (speedMode << 4) |
                                       (sampleMode << 3) |
                                       (refVoltage << 1) |
                                       tempSensor])

        self.writeRegister(1, continuousModeCommand)

    def switchActiveInput(self,
                          channel: int) -> None:
        """Switch the active input channel for the ADS112.

        [7:4] MUX[3:0] = MUX_CODES[ch] - Selects the input channel
        [3:1] GAIN[2:0] = 0b000 - Sets gain to 1
        [0]   PGA_BYPASS = 0b1 - Bypass the programmable gain amplifier for a single-ended read

        """
        if channel == self.activePin:
            print(f"Channel {channel} is already active. No change made.")
            return

        if channel not in MUX_CODES:
            raise ValueError(f"Invalid channel: {channel}")

        muxSetting = MUX_CODES[channel]  # Shift the MUX code to the correct position
        gainSetting = 0b000  # Gain set to 1
        pgaBypass = 0b1  # Bypass the programmable gain amplifier for

        registerValue = bytes([muxSetting << 4 |
                               gainSetting << 1|
                               pgaBypass])

        self.writeRegister(0, registerValue)

        # Check for a successful write by reading the register back
        readValue = self.readRegister(0)
        if readValue != registerValue:
            print(f"Failed to set MUX channel {channel}. Expected {registerValue}, got {readValue}")
        else:
            self.activePin = channel
            print(f"Active input channel set to {channel} (MUX code: 0x{muxSetting})")
            print(f"Set MUX register to: 0x{registerValue.hex()}, read back: 0x{readValue.hex()}")

    def getConvSingleEnded(self,
                           ch: int) -> int:
        """Get a single-ended conversion from the specified channel.

        This function configures the ADS1112 to perform a single-ended conversion on the specified channel
        and returns the conversion result.

        First tell the ADC which channel to sample by setting the write register.

        Then, if in single-shot mode, kick off the conversion by writing to the START/SYNC register.

        """

        # Switch to continuous mode if not already in that mode
        if self.mode != "CONTINUOUS":
            self.setContinuousMode()
            self.mode = "CONTINUOUS"

        # Set the MUX register to select the proper channel
        self.switchActiveInput(ch)

        # Send repeated start condition and write the register value
        return 0

    def writeRegister(self, register: int, value: bytes) -> None:
        """Write a value to a specific register of the ADS112 device.

        :param register: The register address to write to.
        :param value: The value to write to the register.
        """

        # The WREG command is structured like: 0100 rrxx dddd dddd
        # Where rr is the register address and dddd dddd is the data to write.
        # This is sent in two parts: the command - 0100 rrxx, and the data - dddd dddd
        wreg = 0x40 | ((register & 0x03) << 2)  # We know register only 0-3, so mask with 0x03 then shift to correct position.
        wregBytes = bytes([wreg])  # Convert to bytes for I2C write

        self._addressDevice(read=False)
        self.i2c.write(wregBytes)
        self.i2c.write(value)
        self.i2c.stop()

    def readRegister(self, register: int) -> bytearray:
        """Read a value from a specific register of the ADS112 device.

        The rreg command is structured like: 0110 rrxx
        The full rreg sequence takes two i2c transactions:
        1. Send the rreg command to the device.
        2. Read the response data from the device.

        First we address the device and send the rreg command, then we read the data.

        :param register: The register address to read from.
        :return: The value read from the register.
        """

        buf = bytearray(1)  # Buffer to hold the read data

        # The RREG command is structured like: 0010 rrxx
        rreg = 0x20 | ((register & 0x03) << 2)
        rregBytes = bytes([rreg])  # Convert to bytes for I2C write

        # We first write the command to the device
        self._addressDevice(read=False)
        self.i2c.write(rregBytes)

        # Then we read the data from the device
        self._addressDevice(read=True)  # Now we address the device for reading
        self.i2c.readinto(buf)  # Read the 2 bytes of data into the buffer
        self.i2c.stop()

        return buf  # Return the read data

    def _addressDevice(self, read: bool) -> None:
        """Address the specified ADS112 device for communication.

        :param read: If True, address the device for reading; otherwise, address for writing.
        """
        self.i2c.start()
        address_byte = (self.address << 1) | (0x01 if read else 0x00)
        self.i2c.write(bytes([address_byte]))

    def _sendSimpleCommand(self, command: bytes) -> None:
        """Send a command to the ADS1112 device.

        This addresses the device, sends a repeated start condition, writes the command, and stops the transmission.
        This is the format for simple commands with the ADS112.

        """
        # Address the device
        self._addressDevice(read=False)

        # Send the command
        self.i2c.write(command)

        # End transmission
        self.i2c.stop()

