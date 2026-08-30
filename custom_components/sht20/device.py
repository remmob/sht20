"""Register model of the SHT20 sensor.

Instead of manually specifying which registers to read, in what order they
come back, and unpacking them by hand, each field below only describes WHAT
lives at which address. `async_update()` works out how to read that in as few
requests as possible and exposes the values as plain Python attributes.
"""

from __future__ import annotations

from modbus_connection import ModbusUnit
from modbus_connection.model import Component, gauge, integer, raw_register


class Sht20Readings(Component):
    """The measured values: input registers 1 and 2.

    `register_space = "input"` marks these as input registers (function code
    04) rather than holding registers (function code 03) — a separate
    address space from Sht20Settings below, never merged into one request.
    """

    register_space = "input"

    # `signed=True` marks this as an int16 that can go negative.
    #
    # Note there is no scale here: the sensor reports hundredths (2572 means
    # 25.72 °C), but that conversion happens in sensor.py via the
    # user-configurable `multiplier`. Scaling it here too would double-scale
    # the value, so the raw value stays raw.
    temperature = integer(1, signed=True)
    """Temperature, raw register value (hundredths of a degree)."""

    humidity = integer(2, signed=False)
    """Relative humidity, raw register value (hundredths of a percent)."""


class Sht20Settings(Component):
    """The settings stored in the sensor itself: holding registers 257-260.

    No `register_space` here since "holding" is the default. These four
    fields are `writable=True`: `await settings.write("temp_offset", 0.5)`
    writes the value back to the right register, applying the scale in
    reverse.
    """

    device_id = integer(257, signed=False, writable=True)
    """Modbus unit ID the sensor listens on."""

    # `raw_register`, not `integer`, because this register must NOT be
    # interpreted. Some SHT20 units store the actual baud rate (9600), others
    # a code (0, 1 or 2); which one it is can only be told by reading it. That
    # decoding lives in hub.py. An `enum()` field would be wrong here since it
    # assumes the codes are fixed, which they are not across devices.
    baudrate_raw = raw_register(258, writable=True)
    """Baud rate register: holds either a code or the baud rate itself, device-dependent."""

    # Scale lives directly on the field here, unlike the readings above,
    # since there is no user-configurable multiplier for these. On write the
    # library reverses the formula, so 0.5 becomes 5 in the register.
    temp_offset = gauge(259, 0.1, signed=True, writable=True)
    """Temperature correction in degrees, as stored in the sensor."""

    hum_offset = gauge(260, 0.1, signed=True, writable=True)
    """Humidity correction in percent, as stored in the sensor."""


class Sht20Device:
    """Bundles the two components around one unit.

    A thin layer so the rest of the integration holds one thing instead of
    two separate components. The two components are updated separately since
    they have very different rhythms: the readings every scan_interval, the
    settings only when the options screen is opened.
    """

    def __init__(self, unit: ModbusUnit) -> None:
        self.unit = unit
        self.readings = Sht20Readings(unit)
        self.settings = Sht20Settings(unit)
