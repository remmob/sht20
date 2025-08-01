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
    CONF_MULTIPLIER,
    DEFAULT_BAUDRATE,
    DEFAULT_DEVICE_ID,
    DEFAULT_SCAN_INTERVAL,
    PLATFORMS
)

from .hub import ShtModbusHub
from .coordinator import RealtimeCoordinator, SettingsCoordinator

from .config_flow import Sht20OptionsFlowHandler

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

    if mode == "tcp":
        host = entry.data[CONF_HOST]
        port = entry.data[CONF_PORT]
        hub = ShtModbusHub(hass, name, mode, unit_id, host=host, port=port)
    else:
        device = entry.data[CONF_DEVICE]
        baudrate = entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
        hub = ShtModbusHub(hass, name, mode, unit_id, device=device, baudrate=baudrate)

    realtime_coordinator = RealtimeCoordinator(hass, name, hub, scan_interval)
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
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_get_options_flow(config_entry: ConfigEntry,) -> Sht20OptionsFlowHandler:
    """Get the options flow for this integration."""
    return Sht20OptionsFlowHandler(config_entry)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
