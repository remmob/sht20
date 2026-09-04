"""Reads the SHT20 over a Modbus unit.

Two things worth knowing that are not obvious from the code:

Retries: modbus_connection reconnects automatically after a dropped
connection, but it does NOT retry timeouts or other exception responses
(only a SERVER_DEVICE_BUSY response is retried). `_update_with_retry` below
provides that retry ourselves — without it, a single glitch would surface as
a connection error, since ConnectionMonitor can be configured with a delay
as low as one scan interval.

Stuck-link detection: a Modbus line can fail in two ways. If the connection
itself drops (cable pulled, gateway restarted, TCP reset), the library
notices and reconnects on the next poll — nothing for us to do. But a
network-to-serial bridge (e.g. an Elfin EW-11) can keep a socket open while
the device behind it stops responding; the socket looks healthy so nothing
triggers a reconnect, and every read just times out on the same dead link.
`_consecutive_timeouts` in `read_realtime_data` detects that pattern and
forces a disconnect so the next poll opens a fresh connection.

Plausibility check: when this sensor shares a Modbus gateway with another
device polled via a different register space (e.g. a holding-register device
on the same RS485 bus), a read can come back corrupted without raising any
exception - it just decodes into a valid-looking but wrong int16. That shows
up as the value jumping around from poll to poll. `_is_plausible` rejects a
jump bigger than MAX_TEMPERATURE_STEP/MAX_HUMIDITY_STEP and retries within
the same poll; `_implausible_streak` stops that from freezing the sensor
forever if a jump that size ever turns out to be real.

Device ID and baud rate are connection parameters only (config entry data),
never read from or written to the sensor: this hardware does not reliably
apply a write to its own settings registers (confirmed while debugging the
temperature/humidity correction, which is why those moved to sensor.py
instead). Changing the sensor's own address or baud rate is done outside
Home Assistant; the integration only needs to be told the current values so
it can connect.
"""

from __future__ import annotations

import asyncio
import logging

from modbus_connection import ModbusError, ModbusTimeoutError, ModbusUnit

from .const import (
    MAX_HUMIDITY_STEP,
    MAX_IMPLAUSIBLE_POLLS,
    MAX_READ_RETRIES,
    MAX_TEMPERATURE_STEP,
    RETRY_DELAY_SECONDS,
    STUCK_LINK_TIMEOUTS,
)
from .device import Sht20Readings

_LOGGER = logging.getLogger(__name__)


class ShtModbusHub:
    """Thin layer around the sensor's register model."""

    def __init__(self, name: str, unit: ModbusUnit, unit_id: int) -> None:
        self.name = name
        # Kept only for logging - which address we are talking to.
        self.unit_id = unit_id
        self._unit = unit
        self._readings = Sht20Readings(unit)
        # Number of consecutive polls that ended in a timeout. See
        # read_realtime_data() for where this resets and what happens when
        # the counter fills up.
        self._consecutive_timeouts = 0
        # Last known good raw readings, used by _is_plausible() to reject a
        # corrupted decode. None until the first successful read.
        self._last_temperature: int | None = None
        self._last_humidity: int | None = None
        # Number of consecutive polls where no attempt looked plausible. See
        # read_realtime_data() for where this resets and what happens when
        # the counter fills up.
        self._implausible_streak = 0

    async def _update_with_retry(self, component, what: str) -> None:
        """Update a component, retrying timeouts since the library does not."""
        last_error: ModbusError | None = None

        for attempt in range(MAX_READ_RETRIES):
            try:
                await component.async_update()
                return
            except ModbusError as err:
                last_error = err
                _LOGGER.debug(
                    "Reading %s failed (attempt %s/%s): %s",
                    what, attempt + 1, MAX_READ_RETRIES, err,
                )
                if attempt < MAX_READ_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        _LOGGER.warning(
            "Reading %s failed after %s attempts: %s",
            what, MAX_READ_RETRIES, last_error,
        )
        raise last_error

    def _is_plausible(self, temperature: int, humidity: int) -> bool:
        """Reject a jump too large to be real between consecutive polls.

        Nothing to compare against on the very first read, so that one is
        always accepted.
        """
        if self._last_temperature is None or self._last_humidity is None:
            return True
        return (
            abs(temperature - self._last_temperature) <= MAX_TEMPERATURE_STEP
            and abs(humidity - self._last_humidity) <= MAX_HUMIDITY_STEP
        )

    async def read_realtime_data(self) -> dict:
        """Read temperature and humidity as raw register values.

        The dict keys are relied on by sensor.py to build its entities;
        renaming them would give every sensor a new entity ID.
        """
        temperature = humidity = None

        for attempt in range(MAX_READ_RETRIES):
            try:
                await self._update_with_retry(self._readings, "readings")
            except ModbusTimeoutError:
                # Only timeouts count. A ModbusConnectionError means the
                # library already noticed the dropped connection itself and
                # will recover on the next poll without help.
                self._consecutive_timeouts += 1
                if self._consecutive_timeouts >= STUCK_LINK_TIMEOUTS:
                    _LOGGER.warning(
                        "%s consecutive polls timed out; the connection "
                        "appears stuck. Disconnecting so the next poll opens "
                        "a fresh connection.",
                        self._consecutive_timeouts,
                    )
                    await self._unit.disconnect()
                    # Reset to zero, otherwise every following poll would
                    # disconnect again and a fresh connection would never get
                    # a chance to prove itself.
                    self._consecutive_timeouts = 0
                raise

            self._consecutive_timeouts = 0
            temperature = self._readings.temperature
            humidity = self._readings.humidity

            if self._is_plausible(temperature, humidity):
                self._implausible_streak = 0
                break

            _LOGGER.warning(
                "%s: implausible reading temperature=%s humidity=%s (last "
                "temperature=%s humidity=%s) - likely bus corruption from "
                "shared Modbus traffic; retrying (attempt %s/%s)",
                self.name, temperature, humidity,
                self._last_temperature, self._last_humidity,
                attempt + 1, MAX_READ_RETRIES,
            )
            if attempt < MAX_READ_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)
        else:
            self._implausible_streak += 1
            if self._implausible_streak >= MAX_IMPLAUSIBLE_POLLS:
                _LOGGER.warning(
                    "%s: %s consecutive polls without a plausible reading; "
                    "accepting the last one as the new baseline in case it "
                    "is a real change.",
                    self.name, self._implausible_streak,
                )
                self._implausible_streak = 0
            else:
                _LOGGER.warning(
                    "%s: no plausible reading after %s attempts; keeping "
                    "last known good value (temperature=%s humidity=%s).",
                    self.name, MAX_READ_RETRIES,
                    self._last_temperature, self._last_humidity,
                )
                temperature = self._last_temperature
                humidity = self._last_humidity

        self._last_temperature = temperature
        self._last_humidity = humidity

        return {"temperature": temperature, "humidity": humidity}
