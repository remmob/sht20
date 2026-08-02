"""Psychrometric calculations for the SHT20 Modbus integration.

All functions take the temperature in degrees Celsius and the relative
humidity in percent. Pressure is expressed in hPa (mbar).
"""

import math

# Magnus-Tetens coefficients over water (valid for roughly -45..60 °C)
MAGNUS_A = 17.62
MAGNUS_B = 243.12  # °C
MAGNUS_C = 6.112  # hPa

# Ratio of the molar masses of water vapour and dry air
MOLAR_MASS_RATIO = 0.62198

# Specific heat of dry air / latent heat of vaporisation / specific heat of vapour
CP_AIR = 1.006  # kJ/(kg.K)
LATENT_HEAT = 2501.0  # kJ/kg
CP_VAPOUR = 1.86  # kJ/(kg.K)

# Steadman apparent temperature constants
AT_VAPOUR_FACTOR = 0.33
AT_WIND_FACTOR = 0.70
AT_OFFSET = 4.00

# Relative humidity is clamped to this range to keep the maths well defined
MIN_HUMIDITY = 0.01
MAX_HUMIDITY = 100.0


def _clamp_humidity(humidity: float) -> float:
    """Keep the relative humidity within a physically meaningful range."""
    return min(max(humidity, MIN_HUMIDITY), MAX_HUMIDITY)


def saturation_vapour_pressure(temperature: float) -> float:
    """Return the saturation vapour pressure in hPa."""
    return MAGNUS_C * math.exp((MAGNUS_A * temperature) / (MAGNUS_B + temperature))


def vapour_pressure(temperature: float, humidity: float) -> float:
    """Return the actual (partial) water vapour pressure in hPa."""
    return _clamp_humidity(humidity) / 100.0 * saturation_vapour_pressure(temperature)


def dew_point(temperature: float, humidity: float) -> float:
    """Return the dew point temperature in °C."""
    ratio = math.log(vapour_pressure(temperature, humidity) / MAGNUS_C)
    return (MAGNUS_B * ratio) / (MAGNUS_A - ratio)


def absolute_humidity(temperature: float, humidity: float, pressure: float) -> float:
    """Return the humidity ratio in kg water vapour per kg of dry air."""
    partial = vapour_pressure(temperature, humidity)
    # Guard against a vapour pressure at or above the total pressure
    partial = min(partial, pressure - MIN_HUMIDITY)
    return MOLAR_MASS_RATIO * partial / (pressure - partial)


def enthalpy(temperature: float, humidity: float, pressure: float) -> float:
    """Return the specific enthalpy in kJ per kg of dry air."""
    ratio = absolute_humidity(temperature, humidity, pressure)
    return CP_AIR * temperature + ratio * (LATENT_HEAT + CP_VAPOUR * temperature)


def apparent_temperature(
    temperature: float, humidity: float, wind_speed: float = 0.0
) -> float:
    """Return the apparent ("feels like") temperature in °C.

    Uses the Steadman apparent temperature formula. The SHT20 has no
    anemometer, so the wind speed defaults to still air.
    """
    return (
        temperature
        + AT_VAPOUR_FACTOR * vapour_pressure(temperature, humidity)
        - AT_WIND_FACTOR * wind_speed
        - AT_OFFSET
    )
