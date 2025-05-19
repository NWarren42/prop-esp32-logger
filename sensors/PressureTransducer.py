# noqa: INP001 -- Implicit namespace doesn't matter here
from machine import ADC, Pin  # type: ignore # These are micropython libraries


class PressureTransducer:

    def __init__ (self,
                  name: str,
                  ADCIndex: int,
                  pinNumber: int,
                  maxPressure_PSI: int,
                  units: str,
                  ):

        self.name = name
        self.ADCIndex = ADCIndex # ADCIndex is the index of the ADC in the config file. 0 indicates the ESP32 ADC.
        if self.ADCIndex == 0:
            self.pin = ADC(pinNumber) # Pin number is the GPIO pin number. ADC constructor accepts either integer or a Pin() object.
        self.maxPressure_PSI = maxPressure_PSI
        self.units = units

        self.data = []


    def takeData (self, unit="DEF") -> float | int: # If no units are specified, return voltage reading. DEF for default.
        """Take a reading from the pressure transducer.

        Args:
            unit (str, optional): The units to return the reading in. Defaults
            to "DEF". If "DEF" is specified, the units will be the same as the
            units specified in the config file. PSI and V are also valid calls.
        """
        if unit == "DEF":
            unit = self.units

        vReading: int = self.pin.read() # Sensor voltage reading
        if unit == "PSI":
            return ((vReading-1)/4)*(self.maxPressure_PSI) # output is 4-20mA across a 250R resistor so we have a 4V range (1-5V).
                                                           # Subtracting 1 because 1 is the minimum voltage output and we need to set the floor
        if unit == "V":
            return (vReading/4095) * 3.3 # 4095 is the max value for the ESP32 ADC. 3.3V is the max voltage output of the ESP32 ADC.

        else:
            raise ValueError(f"Invalid unit specified: {unit}. Valid units are \'PSI\' and \'V\'.")
