"""Coordinator classes for the SHT20 Modbus integration"""

import logging
from datetime import timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.helpers.update_coordinator import UpdateFailed

_LOGGER = logging.getLogger(__name__)

class RealtimeCoordinator(DataUpdateCoordinator):
    """Coordinator for the realtime temperture en humidity readings."""

    def __init__(self, hass, name, hub, scan_interval, connection_monitor=None):
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{name} Realtime",
            update_interval=timedelta(seconds=scan_interval),
        )
        self._hub = hub
        self._connection_monitor = connection_monitor

    async def _async_update_data(self):
        try:
            data = await self._hub.read_realtime_data()
        except Exception as err:
            if self._connection_monitor is not None:
                await self._connection_monitor.async_failure()
            raise UpdateFailed(f"Error retrieving real-time data {err}") from err

        _LOGGER.debug("Fetched realtime data: %s", data)
        if self._connection_monitor is not None:
            await self._connection_monitor.async_restored()
        return data


class SettingsCoordinator(DataUpdateCoordinator):
    """Coordinator for the device settings."""

    def __init__(self, hass, name, hub):
        super().__init__(
            hass,
            logger=_LOGGER,
            name=f"{name} Settings",
            update_interval=None,
        )
        self._hub = hub

    async def _async_update_data(self):
        try:
            data = await self._hub.read_settings()
        except Exception as err:
            raise UpdateFailed(f"Error retrieving settings data: {err}") from err

        _LOGGER.debug("Fetched setting data: %s", data)
        return data
