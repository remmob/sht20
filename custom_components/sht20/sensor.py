import logging

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import (
    UnitOfTemperature,
    PERCENTAGE,
    EntityCategory,
    __version__ as HA_VERSION,
)

from . import calculations
# UITLEG: nieuw, alleen voor de tijdelijke diagnose-sensor onderaan dit bestand.
from .connection import HAS_SHARED_CONNECTION, active_method
from .const import (
    DOMAIN,
    CONF_NAME,
    CONF_MULTIPLIER,
    CONF_PRESSURE,
    DEFAULT_MULTIPLIER,
    DEFAULT_PRESSURE,
    DISPLAY_PRECISION,
    ABSOLUTE_HUMIDITY_PRECISION,
    UNIT_ABSOLUTE_HUMIDITY,
    UNIT_ENTHALPY,
)

_LOGGER = logging.getLogger(__name__)


# The temperature and humidity corrections are written to the sensor itself,
# so the values read back are already corrected.
SENSOR_TYPES = {
    "temperature": {
        "name": "Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
    },
    "humidity": {
        "name": "Humidity",
        "unit": PERCENTAGE,
        "device_class": SensorDeviceClass.HUMIDITY,
    },
}

# Sensors derived from the measured temperature and humidity. Every entry
# provides a callable that takes (temperature, humidity, pressure).
CALCULATED_SENSOR_TYPES = {
    "dew_point": {
        "name": "Dew point",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "calculate": lambda temp, hum, pressure: calculations.dew_point(temp, hum),
    },
    "absolute_humidity": {
        "name": "Absolute humidity",
        "unit": UNIT_ABSOLUTE_HUMIDITY,
        "device_class": None,
        "precision": ABSOLUTE_HUMIDITY_PRECISION,
        "calculate": calculations.absolute_humidity,
    },
    "enthalpy": {
        "name": "Enthalpy",
        "unit": UNIT_ENTHALPY,
        "device_class": None,
        "calculate": calculations.enthalpy,
    },
    "apparent_temperature": {
        "name": "Apparent temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "calculate": lambda temp, hum, pressure: calculations.apparent_temperature(
            temp, hum
        ),
    },
}


def _device_info(entry, name):
    return {
        "identifiers": {(DOMAIN, str(entry.entry_id))},
        "name": name,
        "manufacturer": "Bommer Home automation",
        "model": "SHT20 Modbus temp/hum sensor",
    }


def _scaled_value(coordinator, entry, key):
    """Return a raw register value scaled with the configured multiplier."""
    value = coordinator.data.get(key) if coordinator.data else None
    if value is None:
        return None

    return value * entry.options.get(CONF_MULTIPLIER, DEFAULT_MULTIPLIER)


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["realtime"]

    #_LOGGER.debug("Setting up SHT20 sensors: data=%s | options=%s", entry.data, entry.options)

    entities = [
        Sht20Sensor(coordinator, entry, key)
        for key in SENSOR_TYPES
        if key in coordinator.data
    ]

    # The calculated sensors need both a temperature and a humidity reading
    if "temperature" in coordinator.data and "humidity" in coordinator.data:
        entities.extend(
            Sht20CalculatedSensor(coordinator, entry, key)
            for key in CALCULATED_SENSOR_TYPES
        )

    # UITLEG: TIJDELIJK. Deze sensor hoort niet bij het apparaat maar bij de
    # ombouw: hij laat zien welke van de twee verbindingsmethodes deze Home
    # Assistant gebruikt. Zo is in één oogopslag te zien of je op het gedeelde
    # pad zit (2026.9+) of op de terugval (ouder). Weghalen zodra de ombouw
    # bewezen is, of omzetten naar een attribuut op een bestaande sensor.
    entities.append(Sht20ConnectionMethodSensor(coordinator, entry))

    async_add_entities(entities)


class Sht20Sensor(CoordinatorEntity, SensorEntity):
    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        info = SENSOR_TYPES[key]

        name = entry.data[CONF_NAME]

        self._attr_name = f"{name} {info['name']}"
        self._attr_native_unit_of_measurement = info["unit"]
        self._attr_device_class = info["device_class"]
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = DISPLAY_PRECISION
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_entity_registry_enabled_default = True

        self._attr_device_info = _device_info(entry, name)

    @property
    def native_value(self):
        value = _scaled_value(self.coordinator, self._entry, self._key)
        if value is not None:
            return round(value, DISPLAY_PRECISION)
        return None


class Sht20CalculatedSensor(CoordinatorEntity, SensorEntity):
    """Sensor derived from the measured temperature and humidity."""

    def __init__(self, coordinator, entry, key):
        super().__init__(coordinator)
        self._entry = entry
        self._key = key
        info = CALCULATED_SENSOR_TYPES[key]

        name = entry.data[CONF_NAME]

        self._attr_name = f"{name} {info['name']}"
        self._attr_native_unit_of_measurement = info["unit"]
        self._attr_device_class = info["device_class"]
        self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = info.get("precision", DISPLAY_PRECISION)
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_entity_registry_enabled_default = True

        self._attr_device_info = _device_info(entry, name)

        self._precision = info.get("precision", DISPLAY_PRECISION)
        self._calculate = info["calculate"]

    @property
    def native_value(self):
        temperature = _scaled_value(self.coordinator, self._entry, "temperature")
        humidity = _scaled_value(self.coordinator, self._entry, "humidity")

        if temperature is None or humidity is None:
            return None

        pressure = self._entry.options.get(CONF_PRESSURE, DEFAULT_PRESSURE)

        try:
            return round(self._calculate(temperature, humidity, pressure), self._precision)
        except (ValueError, ZeroDivisionError) as err:
            _LOGGER.warning("Could not calculate %s: %s", self._key, err)
            return None


class Sht20ConnectionMethodSensor(CoordinatorEntity, SensorEntity):
    """TIJDELIJK: toont welke Modbus-verbindingsmethode actief is.

    # UITLEG: DEZE KLASSE IS NIEUW EN BEDOELD OM WEER TE VERDWIJNEN.
    #
    # Hij leest geen register uit. De waarde komt uit connection.py en zegt
    # alleen of `async_get_unit` van Home Assistant beschikbaar was:
    #
    #   "gedeeld (HA modbus)"  -> HA 2026.9 of nieuwer, verbinding wordt gedeeld
    #   "eigen verbinding"     -> ouder, deze integratie opent zijn eigen socket
    #
    # Het is een diagnose-entiteit (EntityCategory.DIAGNOSTIC), dus hij komt
    # onderaan bij het apparaat te staan en niet tussen de meetwaarden.
    #
    # Dit is de énige entiteit die erbij hoort te komen. Verschijnt er nog iets
    # anders, dan is er per ongeluk een sleutel veranderd en klopt er iets niet.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:transit-connection-variant"

    def __init__(self, coordinator, entry):
        super().__init__(coordinator)
        name = entry.data[CONF_NAME]

        self._attr_name = f"{name} Verbindingsmethode"
        self._attr_unique_id = f"{entry.entry_id}_connection_method"
        self._attr_device_info = _device_info(entry, name)

    @property
    def native_value(self):
        return active_method()

    @property
    def extra_state_attributes(self):
        # UITLEG: De HA-versie erbij, zodat een screenshot meteen laat zien
        # waaróm deze methode gekozen is.
        return {
            "gedeelde_verbinding_beschikbaar": HAS_SHARED_CONNECTION,
            "home_assistant_versie": HA_VERSION,
        }
