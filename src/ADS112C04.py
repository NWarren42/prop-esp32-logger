import time

from machine import (  # type: ignore
    Pin,  # type: ignore
    SoftI2C,  # type: ignore
)


MUX_CODES = {
    (0,1): 0b0000,  # AIN0→AIN1
    (0,2): 0b0001,  # AIN0→AIN2
    (0,3): 0b0010,  # AIN0→AIN3
    (1,0): 0b0011,  # AIN1→AIN0
    (1,2): 0b0100,  # AIN1→AIN2
    (1,3): 0b0101,  # AIN1→AIN3
    (2,3): 0b0110,  # AIN2→AIN3
    (3,2): 0b0111,  # AIN3→AIN2
    (0, -1): 0b1000,   # AIN0→GND
    (1, -1): 0b1001,   # AIN1→GND
    (2, -1): 0b1010,   # AIN2→GND
    (3, -1): 0b1011,   # AIN3→GND
    # Other codes exist but are not used in this implementation. See data sheet.
}

# DRDY pin mappings for the ADS112 devices on the ADC Breakout board. #FIXME: Fix for PANDA
# This is intended for comparison with self.addressI2C, which is the I2C address shifted left by 1 bit.
DRDY_PINS = { #             A1↓  A0↓
    0b10000000: 4,  # ADC0 - GND, GND - has its DRDY pin on GPIO 4
    0b10000010: 5,  # ADC1 - GND, VDD - has its DRDY pin on GPIO 5
    0b10001000: 15, # ADC2 - VDD, GND - has its DRDY pin on GPIO 15
    0b10001010: 16, # ADC3 - VDD, VDD - has its DRDY pin on GPIO 16
}

VREF_BITS = {
    2.048: 0b00,
    0: 0b01,
    5: 0b10,
}


