# noqa: INP001 -- Implicit namespace doesn't matter here
from machine import ADC, Pin  # type: ignore # These are micropython libraries


class LoadCell:

    def __init__ (self,
                  name: str,
                  ADCIndex: int,
                  highPin: int,
                  lowPin: int,
                  loadRating_N: float,
                  excitation_V: float,
                  sensitivity_vV: float,
                  units: str,
                  ):

        self.name = name
        self.ADCIndex = ADCIndex # ADCIndex is the index of the ADC in the config file. 0 indicates the ESP32 ADC.
        if self.ADCIndex == 0:
            # If the ADC index is 0, use the ESP32 ADC
            self.highPin = ADC(highPin) # Pin number is the GPIO pin number. ADC constructor accepts either integer or a Pin() object.
            self.lowPin = ADC(lowPin)
        self.maxWeight = loadRating_N
        self.units = units

        self.fullScaleVoltage = excitation_V * (sensitivity_vV/1000) # input sensitivity in units of mv/V in the config file

        self.data = []

    def takeData (self, units="DEF") -> float | int: # If no units are specified, return voltage reading
        """Take a reading from the load cell.

        Args:
            unit (str, optional): The units to return the reading in. Defaults
            to "DEF". If "DEF" is specified, the units will be the same as the
            units specified in the config file. kg, N and V are also valid calls.
        """
        if units == "DEF":
            units = self.units

        vReading: int = self.highPin.read() - self.lowPin.read() # Differential voltage reading

        if units == 'kg':
            return (vReading/self.fullScaleVoltage)*(self.maxWeight/9.805)
        if units == 'N':
            return (vReading/self.fullScaleVoltage)*(self.maxWeight)
        if units == 'V':
            return (vReading/4095) * 3.3 # 4095 is the max value for the ESP32 ADC. 3.3V is the max voltage output of the ESP32 ADC.
        else:
            raise ValueError(f"Invalid unit specified: {units}. Valid units are \'kg\', \'N\' and \'V\'.")
