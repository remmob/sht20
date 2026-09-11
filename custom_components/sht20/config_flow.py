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
from homeassistant.helpers import selector

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
    DEFAULT_TEMP_OFFSET,
    DEFAULT_HUM_OFFSET,
    CONF_MULTIPLIER,
    DEFAULT_MULTIPLIER,
    CONF_PRESSURE,
    DEFAULT_PRESSURE,
    BAUDRATE_CODES,
    CONF_NOTIFY_CONNECTION_ERRORS_MOBILE,
    CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
    CONF_NOTIFY_CONNECTION_ERRORS_SERVICES,
    CONF_CONNECTION_ERROR_NOTIFICATION_TITLE,
    CONF_CONNECTION_ERROR_DELAY,
    CONF_NOTIFY_RECOVERY,
    CONF_QUIET_HOURS_ENABLED,
    CONF_QUIET_HOURS_START,
    CONF_QUIET_HOURS_END,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT,
    DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES,
    DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE,
    DEFAULT_CONNECTION_ERROR_DELAY,
    DEFAULT_NOTIFY_RECOVERY,
    DEFAULT_QUIET_HOURS_ENABLED,
    DEFAULT_QUIET_HOURS_START,
    DEFAULT_QUIET_HOURS_END,
)

_LOGGER = logging.getLogger(__name__)

MODES = ["tcp", "udp", "rtu"]
# Both network modes use the same host/port form
NETWORK_MODES = ("tcp", "udp")
ALLOWED_BAUDRATES = list(BAUDRATE_CODES.values())
MIN_DEVICE_ID = 1
MAX_DEVICE_ID = 247

# A plain number box with arrows, so it does not render as a slider
DEVICE_ID_SELECTOR = selector.NumberSelector(
    selector.NumberSelectorConfig(
        min=MIN_DEVICE_ID,
        max=MAX_DEVICE_ID,
        step=1,
        mode=selector.NumberSelectorMode.BOX,
    )
)

def _get_notify_service_options(hass) -> list:
    """Return the notify services of the registered mobile apps."""
    services = hass.services.async_services().get("notify", {})
    return sorted(name for name in services if name.startswith("mobile_app_"))

def _services_default(value) -> list:
    """Turn a stored comma separated string back into a list for the selector."""
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        return [s.strip() for s in value.split(",") if s.strip()]
    return []

def _normalize_services(value) -> str:
    """Store the selected services as a comma separated string."""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    return str(value).strip() if value else ""

def _notify_services_selector(hass) -> selector.SelectSelector:
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=_get_notify_service_options(hass),
            multiple=True,
            custom_value=True,
            mode=selector.SelectSelectorMode.DROPDOWN,
        )
    )

BAUDRATE_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[str(baudrate) for baudrate in ALLOWED_BAUDRATES],
        mode=selector.SelectSelectorMode.DROPDOWN,
    )
)