class ADS112C04:
    """ADS112C04 I2C ADC driver for ESP32."""
    def __init__(self,
                 i2c: SoftI2C.SoftI2C,
                 address: int):
        """:param address: I2C address of the ADS1112 device (can be specified as hex, e.g., 0x48)"""

        self.i2c = i2c
        self.address = address
        self.addressI2C  = bytes([self.address << 1 | 0])  # Shift address for I2C read/write operations
        self.drdyPin: Pin | None = None

        self.mode = "SINGLE"  # Default mode is single conversion
        self.activePosPin: int | None = None  # Initialize activePosPin to None
        self.activeNegPin: int | None = None  # Initialize activeNegPin to None

        # FIXME: Unimplemented configuration options. We just assume that these are right for now.
        self.pgaGain = -1  # Default gain is 1

        #FIXME: Make sure to measure the VDD pins before setting this!! Mine is at 5.15V.
        self.vref = 5  # Internal reference is 2.048V but we set VDD to 5V and configure the device to use VDD as the reference voltage.


        # Initialize the device
        self.resetDevice()

    def resetDevice(self) -> None:
        """Reset the ADS1112 device."""
        resetCommand = bytes([0x06]) # Reset command is 0000 011x
        self._sendSimpleCommand(resetCommand)

        if self.readRegister(0) != bytes([0x00]) or self.readRegister(1) != bytes([0x00]):
            raise RuntimeError("Failed to reset ADS1112 device. Check connections and power supply.")

        # Set the PGA to bypass
        reg0 = self.readRegister(0)[0]
        reg0 |= 0x01  # Set PGA_BYPASS bit
        self.writeRegister(0, bytes([reg0]))

        self.activePosPin = None  # Reset active positive pin
        self.activeNegPin = None  # Reset active negative pin
        self.mode = "SINGLE"  # Reset mode to single conversion

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
        [2:1] VREF = 0b10 - Sets the reference voltage to VDD.
        [0]   TS = 0b0 - Temperature sensor disabled. 0b1 to enable.

        """

        # Create the command to set continuous mode
        dataRate = 0b110  # Data rate 1000 SPS in Normal Mode
        speedMode = 0b0  # Normal mode
        sampleMode = 0b1  # Continuous mode
        refVoltage = 0b10  # Use VDD as the reference voltage
        tempSensor = 0b0  # Temperature sensor disabled

        continuousModeCommand = bytes([(dataRate << 5) |
                                       (speedMode << 4) |
                                       (sampleMode << 3) |
                                       (refVoltage << 1) |
                                       tempSensor])

        self.writeRegister(1, continuousModeCommand)
        self.start()  # Start continuous conversion mode

    def setInputPins(self,
                        AIN_Positive: int,
                        AIN_Negative: int = -1,
                        pgaGain: int = -1,  # Default to -1 (bypass)
                        ) -> None:
        """Switch the active input channel for the ADS112.

        This function sets the MUX register to select the input channel for single-ended or differential readings. If a
        reading is single-ended, the negative input is set to GND (-1).

        [7:4] MUX[3:0] = MUX_CODES[ch] - Selects the input channel
        [3:1] GAIN[2:0] = 0b000 - Sets gain to 1
        [0]   PGA_BYPASS = 0b1 - Bypass the programmable gain amplifier for a single-ended read

        """

        # Any time we change the inputs, the first order of operation is to enable pga bypass to let us make switches
        # without fear that the new channel's voltage with the old gain setting will not kill the ADC. We need to set
        # the last four bits to zero as gains 8 to 128 ignore the bypass bit and use the PGA anyways.
        reg0 = self.readRegister(0)[0]
        reg0 &= 0xF0  # Clear the last four bits
        reg0 |= 0x01  # Set to 0b0001: gain=0, bypass=1
        self.writeRegister(0, bytes([reg0]))

        channel = (AIN_Positive, AIN_Negative)
        if channel not in MUX_CODES:
            raise ValueError(f"Invalid channel read configuration: {channel}")

        muxSetting = MUX_CODES[channel]

        # Read current Reg0, keep lower 4 bits (gain + bypass), replace only MUX
        reg0 = self.readRegister(0)[0]
        reg0 = (reg0 & 0x0F) | (muxSetting << 4)

        if AIN_Negative == -1:
            reg0 |= 0x01 # Single ended measurements always need PGA bypassed
        elif pgaGain != -1: reg0 &= ~0x01  # Clear PGA_BYPASS bit if gain is not -1 (bypass)
        else: reg0 |= 0x01  # Set PGA_BYPASS bit if gain is -1 (bypass)

        self.writeRegister(0, bytes([reg0]))
        check = self.readRegister(0)
        if check[0] != reg0:
            print(f"Failed to set MUX channel {channel}. Expected {reg0:#04x}, got {check[0]:#04x}")
        else:
            self.activePosPin = channel[0]
            self.activeNegPin = channel[1]

    def getReading(self,
                           AIN_Pos: int,
                           AIN_Neg: int = -1,
                           pgaGain: int = -1,
                           ) -> float:
        """Get a single-ended conversion from the specified channel and returns a voltage.

        This function configures the ADS1112 to perform a single-ended conversion on the specified channel
        and returns the conversion result. Defaults to GND for the negative input if not specified.

        First tell the ADC which channel to sample by setting the write register.

        Then, if in single-shot mode, kick off the conversion by writing to the START/SYNC register.

        """

        # Set the MUX register to select the proper channel if it is not already set
        if self.activePosPin != AIN_Pos or self.activeNegPin != AIN_Neg:
            self.setInputPins(AIN_Positive=AIN_Pos, AIN_Negative=AIN_Neg, pgaGain=-1) # Force bypass

            if pgaGain == -1:
                self.setPGA(-1)
            else:
                self.setPGA(pgaGain)

        # Switch to continuous mode if not already in that mode
        if self.mode != "CONTINUOUS":
            self.setContinuousMode()
            self.mode = "CONTINUOUS"


        # Now send the first I2C frame which writes the RDATA command to the device.
        rdataCommand = bytes([0x10])     # RDATA command is 0001 0000
        self._addressDevice(read=False)  # Address the device for writing
        self.i2c.write(rdataCommand)     # Send the RDATA command

        # Now re-address the device for reading and it will return the conversion result.
        self._addressDevice(read=True)  # Address the device for reading

        # This is a 16-bit result, so the device will return two transmissions. The first is the MSB and the second is
        # the LSB. We read them separately so that we acknowledge the first byte and then read the second byte.
        buf = bytearray(2)  # Buffer to hold the read data
        self.i2c.readinto(buf)  # Read the 2 bytes of data into
        self.i2c.stop()  # Stop the I2C transmission and pull the

        # String together the bits of the bytearray for debugging. Unused for now.
        bitString = " ".join(f"0b{byte:08b}" for byte in buf)
        # print(f"Read from ADS112C04: {bitString}")

        # Convert the raw ADC bits to a voltage
        voltage = self._bitsToVoltage(buf[0], buf[1], vref=self.vref)

        return voltage

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

        # Print the bits of the bytearray for debugging
        bitString = " ".join(f"0b{byte:08b}" for byte in buf)
        # print(f"Read from register {register}: {bitString}")

        return buf  # Return the read data

    def setPGA(self, gain: int) -> None:
        """Set the Programmable Gain Amplifier (PGA) gain.

        :param gain: The gain to set (1, 2, 4, 8, 16, 32, 64, 128), or -1 to disable PGA (bypass).
        """
        if gain == -1:
            # Disable PGA (bypass): set bit 0 to 1, clear bits 3:1
            reg0 = self.readRegister(0)[0]
            reg0 &= ~0x0F  # Clear bits 3:0
            reg0 |= 0x01   # Set bit 0 (PGA bypass)
            self.writeRegister(0, bytes([reg0]))
            check = self.readRegister(0)
            if check[0] != reg0:
                raise ValueError("Failed to disable PGA (bypass).")
            print("PGA bypass enabled (disabled).")
            self.pgaGain = -1  # For calculations, PGA is bypassed (gain=1)
            return

        if gain not in [1, 2, 4, 8, 16, 32, 64, 128]:
            raise ValueError(f"Invalid gain value: {gain}. Valid values are: [1, 2, 4, 8, 16, 32, 64, 128, -1].")

        # The PGA setting is in bits [3:1] of the MUX register
        gain_to_bits = {1: 0b000, 2: 0b001, 4: 0b010, 8: 0b011, 16: 0b100, 32: 0b101, 64: 0b110, 128: 0b111}
        pgaSetting = gain_to_bits[gain] << 1
        reg0 = self.readRegister(0)[0]
        reg0 &= ~0x0F  # Clear bits 3:0 (PGA gain + bypass)
        reg0 |= pgaSetting  # Set new PGA gain
        # Ensure PGA bypass is 0 (enabled)
        self.writeRegister(0, bytes([reg0]))

        check = self.readRegister(0)
        if check[0] != reg0:
            raise ValueError("Failed to set PGA gain.")

        print(f"Successfully set PGA gain to {gain}.")
        self.pgaGain = gain  # Update the instance variable

    def benchmarkReadings(self,
                          posChannel: int,
                          negChannel: int=-1,
                          samples: int=100) -> tuple[list[float], float]:
        """Call adc.getReading(channel, neg_channel) `samples` times, measure each call's duration (in µs), and report stats."""
        timings = []

        # Warm-up (optional — discard first reading)
        _ = self.getReading(posChannel, negChannel)

        for _ in range(samples):
            t0 = time.ticks_us() #type: ignore # this is a micropython library function that returns the current time in microseconds
            _ = self.getReading(posChannel, negChannel)
            t1 = time.ticks_us() #type: ignore # this is a micropython library function that returns the current time in microseconds
            dt = time.ticks_diff(t1, t0)  # dt in µs, handles wraparound #type: ignore # this is a micropython function
            timings.append(dt)

        avg = sum(timings) / samples

        print(f"Ran {samples} samples on channel {posChannel}:")
        print(f"  Min: {min(timings):6d} µs")
        print(f"  Max: {max(timings):6d} µs")
        print(f"  Avg: {avg:6.1f} µs")

        return timings, avg

    def _addressDevice(self, read: bool) -> None:
        """Address the specified ADS112 device for communication.

        Addressing the devices constitutes sending a start condition, followed by the address of the device being addressed.

        :param read: If True, address the device for reading; otherwise, address for writing.
        """
        address_byte = (self.address << 1) | (0x01 if read else 0x00)

        self.i2c.start()
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

    def _bitsToVoltage(self,
                       msb: int,
                       lsb: int,
                       vref: float = 5.0) -> float:
        """Convert the raw ADC bits to a voltage."""
        raw = (msb << 8) | lsb  # Combine MSB and LSB
        if raw & 0x8000:  # If the sign bit is set
            raw -= 1 << 16  # Convert to negative value
        voltage = raw * (vref / 2**15) / abs(self.pgaGain)
        return voltage

