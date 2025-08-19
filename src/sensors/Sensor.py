# noqa: INP001 -- Implicit namespace doesn't matter here
from machine import Pin  # type: ignore # These are micropython libraries

from ADS112C04 import ADS112C04


class Sensor:
    """Base class for sensors."""

    def __init__(self,
                 name: str,
                 ADCIndex: int,
                 ADC: ADS112C04 | None,  # Optional ADS112C04 instance for external ADCs. None if using the ESP32 ADC.
                 highPin: int,
                 lowPin: int = -1, # Low pin number is optional, used for differential sensors. -1 indicates ground reference pin.
                 units: str = "V",  # Default to returning a voltage reading
                 ):
        self.name = name
        self.ADCIndex = ADCIndex  # ADCIndex is the index of the ADC in the config file. 0 indicates the ESP32 ADC. 1-4 # indicate the ADS112C04 ADCs.

        # Pins can either be Pin objects or integers. They are Pins if using the onboard ADC and integers if using the ADS112C04.
        self.highPin: Pin | int
        self.lowPin:  Pin | int
        self.pgaGain: int = -1  # Default PGA gain for the ADC. -1 for bypass

        # ADC MANAGEMENT
        # --------------------
        # Check if the ADCIndex is valid
        if self.ADCIndex < 0 or self.ADCIndex > 4:
            raise ValueError(f"Invalid ADCIndex: {self.ADCIndex}. Must be between 0 and 4.")

        if self.ADCIndex == 0:
            # If the ADC index is 0, use the ESP32 ADC
            self.highPin = Pin(highPin, Pin.IN)

            # Assign a low pin if the reading is ground referenced
            if lowPin != -1:
                self.lowPin = Pin(lowPin, Pin.IN)
            else:
                self.lowPin = -1
        else:
            # If not using the ESP32 ADC, we just store the pin numbers and assign the ADS112C04 object to the ADC attribute.
            self.highPin = highPin
            self.lowPin = lowPin # Fine to store -1 here, the ADS112 driver accepts -1 as a ground reference pin.
            self.ADC = ADC

        # Data management
        self.units = units
        self.data = []

    def takeData(self) -> float:
        """Take a reading and return a value in the specified units.

        This is up for implementation in subclasses. The default implementation returns a voltage reading. A child class
        should override this method to provide specific sensor readings.

        """
        return self._getVoltageReading()

    def _getVoltageReading(self) -> float:
        # Native ESP32 ADC reading
        if self.ADCIndex == 0:
            if isinstance(self.lowPin, Pin):
                adcReading = self.highPin.read() - self.lowPin.read() # type:ignore # these are micropython Pin objects
                return (adcReading / 4095) * 3.3  # 4095 at 3.3V is the max value for the ESP32 ADC.
            if self.lowPin == -1:                 # If lowPin is -1, we are using a ground reference pin
                adcReading = self.highPin.read()    # type:ignore # this is a micropython Pin object
                return (adcReading / 4095) * 3.3    # 4095 at 3.3V is the max value for the ESP32 ADC
            raise ValueError("Invalid lowPin value. Must be a Pin object or -1 for ground reference.")

        # ADS112C04 ADC reading
        if isinstance(self.ADC, ADS112C04):
            voltageReading = self.ADC.getReading(self.highPin, self.lowPin, self.pgaGain)
            return voltageReading # The get reading method returns a voltage reading directly.

        raise ValueError("No valid ADC found.")
