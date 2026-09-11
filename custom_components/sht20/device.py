"""Register model of the SHT20 sensor.

Instead of manually specifying which registers to read, in what order they
come back, and unpacking them by hand, each field below only describes WHAT
lives at which address. `async_update()` works out how to read that in as few
requests as possible and exposes the values as plain Python attributes.
"""

from __future__ import annotations

from modbus_connection.model import Component, integer


class Sht20Readings(Component):
    """The measured values: input registers 1 and 2.

    `register_space = "input"` marks these as input registers (function code
    04) rather than holding registers (function code 03).
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
