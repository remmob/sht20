"""Reads and writes the SHT20 over a Modbus unit.

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
"""

from __future__ import annotations

import asyncio
import logging

from modbus_connection import ModbusError, ModbusTimeoutError, ModbusUnit

from .const import (
    BAUDRATE_CODES,
    BAUDRATE_VALUES,
    MAX_READ_RETRIES,
    RETRY_DELAY_SECONDS,
    STUCK_LINK_TIMEOUTS,
)
from .device import Sht20Device

_LOGGER = logging.getLogger(__name__)


class ShtModbusHub:
    """Thin layer around the sensor's register model."""

    def __init__(self, name: str, unit: ModbusUnit, unit_id: int) -> None:
        self.name = name
        # Kept only to know which address we are talking to, for logging and
        # when changing the device ID.
        self.unit_id = unit_id
        self._unit = unit
        self._device = Sht20Device(unit)
        # Number of consecutive polls that ended in a timeout. See
        # read_realtime_data() for where this resets and what happens when
        # the counter fills up.
        self._consecutive_timeouts = 0

    # ------------------------------------------------------------------ read

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

    async def read_realtime_data(self) -> dict:
        """Read temperature and humidity as raw register values.

        The dict keys are relied on by sensor.py to build its entities;
        renaming them would give every sensor a new entity ID.
        """
        # The stuck-link counter is deliberately only incremented here and
        # not in read_settings(): count on a single coordinator, the one
        # with the fastest interval, otherwise a second coordinator could
        # cut off a poll that is already in flight. Settings are only read
        # on demand, readings on every scan_interval.
        try:
            await self._update_with_retry(self._device.readings, "readings")
        except ModbusTimeoutError:
            # Only timeouts count. A ModbusConnectionError means the library
            # already noticed the dropped connection itself and will recover
            # on the next poll without help.
            self._consecutive_timeouts += 1
            if self._consecutive_timeouts >= STUCK_LINK_TIMEOUTS:
                _LOGGER.warning(
                    "%s consecutive polls timed out; the connection appears "
                    "stuck. Disconnecting so the next poll opens a fresh "
                    "connection.",
                    self._consecutive_timeouts,
                )
                await self._unit.disconnect()
                # Reset to zero, otherwise every following poll would
                # disconnect again and a fresh connection would never get a
                # chance to prove itself.
                self._consecutive_timeouts = 0
            raise

        self._consecutive_timeouts = 0

        return {
            "temperature": self._device.readings.temperature,
            "humidity": self._device.readings.humidity,
        }

    async def read_settings(self) -> dict:
        """Read the four settings stored in the sensor itself."""
        await self._update_with_retry(self._device.settings, "settings")
        settings = self._device.settings

        return {
            "device_id": settings.device_id,
            "baudrate": self._decode_baudrate(settings.baudrate_raw),
            "temp_offset": settings.temp_offset,
            "hum_offset": settings.hum_offset,
        }

    # -------------------------------------------------------------- write

    async def write_correction_settings(
        self, temp_offset: float, hum_offset: float
    ) -> None:
        """Write the two correction values to the sensor."""
        await self._device.settings.write("temp_offset", temp_offset)
        await self._device.settings.write("hum_offset", hum_offset)

    async def write_device_id(self, device_id: int) -> None:
        """Write a new Modbus address to the sensor.

        This is the most sensitive operation in the integration: after this
        write, the sensor listens on a different address, and this hub's
        unit still points at the old one. Anything that still needs to talk
        to the sensor must request a new unit at the new address — the
        caller in config_flow.py does this after calling write_device_id().
        This is why it is split from write_baudrate().
        """
        _LOGGER.debug("Writing new device ID %s (was %s)", device_id, self.unit_id)
        await self._device.settings.write("device_id", device_id)

    async def write_baudrate(self, baudrate: int) -> None:
        """Write a new baud rate to the sensor.

        This breaks the connection until the gateway is set to the same
        speed, so it must always happen last.
        """
        if baudrate not in BAUDRATE_VALUES:
            raise ValueError(f"Unsupported baudrate: {baudrate}")

        await self._device.settings.write(
            "baudrate_raw", await self._encode_baudrate(baudrate)
        )

    # ---------------------------------------------------- baudrate translation

    @staticmethod
    def _decode_baudrate(raw: int | None) -> int | None:
        """Convert the raw register value to a baud rate.

        Some sensors store 9600 directly, others store the code 0. A known
        baud rate wins if present; otherwise the value is read as a code.
        """
        if raw is None:
            return None
        if raw in BAUDRATE_VALUES:
            return raw

        baudrate = BAUDRATE_CODES.get(raw)
        if baudrate is None:
            _LOGGER.warning("Unknown baudrate in the settings register: %s", raw)
        return baudrate

    async def _encode_baudrate(self, baudrate: int) -> int:
        """Work out what to write to the register, in this device's format.

        We first read what is currently stored to see which of the two
        formats this sensor uses, then write back in that same format.
        """
        await self._device.settings.async_update()
        current = self._device.settings.baudrate_raw

        if current in BAUDRATE_CODES:
            # This sensor stores a code instead of the baud rate itself
            return BAUDRATE_VALUES[baudrate]
        return baudrate
