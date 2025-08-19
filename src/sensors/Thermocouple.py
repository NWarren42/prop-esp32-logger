# noqa: INP001 -- Implicit namespace doesn't matter here
from ADS112C04 import ADS112C04  # Importing the ADS112C04 class for external ADCs
from sensors.Sensor import Sensor  # Importing the base Sensor class


class Thermocouple(Sensor):
    """Class for reading thermocouple data from an ADC.

    UNFINISHED. Don't use this yet. Need to see how the circuitry works out

    """

    def __init__ (self,
                  name: str,
                  ADCIndex: int,
                  ADC: ADS112C04 | None,  # Optional ADS112C04 instance for external ADCs. None if using the ESP32 ADC.
                  highPin: int,
                  lowPin: int,
                  units: str,
                  thermoType: str,
                  ):

        super().__init__(
            name=name,
            ADCIndex=ADCIndex,
            ADC=ADC,  # No external ADC for thermocouples
            highPin=highPin,
            lowPin=lowPin,
            units=units,
        )

        self.pgaGain = 1  # Default PGA gain for the ADC, can be set later.

        if self.units not in ["V", "C"]:
            raise ValueError(f"Invalid units specified: {self.units}. Valid units are 'V' and 'C'.")

        self.type = thermoType


    def takeData(self, unit="DEF") -> float: # Currently returns differential voltage reading. DEF for default.
        """Take a reading from the thermocouple and add it to the data list."""
        if self.ADC and self.ADC.pgaGain != self.pgaGain:
            self.ADC.setPGA(self.pgaGain)

        reading = self._getVoltageReading()

        if unit == "DEF":
            readingUnit = self.units
        else:
            readingUnit = unit

        if readingUnit == "V": return reading
        if readingUnit == "C": return self._convertVoltageToTemperature(reading)

        raise ValueError(f"Invalid unit specified: {readingUnit}. Valid units are 'V' and 'C'.")

    def _convertVoltageToTemperature(self, voltage: float) -> float:
        """Convert the voltage reading to temperature in Celsius.

        This method should be implemented based on the thermocouple type.
        """
        # FIXME: Placeholder for conversion logic
        # For example, if using a K-type thermocouple, you would use the appropriate conversion formula.
        return voltage
