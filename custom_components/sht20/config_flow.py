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


# A dropdown with the current value preselected. The frontend compares option
# values as strings, so the options and the default have to be strings too.
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

    async def get_serial_ports():
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: [port.device for port in serial.tools.list_ports.comports()])
    
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

            # Valideer IP-adres
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
        # UITLEG: Hier werd een tweede, eigen hub opgebouwd om de sensor even uit
        # te lezen tijdens de installatie, met een `await hub.connect()` erbij.
        # Nu vragen we een tijdelijke unit aan.
        #
        # Het verschil is groter dan het lijkt: op HA 2026.9+ lift die tijdelijke
        # unit mee op een verbinding die al openstaat naar dezelfde gateway, in
        # plaats van er een tweede socket naast te zetten. Precies het probleem
        # dat een Elfin EW-11 niet aankan.
        from .connection import build_params, temporary_unit
        from .hub import ShtModbusHub

        properties = {}
        unit_id = self._data[CONF_DEVICE_ID]

        try:
            async with temporary_unit(
                self.hass, build_params(self._data), unit_id
            ) as unit:
                hub = ShtModbusHub(self._data[CONF_NAME], unit, unit_id)
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

    def _sensor_settings(self):
        """Return the settings as last read from the sensor, empty when unknown."""
        entry_data = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
        if entry_data:
            coordinator = entry_data.get("settings")
            if coordinator and coordinator.data:
                return coordinator.data
        return {}

    async def async_step_init(self, user_input=None):
        errors = {}

        mode = self.config_entry.data.get(CONF_MODE)
        options = self.config_entry.options

        if user_input is None:
            # Refresh first, so the form shows what the sensor currently holds
            entry_data = self.hass.data.get(DOMAIN, {}).get(self.config_entry.entry_id)
            if entry_data and entry_data.get("settings"):
                await entry_data["settings"].async_refresh()

        settings = self._sensor_settings()

        current_device_id   = settings.get("device_id") or self.config_entry.data.get(CONF_DEVICE_ID, DEFAULT_DEVICE_ID)
        current_temp_offset = settings.get("temp_offset", self.config_entry.options.get(CONF_TEMP_OFFSET, 0))
        current_hum_offset  = settings.get("hum_offset", self.config_entry.options.get(CONF_HUM_OFFSET, 0))

        # What the sensor reported wins, but only when it is a known baud rate
        current_baudrate = settings.get(CONF_BAUDRATE)
        if current_baudrate not in ALLOWED_BAUDRATES:
            current_baudrate = self.config_entry.options.get(CONF_BAUDRATE)
        if current_baudrate not in ALLOWED_BAUDRATES:
            current_baudrate = self.config_entry.data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)

        if user_input is not None:
            from .connection import build_params, temporary_unit
            from .hub import ShtModbusHub

            # The selectors hand back a float and a string
            device_id   = int(user_input.get(CONF_DEVICE_ID, current_device_id))
            baudrate    = int(user_input.get(CONF_BAUDRATE, current_baudrate))
            temp_offset = user_input.get(CONF_TEMP_OFFSET, 0)
            hum_offset  = user_input.get(CONF_HUM_OFFSET, 0)

            # Store the normalised values instead of what the selectors returned
            user_input = {
                **user_input,
                CONF_DEVICE_ID: device_id,
                CONF_BAUDRATE: baudrate,
                CONF_NOTIFY_CONNECTION_ERRORS_SERVICES: _normalize_services(
                    user_input.get(CONF_NOTIFY_CONNECTION_ERRORS_SERVICES)
                ),
            }

            offsets_changed   = (temp_offset, hum_offset) != (current_temp_offset, current_hum_offset)
            device_id_changed = device_id != current_device_id
            baudrate_changed  = baudrate != current_baudrate

            # Only talk to the sensor when something it stores actually changed
            if offsets_changed or device_id_changed or baudrate_changed:
                # UITLEG: De verbindingsinstellingen zoals ze NU zijn. Bij rtu
                # hoort de huidige baudrate daarbij, want die bepaalt hoe we de
                # sensor op dit moment kunnen bereiken.
                name = self.config_entry.data[CONF_NAME]
                current_params = build_params(
                    {**self.config_entry.data, CONF_BAUDRATE: current_baudrate}
                )

                try:
                    # UITLEG: Stap 1, op het HUIDIGE adres. De offsets eerst,
                    # want die veranderen niets aan de bereikbaarheid. Daarna het
                    # device-id, wat het adres van de sensor verzet.
                    async with temporary_unit(
                        self.hass, current_params, current_device_id
                    ) as unit:
                        hub = ShtModbusHub(name, unit, current_device_id)

                        if offsets_changed:
                            await hub.write_correction_settings(
                                temp_offset=temp_offset, hum_offset=hum_offset
                            )

                        if device_id_changed:
                            await hub.write_device_id(device_id)

                    # UITLEG: Stap 2, op het NIEUWE adres. Dit is het echte
                    # verschil met vroeger. De oude hub kon na het schrijven van
                    # het device-id gewoon `self.unit = device_id` doen en op
                    # dezelfde client verder praten. Een unit die van buiten komt
                    # zit vast aan het adres waarmee hij is opgevraagd, dus voor
                    # de baudrate vragen we een nieuwe unit aan op het adres waar
                    # de sensor sinds stap 1 naar luistert.
                    #
                    # De baudrate gaat bewust als laatste: die verbreekt de
                    # verbinding tot de gateway op dezelfde snelheid staat.
                    if baudrate_changed:
                        async with temporary_unit(
                            self.hass, current_params, device_id
                        ) as unit:
                            hub = ShtModbusHub(name, unit, device_id)
                            await hub.write_baudrate(baudrate)

                except Exception as e:
                    _LOGGER.warning(f"Could not write settings to sensor: {e}")
                    errors["base"] = "write_failed"

            if not errors:
                # Only update relevant data in the config entry
                updated_data = {
                    **self.config_entry.data,
                    CONF_DEVICE_ID: device_id,
                    CONF_BAUDRATE: baudrate,
                }

                self.hass.config_entries.async_update_entry(
                    self.config_entry,
                    data=updated_data,
                )

                return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            errors=errors,
            data_schema=vol.Schema({
                vol.Required(CONF_DEVICE_ID, default=current_device_id): DEVICE_ID_SELECTOR,
                vol.Required(CONF_BAUDRATE, default=str(current_baudrate)): BAUDRATE_SELECTOR,
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
    )