import asyncio
import socket

from sensors.LoadCell import LoadCell
from sensors.PressureTransducer import PressureTransducer
from sensors.Thermocouple import Thermocouple


streamTask: asyncio.Task | None = None  # Task for streaming data from sensors

async def gets(sensors: list[LoadCell | Thermocouple | PressureTransducer],
         sock: socket.socket,
         ) -> str:
    """Get a single reading from each sensor and return it as a formatted string."""
    data = " ".join(str(sensor.takeData()) for sensor in sensors)
    return data

def strm(sensors: list[LoadCell | Thermocouple | PressureTransducer],
         sock: socket.socket,
         frequency_hz: float | None = None,
         ) -> None:
    """Start the asynchronous data streaming job."""

    global streamTask
    streamTask = asyncio.create_task(_streamData(sensors, sock, frequency_hz))

def stopStrm() -> None:
    """Stop the streaming task if it is running."""
    global streamTask
    if streamTask and not streamTask.done():
        streamTask.cancel()
        print("Streaming task cancelled.")
    else:
        print("No streaming task to cancel.")
    streamTask = None  # Reset the task reference


async def _streamData(sensors: list[LoadCell | Thermocouple | PressureTransducer],
                      sock: socket.socket,
                      frequency_hz: float | None,
                     ) -> None:
    """Asynchronous Helper function to stream data from sensors."""

    try:
        while True:
            data = "STRM " + await gets(sensors, sock) + "\n" # Attach "STRM" prefix to the data
            sock.sendall(data.encode("utf-8"))

            # If no frequency is specified, stream as fast as possible
            if frequency_hz is not None:
                await asyncio.sleep(1 / frequency_hz)

            # Give a chance to check for cancellation
            await asyncio.sleep(0)
    except asyncio.CancelledError:
        print("Streaming task cancelled.")
