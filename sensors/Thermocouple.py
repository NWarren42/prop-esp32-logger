# noqa: INP001 -- Implicit namespace doesn't matter here
from machine import ADC, Pin  # type: ignore # These are micropython libraries


class Thermocouple:
    """Class for reading thermocouple data from an ADC.

    UNFINISHED. Don't use this yet. Need to see how the circuitry works out

    """

    def __init__ (self,
                  name: str,
                  ADCIndex: int,
                  highPin: int,
                  lowPin: int,
                  thermoType: str,
                  units: str,
                  ):

        self.name = name
        self.ADCIndex = ADCIndex # ADCIndex is the index of the ADC in the config file. 0 indicates the ESP32 ADC.
        if self.ADCIndex == 0:
            # If the ADC index is 0, use the ESP32 ADC
            self.highPin = ADC(highPin) # Pin number is the GPIO pin number. ADC constructor accepts either integer or a Pin() object.
            self.lowPin = ADC(lowPin)
        self.type = thermoType
        self.units = units

        self.data = []

    def takeData (self, units="DEF") -> float: # Currently returns differential voltage reading. DEF for default.
        """Take a reading from the thermocouple.
        Args:
            unit (str, optional): The units to return the reading in. Defaults
            to "DEF". If "DEF" is specified, the units will be the same as the
            units specified in the config file. Currently V is the only valid call.
        """
        if units == "DEF":
            units = self.units

        vReading = self.highPin.read() - self.lowPin.read()
        if units == "V":
            return (vReading/4095) * 3.3 # 4095 is the max value for the ESP32 ADC. 3.3V is the max voltage output of the ESP32 ADC.

        else:
            raise ValueError(f"Invalid unit specified: {units}. Valid units are \'V\'.")
