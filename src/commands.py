import asyncio
import socket
import time

import ujson

from Control import Control
from sensors.LoadCell import LoadCell
from sensors.PressureTransducer import PressureTransducer
from sensors.Thermocouple import Thermocouple


streamTask: asyncio.Task | None = None  # Task for streaming data from sensors

async def gets(sensors: dict[str, LoadCell | Thermocouple | PressureTransducer]) -> str:
    """Get a single reading from each sensor and return it as a formatted string.

    Data string format is: <acqTime:timestamp>,<sensor1_name>:value,<sensor2_name>:value,...

    """

    dataDict = {}

    acqTime = time.time()  # Get the current time in seconds since the epoch
    dataDict["acqTime"] = acqTime

    for sensor in sensors.values():
        dataDict[sensor.name] = sensor.takeData()

    # Format the data as a string
    timeString = f"time:{acqTime:.3f}"  # Format the acquisition time to 3 decimal places

    sortedKeys = sorted(dataDict.keys())
    dataString = " ".join(f"{key}:{dataDict[key]}" for key in sortedKeys if key != "acqTime")

    # Combine the time string with the data string
    payload = f"{timeString} {dataString}"

    return payload

def strm(sensors: dict[str, LoadCell | Thermocouple | PressureTransducer],
         sock: socket.socket,
         args: list[str] | None = None,
         ) -> None:
    """Start the asynchronous data streaming job."""
    if args is None:
        args = []

    global streamTask  # noqa: PLW0603

    if len(args) == 1:
        # If a frequency is specified, run sampling at that frequency
        frequency_hz: float = float(args[0])
        streamTask = asyncio.create_task(_streamData(sensors, sock, frequency_hz))

    else:
        # Otherwise, stream as fast as possible
        streamTask = asyncio.create_task(_streamData(sensors, sock, None))

def stopStrm() -> str:
    """Stop the streaming task if it is running."""
    global streamTask  # noqa: PLW0603

    if streamTask and not streamTask.done():
        streamTask.cancel()
        print("Streaming task cancelled.")
        msg = "Streaming task cancelled."
    else:
        print("No streaming task to cancel.")
        msg = "No streaming task to cancel."
    streamTask = None  # Reset the task reference
    return msg

def actuateControl(controls: dict[str, Control], args : list[str]) -> str:
    """Actuate a control (e.g., open or close a valve) based on the command arguments.

    For relay type controls, closed lets current flow, open stops current flow.
    """

    if len(args) != 2:
        return "Invalid number of arguments for control command. Usage: CONTROL <control_name> <open|close>"

    controlName, action = args
    controlName = controlName.upper()  # All commands normalized to upper case to be case-insensitive
    # Control lookup
    try:
        control = controls[controlName]
    except KeyError:
        msg = f"Control '{controlName}' not found. Valid controls are: {', '.join(controls.keys())}."
        print(msg)
        return msg

    # Actuate the control based on the action
    if action.upper() == "OPEN":
        if control.currentState == "CLOSED":
            control.open()
            msg = f"{controlName} opened"
        else:
            msg = f"{controlName} already open"

        print(msg)
        return msg

    # Close the valve if the action is "close"
    if action.upper() == "CLOSE":
        if control.currentState == "OPEN":
            msg = f"{controlName} closed"
            control.close()
        else:
            msg = f"{controlName} already closed"
            print(msg)
            return msg

        print(msg)
        return msg

    return f"Invalid action '{action}' for control '{controlName}'. Use 'OPEN' or 'CLOSE'."

def getStatus(controls: dict[str, Control]) -> str:
    status = {
        "device": "ESP32 Sensor",
        "status": "OK", # FIXME only ever okay lol
        "controls": {
        },
    }

    # Gather status information from each control
    for name, control in controls.items():
        status["controls"][name] = control.currentState.upper()

    return ujson.dumps(status)

async def _streamData(sensors: dict[str, LoadCell | Thermocouple | PressureTransducer],
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
