from machine import Pin  # type: ignore - MicroPython's Pin class


class Valve:
    def __init__(self,
                 name: str,
                 pin: int,
                 defaultState: str,
                 ):
        self.name = name
        self.pin = Pin(pin, Pin.OUT)
        self.defaultState = defaultState.upper()  # Normalize to upper case for consistency
        self.currentState = self.defaultState

    def open(self) -> None:
        """Open the valve based on its default state."""
        if self.defaultState == "OPEN":
            self.pin.off()
        else:
            self.pin.on()

        self.currentState = "OPEN"

    def close(self) -> None:
        """Close the valve based on its default state."""
        if self.defaultState == "CLOSED":
            self.pin.off()
        else:
            self.pin.on()

        self.currentState = "CLOSED"