class Sht20ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this integration"""
        return Sht20OptionsFlowHandler(config_entry)

    async def async_step_user(self, user_input = None):
        if user_input is not None:
            self._data = user_input.copy()
            # A number selector hands back a float
            self._data[CONF_DEVICE_ID] = int(self._data[CONF_DEVICE_ID])
            if self._data[CONF_MODE] == "udp":
                return await self.async_step_udp()
            if self._data[CONF_MODE] == "tcp":
                return await self.async_step_tcp()
            return await self.async_step_rtu()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_NAME, default="SHT20 Sensor"): str,
                vol.Required(CONF_DEVICE_ID, default=DEFAULT_DEVICE_ID): DEVICE_ID_SELECTOR,
                vol.Required(CONF_MODE, default="tcp"): vol.In(MODES),
            })
        )

    async def async_step_tcp(self, user_input=None) -> FlowResult:
        return await self._async_step_network("tcp", user_input)

    async def async_step_udp(self, user_input=None) -> FlowResult:
        return await self._async_step_network("udp", user_input)

    async def _async_step_network(self, step_id: str, user_input) -> FlowResult:
        """Host and port form, shared by the tcp and udp modes."""
        errors = {}

        if user_input is not None:
            host = user_input.get(CONF_HOST)

            try:
                ipaddress.ip_address(host)
            except ValueError:
                errors[CONF_HOST] = "invalid_ip"

            if not errors:
                self._data.update(user_input)
                return await self._create_entry()

        return self.async_show_form(
            step_id=step_id,
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

        available_ports = await get_serial_ports()
        default_device = available_ports[0] if available_ports else ""

        if user_input is not None:
            # The selector hands back a string
            try:
                baudrate = int(user_input.get(CONF_BAUDRATE))
            except (TypeError, ValueError):
                baudrate = None

            if baudrate not in ALLOWED_BAUDRATES:
                errors[CONF_BAUDRATE] = "invalid_baudrate"

            if not errors:
                self._data.update(user_input)
                self._data[CONF_BAUDRATE] = baudrate
                return await self._create_entry()

        return self.async_show_form(
            step_id="rtu",
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE, default=default_device): vol.In(available_ports) if available_ports else str,
                vol.Required(CONF_BAUDRATE, default=str(DEFAULT_BAUDRATE)): BAUDRATE_SELECTOR,
                vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): int,
            }),
            errors=errors,
            description_placeholders={
                "no_ports_found": not available_ports
            }
        )

    async def _create_entry(self) -> FlowResult:
        _LOGGER.debug(f"SHT20 hub config: {self._data}")

        return self.async_create_entry(
            title=self._data[CONF_NAME],
            data=self._data,
            options={},
        )

class Sht20OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry):
        self._data = dict(config_entry.data)

    async def async_step_init(self, user_input=None):
        mode = self.config_entry.data.get(CONF_MODE)
        options = self.config_entry.options

        current_device_id = self.config_entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)
        current_scan_interval = self.config_entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        current_temp_offset = self.config_entry.options.get(CONF_TEMP_OFFSET, DEFAULT_TEMP_OFFSET)
        current_hum_offset  = self.config_entry.options.get(CONF_HUM_OFFSET, DEFAULT_HUM_OFFSET)

        current_baudrate = self.config_entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)
        if current_baudrate not in ALLOWED_BAUDRATES:
            current_baudrate = DEFAULT_BAUDRATE

        if user_input is not None:
            # The selectors hand back a float and a string
            device_id = int(user_input.get(CONF_DEVICE_ID, current_device_id))
            baudrate  = int(user_input.get(CONF_BAUDRATE, current_baudrate))
            scan_interval = int(user_input.get(CONF_SCAN_INTERVAL, current_scan_interval))

            # Store the normalised values instead of what the selectors returned
            user_input = {
                **user_input,
                CONF_DEVICE_ID: device_id,
                CONF_BAUDRATE: baudrate,
                CONF_SCAN_INTERVAL: scan_interval,
                CONF_NOTIFY_CONNECTION_ERRORS_SERVICES: _normalize_services(
                    user_input.get(CONF_NOTIFY_CONNECTION_ERRORS_SERVICES)
                ),
            }

            # device_id/baudrate/scan_interval are connection parameters, not
            # sensor state - this never writes to the sensor. Changing the
            # sensor's own address or baud rate (so it matches what is
            # entered here) is done outside Home Assistant.
            updated_data = {
                **self.config_entry.data,
                CONF_DEVICE_ID: device_id,
                CONF_BAUDRATE: baudrate,
                CONF_SCAN_INTERVAL: scan_interval,
            }

            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=updated_data,
            )

            return self.async_create_entry(title="", data=user_input)

        schema_fields = {
            vol.Required(CONF_DEVICE_ID, default=current_device_id): DEVICE_ID_SELECTOR,
        }
        if mode == "rtu":
            # Baud rate only matters for a direct serial connection; a
            # TCP/UDP gateway's own baud rate towards the sensor is not
            # something Home Assistant talks to.
            schema_fields[vol.Required(CONF_BAUDRATE, default=str(current_baudrate))] = BAUDRATE_SELECTOR
        schema_fields.update({
            vol.Optional(CONF_SCAN_INTERVAL, default=current_scan_interval): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
            vol.Optional(CONF_TEMP_OFFSET, default=current_temp_offset): vol.Coerce(float),
            vol.Optional(CONF_HUM_OFFSET, default=current_hum_offset): vol.Coerce(float),
            vol.Optional(CONF_MULTIPLIER, default=self.config_entry.options.get(CONF_MULTIPLIER, DEFAULT_MULTIPLIER)): vol.Coerce(float),
            vol.Optional(CONF_PRESSURE, default=self.config_entry.options.get(CONF_PRESSURE, DEFAULT_PRESSURE)): vol.Coerce(float),

            # Connection error notifications
            vol.Optional(CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT, default=options.get(CONF_NOTIFY_CONNECTION_ERRORS_PERSISTENT, DEFAULT_NOTIFY_CONNECTION_ERRORS_PERSISTENT)): bool,
            vol.Optional(CONF_NOTIFY_CONNECTION_ERRORS_MOBILE, default=options.get(CONF_NOTIFY_CONNECTION_ERRORS_MOBILE, DEFAULT_NOTIFY_CONNECTION_ERRORS_MOBILE)): bool,
            vol.Optional(CONF_NOTIFY_CONNECTION_ERRORS_SERVICES, default=_services_default(options.get(CONF_NOTIFY_CONNECTION_ERRORS_SERVICES, DEFAULT_NOTIFY_CONNECTION_ERRORS_SERVICES))): _notify_services_selector(self.hass),
            vol.Optional(CONF_CONNECTION_ERROR_NOTIFICATION_TITLE, default=options.get(CONF_CONNECTION_ERROR_NOTIFICATION_TITLE, DEFAULT_CONNECTION_ERROR_NOTIFICATION_TITLE)): str,
            vol.Optional(CONF_CONNECTION_ERROR_DELAY, default=options.get(CONF_CONNECTION_ERROR_DELAY, DEFAULT_CONNECTION_ERROR_DELAY)): vol.All(vol.Coerce(int), vol.Range(min=0)),
            vol.Optional(CONF_NOTIFY_RECOVERY, default=options.get(CONF_NOTIFY_RECOVERY, DEFAULT_NOTIFY_RECOVERY)): bool,

            # Quiet hours
            vol.Optional(CONF_QUIET_HOURS_ENABLED, default=options.get(CONF_QUIET_HOURS_ENABLED, DEFAULT_QUIET_HOURS_ENABLED)): bool,
            vol.Optional(CONF_QUIET_HOURS_START, default=options.get(CONF_QUIET_HOURS_START, DEFAULT_QUIET_HOURS_START)): selector.TimeSelector(),
            vol.Optional(CONF_QUIET_HOURS_END, default=options.get(CONF_QUIET_HOURS_END, DEFAULT_QUIET_HOURS_END)): selector.TimeSelector(),
        })

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(schema_fields),
        )