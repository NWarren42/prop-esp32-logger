# noqa: INP001 -- Implicit namespace doesn't matter here

from sensors.Sensor import Sensor  # Importing the base Sensor class


class LoadCell(Sensor):
    """Class for reading load cell data from an ADC."""

    def __init__(self,
                 name: str,
                 ADCIndex: int,
                 ADC: None,  # For future external ADC support, currently None
                 highPin: int,
                 lowPin: int,
                 loadRating_N: float,
                 excitation_V: float,
                 sensitivity_vV: float,
                 units: str,
                 ):
        super().__init__(
            name=name,
            ADCIndex=ADCIndex,
            ADC=ADC,
            highPin=highPin,
            lowPin=lowPin,
            units=units,
        )
        self.maxWeight = loadRating_N
        self.fullScaleVoltage = excitation_V * (sensitivity_vV / 1000)  # input sensitivity in mV/V
        self.pgaGain = 8

        if self.units not in ["kg", "N", "V"]:
            raise ValueError(f"Invalid units specified: {self.units}. Valid units are 'kg', 'N', and 'V'.")

    def takeData(self, unit: str = "DEF") -> float:
        """Take a reading from the load cell and add it to the data list."""
        if self.ADC and self.ADC.pgaGain != self.pgaGain:
            self.ADC.setPGA(self.pgaGain)

        vReading = self._getVoltageReading()

        if unit == "DEF":
            readingUnit = self.units
        else:
            readingUnit = unit

        if readingUnit == "kg":
            kg = self._convertVoltageToKg(vReading)
            return kg

        if readingUnit == "N":
            n = self._convertVoltageToNewton(vReading)
            return n

        if readingUnit == "V":
            return vReading

        raise ValueError(f"Invalid unit specified: {readingUnit}. Valid units are 'kg', 'N', and 'V'.")

    def _convertVoltageToKg(self, voltage: float) -> float:
        """Convert the voltage reading to kilograms."""
        return (voltage / self.fullScaleVoltage) * (self.maxWeight / 9.805)

    def _convertVoltageToNewton(self, voltage: float) -> float:
        """Convert the voltage reading to Newtons."""
        return (voltage / self.fullScaleVoltage) * self.maxWeight
