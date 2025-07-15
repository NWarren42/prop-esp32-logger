import asyncio
import socket

from sensors.LoadCell import LoadCell
from sensors.PressureTransducer import PressureTransducer
from sensors.Thermocouple import Thermocouple
from Valve import Valve


streamTask: asyncio.Task | None = None  # Task for streaming data from sensors

async def gets(sensors: list[LoadCell | Thermocouple | PressureTransducer]) -> str:
    """Get a single reading from each sensor and return it as a formatted string."""
    data = " ".join(str(sensor.takeData()) for sensor in sensors)
    return data

def strm(sensors: list[LoadCell | Thermocouple | PressureTransducer],
         sock: socket.socket,
         args: list[str] = [],
         ) -> None:
    """Start the asynchronous data streaming job."""
    global streamTask

    if len(args) == 1:
        # If a frequency is specified, run sampling at that frequency
        frequency_hz: float = float(args[0])
        streamTask = asyncio.create_task(_streamData(sensors, sock, frequency_hz))

    else:
        # Otherwise, stream as fast as possible
        streamTask = asyncio.create_task(_streamData(sensors, sock, None))

def stopStrm() -> str:
    """Stop the streaming task if it is running."""
    global streamTask

    if streamTask and not streamTask.done():
        streamTask.cancel()
        print("Streaming task cancelled.")
        msg = "Streaming task cancelled."
    else:
        print("No streaming task to cancel.")
        msg = "No streaming task to cancel."
    streamTask = None  # Reset the task reference
    return msg

def actuateValve(valves: dict[str, Valve], args : list[str]) -> str:

    if len(args) != 2:
        return "Invalid number of arguments for valve command. Usage: VALVE <valve_name> <open|close>"

    valveName, action = args
    valveName = valveName.upper()  # All commands normalized to upper case to be case-insensitive
    # Valve lookup
    try:
        valve = valves[valveName]
    except KeyError:
        msg = f"Valve '{valveName}' not found. Valid valves are: {', '.join(valves.keys())}."
        print(msg)
        return msg

    # Actuate the valve based on the action
    if action.upper() == "OPEN":
        if valve.currentState == "CLOSED":
            valve.open()
            msg = f"{valveName} opened"
        else:
            msg = f"{valveName} already open"

        print(msg)
        return msg

    # Close the valve if the action is "close"
    if action.upper() == "CLOSE":
        if valve.currentState == "OPEN":
            msg = f"{valveName} closed"
            valve.close()
        else:
            msg = f"{valveName} already closed"
            print(msg)
            return msg

        print(msg)
        return msg

    else:
        return f"Invalid action '{action}' for valve '{valveName}'. Use 'OPEN' or 'CLOSE'."


async def _streamData(sensors: list[LoadCell | Thermocouple | PressureTransducer],
                      sock: socket.socket,
                      frequency_hz: float | None,
                     ) -> None:
    """Asynchronous Helper function to stream data from sensors."""

    print(f"Streaming freq:{frequency_hz}")

    try:
        while True:
            data = "STRM " + await gets(sensors) + "\n" # Attach "STRM" prefix to the data
            sock.sendall(data.encode("utf-8"))

            # If no frequency is specified, stream as fast as possible
            if frequency_hz is not None:
                await asyncio.sleep(1 / frequency_hz)

            # Give a chance to check for cancellation
            await asyncio.sleep(0)
    except asyncio.CancelledError:
        print("Streaming task cancelled.")
