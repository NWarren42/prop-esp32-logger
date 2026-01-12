from ADS112C04 import ADS112C04
from sensors.Sensor import Sensor


class Current(Sensor):
    """Class for taking current readings from a CSA (Current Sense Amplifier) connected to an ADS112C04 ADC."""\

    def __init__(self,
                 name: str,
                 ADCIndex: int,
                 ADC: ADS112C04 | None,  # Optional ADS112C04 instance for external ADCs. None if using the ESP32 ADC.
                 pinNumber: int,
                 shuntResistor_Ohms: float,
                 csaGain: int,
    ):
        super().__init__(
            name=name,
            ADCIndex=ADCIndex,
            ADC=ADC,
            highPin=pinNumber,
            lowPin=-1,
            units="A",
        )
        self.shuntResistor_Ohms = shuntResistor_Ohms
        self.pgaGain = -1  # Default PGA gain for the ADC, can be set later.
        self.csaGain = csaGain  # Gain of the current sense amplifier

    def takeData(self, unit: str = "DEF") -> float:
        """Take a reading from the current sensor and add it to the data list."""
        if self.ADC and self.ADC.pgaGain != self.pgaGain:
            self.ADC.setPGA(self.pgaGain)

        vReading = self._getVoltageReading()

        if unit == "DEF":
            readingUnit = self.units
        else:
            readingUnit = unit

        if readingUnit == "A":
            current = self._convertVoltageToCurrent(vReading)
            return current

        if readingUnit == "V":
            return vReading

        raise ValueError(f"Invalid unit specified: {readingUnit}. Valid units are 'A' and 'V'.")

    def _convertVoltageToCurrent(self, voltage: float) -> float:
        """Convert the voltage reading to current in Amperes."""
        return voltage / (self.shuntResistor_Ohms * self.csaGain)
