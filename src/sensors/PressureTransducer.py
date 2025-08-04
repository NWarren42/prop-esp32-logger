# noqa: INP001 -- Implicit namespace doesn't matter here
from sensors.Sensor import Sensor  # Importing the base Sensor class


class PressureTransducer(Sensor):
    """Class for reading pressure transducer data from an ADC."""

    def __init__(self,
                 name: str,
                 ADCIndex: int,
                 ADC: None,  # For future external ADC support, currently None
                 pinNumber: int,
                 maxPressure_PSI: int,
                 units: str,
                 ):
        super().__init__(
            name=name,
            ADCIndex=ADCIndex,
            ADC=ADC,
            highPin=pinNumber,
            lowPin=-1,
            units=units,
        )
        self.maxPressure_PSI = maxPressure_PSI

        if self.units not in ["PSI", "V"]:
            raise ValueError(f"Invalid units specified: {self.units}. Valid units are 'PSI' and 'V'.")

    def takeData(self, unit:str ="DEF") -> float:
        """Take a reading from the pressure transducer and add it to the data list."""
        vReading = self._getVoltageReading()

        if unit == "DEF":
            readingUnit = self.units
        else:
            readingUnit = unit

        if readingUnit == "V":
            self.data.append(vReading)
            return vReading

        if readingUnit == "PSI":
            psi = self._convertVoltageToPressure(vReading)
            self.data.append(psi)
            return psi

        raise ValueError(f"Invalid unit specified: {readingUnit}. Valid units are 'PSI' and 'V'.")

    def _convertVoltageToPressure(self, voltage: float) -> float:
        """Convert the voltage reading to pressure in PSI."""
        # Example conversion for 4-20mA sensor across 250R resistor (1-5V output)
        # Adjust formula as needed for your sensor
        return ((voltage - 1) / 4) * self.maxPressure_PSI

