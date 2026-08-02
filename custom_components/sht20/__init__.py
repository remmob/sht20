"""Initialize the SHT20 Modbus integration"""

import logging
import asyncio
import pymodbus
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_NAME, CONF_PORT
from homeassistant.helpers import device_registry as dr

from .const import (
    DOMAIN,
    CONF_MODE,
    CONF_DEVICE,
    CONF_DEVICE_ID,
    CONF_BAUDRATE,
    CONF_SCAN_INTERVAL,
    DEFAULT_BAUDRATE,
    DEFAULT_DEVICE_ID,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS
)

from .hub import ShtModbusHub
from .coordinator import RealtimeCoordinator, SettingsCoordinator
from .connection_monitor import ConnectionMonitor

_LOGGER = logging.getLogger(__name__)


async def async_setup(_hass: HomeAssistant, _config: dict) -> bool:
    """Set up the integration via YAML (not supported)."""
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up SHT20 Modbus from a config entry."""
    _LOGGER.debug(f"Gebruikte pymodbus versie: {pymodbus.__version__}")
    hass.data.setdefault(DOMAIN, {})

    name = entry.data[CONF_NAME]
    mode = entry.data[CONF_MODE]
    unit_id = entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)
    scan_interval = entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)

    if mode in ("tcp", "udp"):
        host = entry.data[CONF_HOST]
        port = entry.data[CONF_PORT]
        hub = ShtModbusHub(hass, name, mode, unit_id, host=host, port=port)
    else:
        device = entry.data[CONF_DEVICE]
        baudrate = entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
        hub = ShtModbusHub(hass, name, mode, unit_id, device=device, baudrate=baudrate)

    connection_monitor = ConnectionMonitor(hass, name, dict(entry.options), scan_interval)
    connection_monitor.start()

    realtime_coordinator = RealtimeCoordinator(
        hass, name, hub, scan_interval, connection_monitor
    )
    settings_coordinator = SettingsCoordinator(hass, name, hub)

    await realtime_coordinator.async_config_entry_first_refresh()
    await asyncio.sleep(1)
    await settings_coordinator.async_refresh()

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, f"{entry.entry_id}")},
        manufacturer="SHTech",
        name=name,
        model="SHT20",
    )

    hass.data[DOMAIN][entry.entry_id] = {
        "hub": hub,
        "realtime": realtime_coordinator,
        "settings": settings_coordinator,
        "connection_monitor": connection_monitor,
    }

    # Reload on changes so a new multiplier, pressure or device ID takes effect
    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry after the settings changed."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        entry_data = hass.data[DOMAIN].pop(entry.entry_id, {})
        monitor = entry_data.get("connection_monitor")
        if monitor is not None:
            monitor.stop()
        hub = entry_data.get("hub")
        if hub is not None:
            await hub.close()
    return unload_ok
