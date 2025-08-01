"""SHT20 config flow"""
import logging
import voluptuous as vol
import asyncio
import ipaddress
import serial.tools.list_ports

from homeassistant import config_entries
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.const import CONF_HOST
from homeassistant.config_entries import OptionsFlow

from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_MODE,
    CONF_DEVICE,
    CONF_PORT,
    CONF_BAUDRATE,
    CONF_SCAN_INTERVAL,
    CONF_DEVICE_ID,
    DEFAULT_DEVICE_ID,
    DEFAULT_BAUDRATE,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    CONF_TEMP_OFFSET,
    CONF_HUM_OFFSET,
    CONF_MULTIPLIER,
    DEFAULT_MULTIPLIER,
)

_LOGGER = logging.getLogger(__name__)

MODES = ["tcp", "rtu"]
ALLOWED_BAUDRATES = [9600, 14400, 19200]
MIN_DEVICE_ID = 1
MAX_DEVICE_ID = 247

class Sht20ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def async_get_options_flow(config_entry):
        """Get the options flow for this integration"""
        return Sht20OptionsFlowHandler(config_entry)

    async def get_serial_ports():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: [port.device for port in serial.tools.list_ports.comports()])
    
    async def async_step_user(self, user_input = None):
        if user_input is not None:
            self._data = user_input.copy()
            if self._data[CONF_MODE] == "tcp":
                return await self.async_step_tcp()
            else:
                return await self.async_step_rtu()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default="SHT20 Sensor"): str,
                vol.Required(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): int,
                vol.Required(CONF_MODE, default="tcp"): vol.In(MODES),
            })
        )

    async def async_step_tcp(self, user_input=None) -> FlowResult:
        errors = {}

        if user_input is not None:
            host = user_input.get(CONF_HOST)

            # Valideer IP-adres
            try:
                ipaddress.ip_address(host)
            except ValueError:
                errors[CONF_HOST] = "invalid_ip"

            if not errors:
                self._data.update(user_input)
                return await self._create_entry()

        return self.async_show_form(
            step_id="tcp",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=self._data.get(CONF_HOST, "")): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }),
            errors=errors,
        )

    async def async_step_rtu(self, user_input=None) -> FlowResult:
        errors = {}

        async def get_serial_ports():
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, lambda: [port.device for port in serial.tools.list_ports.comports()])

            return await loop.run_in_executor(None, _list_ports)

        available_ports = await get_serial_ports()
        default_device = available_ports[0] if available_ports else ""

        if user_input is not None:
            baudrate = user_input.get(CONF_BAUDRATE)

            if baudrate not in ALLOWED_BAUDRATES:
                errors[CONF_BAUDRATE] = "invalid_baudrate"

            if not errors:
                self._data.update(user_input)
                return await self._create_entry()

        return self.async_show_form(
            step_id="rtu",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE, default=default_device): vol.In(available_ports) if available_ports else str,
                vol.Required(CONF_BAUDRATE, default=DEFAULT_BAUDRATE): vol.In(ALLOWED_BAUDRATES),
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }),
            errors=errors,
            description_placeholders={
                "no_ports_found": not available_ports
            }
        )

    async def _create_entry(self) -> FlowResult:
        from .hub import ShtModbusHub
        properties = {}

        try:
            hub = ShtModbusHub(
                self.hass,
                name=self._data[CONF_NAME],
                mode=self._data[CONF_MODE],
                unit_id=self._data[CONF_DEVICE_ID],
                host=self._data.get(CONF_HOST),
                port=self._data.get(CONF_PORT),
                device=self._data.get(CONF_DEVICE),
                baudrate=self._data.get(CONF_BAUDRATE)
            )
            await hub.connect()
            properties = await hub.read_settings()
        except Exception as e:
            _LOGGER.warning(f"Could not retrieve settings during installation.: {e}")

        _LOGGER.debug(f"SHT20 hub config: {self._data}")

        return self.async_create_entry(
            title=self._data[CONF_NAME],
            data=self._data,
            options=properties
        )

class Sht20OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry):
        self._data = dict(config_entry.data)

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            from .hub import ShtModbusHub
            try:
                device_id    = user_input.get(CONF_DEVICE_ID)
                baudrate     = user_input.get(CONF_BAUDRATE)
                temp_offset  = user_input.get(CONF_TEMP_OFFSET, 0)
                hum_offset   = user_input.get(CONF_HUM_OFFSET, 0)

                mode = self.config_entry.data.get(CONF_MODE)

                hub = ShtModbusHub(
                    self.hass,
                    name=self.config_entry.data[CONF_NAME],
                    mode=self.config_entry.data[CONF_MODE],
                    unit_id=self.config_entry.data[CONF_DEVICE_ID],
                    host=self.config_entry.data.get(CONF_HOST),
                    port=self.config_entry.data.get(CONF_PORT),
                    device=self.config_entry.data.get(CONF_DEVICE),
                    baudrate=self.config_entry.data.get(CONF_BAUDRATE),
                )
                await hub.connect()
        
                await hub.write_correction_settings(temp_offset=temp_offset, hum_offset=hum_offset)

                # Only update relevant data in the config entry
                updated_data = {**self.config_entry.data, CONF_DEVICE_ID: device_id}
                if mode == "rtu":
                    updated_data[CONF_BAUDRATE] = baudrate

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=updated_data,
                    options=user_input
    )

            except Exception as e:
                _LOGGER.warning(f"Could not write settings to sensor: {e}")

            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_ID, default=self.config_entry.options.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)): int,
                vol.Required(CONF_BAUDRATE, default=self.config_entry.options.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)): vol.In(ALLOWED_BAUDRATES),
                vol.Optional(CONF_TEMP_OFFSET, default=self.config_entry.options.get(CONF_TEMP_OFFSET, 0)): vol.Coerce(float),
                vol.Optional(CONF_HUM_OFFSET, default=self.config_entry.options.get(CONF_HUM_OFFSET, 0)): vol.Coerce(float),
                vol.Optional(CONF_MULTIPLIER, default=self.config_entry.options.get(CONF_MULTIPLIER, DEFAULT_MULTIPLIER)): vol.Coerce(float),
            })
    )