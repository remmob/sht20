import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.const import UnitOfTemperature, PERCENTAGE

from .const import (
    DOMAIN,
    CONF_TEMP_OFFSET,
    CONF_HUM_OFFSET,
    CONF_NAME,
    CONF_MULTIPLIER, 
    DEFAULT_MULTIPLIER
    
)

_LOGGER = logging.getLogger(__name__)


SENSOR_TYPES = {
    "temperature": {
        "name": "Temperature",
        "unit": UnitOfTemperature.CELSIUS,
        "device_class": SensorDeviceClass.TEMPERATURE,
        "offset_key": CONF_TEMP_OFFSET,
    },
    "humidity": {
        "name": "Humidity",
        "unit": PERCENTAGE,
        "device_class": SensorDeviceClass.HUMIDITY,
        "offset_key": CONF_HUM_OFFSET,
    },
}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]["realtime"]

    #_LOGGER.debug("Setting up SHT20 sensors: data=%s | options=%s", entry.data, entry.options)

    entities = [
        Sht20Sensor(coordinator, entry, key)
        for key in SENSOR_TYPES
        if key in coordinator.data
    ]
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
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_entity_registry_enabled_default = True

        self._attr_device_info = {
            "identifiers": {(DOMAIN, str(entry.entry_id))},
            "name": name,
            "manufacturer": "Bommer Home automation",
            "model": "SHT20 Modbus temp/hum sensor",
        }

        self._offset_key = info.get("offset_key")

    @property
    def native_value(self):
        value = self.coordinator.data.get(self._key)
        offset = self._entry.options.get(self._offset_key, 0) if self._offset_key else 0

        if value is not None:
            multiplier = self._entry.options.get(CONF_MULTIPLIER, DEFAULT_MULTIPLIER)
            return round((value * multiplier) + offset, 2)
        return None
