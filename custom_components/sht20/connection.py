"""Modbus-verbinding voor de SHT20-integratie.

# UITLEG: DIT BESTAND IS HELEMAAL NIEUW.
#
# Vroeger bouwde hub.py zelf zijn pymodbus-client op (AsyncModbusTcpClient en
# vrienden), hield die vast, en sloot hem weer. Dat doet dit bestand nu, maar
# een niveau abstracter: het levert een "unit" op. Een unit is een handvat naar
# één apparaat op een Modbus-lijn. Wie de verbinding eronder bezit en wanneer
# die open- en dichtgaat, is niet meer onze zorg.
#
# Waarom een apart bestand? Omdat hier het enige verschil zit tussen Home
# Assistant 2026.8 en 2026.9. De rest van de integratie merkt daar niets van.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from modbus_connection import (
    ModbusSerialParams,
    ModbusTcpParams,
    ModbusUdpParams,
    ModbusUnit,
)
from modbus_connection.tmodbus import ModbusConnection

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from .const import (
    CONF_BAUDRATE,
    CONF_DEVICE,
    CONF_MODE,
    DEFAULT_BAUDRATE,
    DEFAULT_PORT,
)

# UITLEG: Hier zit de hele versiecompatibiliteit.
#
# `async_get_unit` zit in de modbus-integratie van Home Assistant zelf, maar
# bestaat pas vanaf 2026.9. Op 2026.8 mislukt deze import, en dan vallen we
# terug op een eigen verbinding. Eén codebase die op beide versies draait,
# in plaats van twee aparte releases.
#
# Deze terugval blijft tot september 2027 staan, een jaar na 2026.9. Daarna
# mag dit try/except-blok eruit en gaat de ondergrens in hacs.json omhoog.
try:
    from homeassistant.components.modbus import (
        async_get_temporary_unit,
        async_get_unit,
    )

    HAS_SHARED_CONNECTION = True
except ImportError:  # Home Assistant ouder dan 2026.9
    async_get_temporary_unit = None
    async_get_unit = None
    HAS_SHARED_CONNECTION = False


# UITLEG: Twee labels voor de tijdelijke diagnose-sensor, zodat je in de
# interface kunt zien welke van de twee wegen hierboven actief is.
METHOD_SHARED = "gedeeld (HA modbus)"
METHOD_OWN = "eigen verbinding"


def active_method() -> str:
    """Geef terug welke verbindingsmethode deze Home Assistant gebruikt."""
    return METHOD_SHARED if HAS_SHARED_CONNECTION else METHOD_OWN


def build_params(
    data: Mapping[str, Any],
) -> ModbusTcpParams | ModbusUdpParams | ModbusSerialParams:
    """Bouw de verbindingsparameters uit de gegevens van de config entry.

    # UITLEG: Dit verving het if/elif-blok in hub.connect(), waar per modus een
    # andere pymodbus-clientklasse werd aangemaakt. Nu maken we geen client meer
    # maar een klein beschrijvend object. Er gebeurt hier geen netwerkverkeer;
    # het is puur "zo is dit apparaat te bereiken".
    #
    # Bijkomend voordeel: de try/except rond AsyncModbusUdpClient in de oude
    # hub.py is niet meer nodig. Die was er omdat oudere pymodbus-versies geen
    # UDP-client hadden. ModbusUdpParams bestaat altijd.
    """
    mode = data[CONF_MODE]

    if mode == "tcp":
        return ModbusTcpParams(
            host=data[CONF_HOST],
            port=int(data.get(CONF_PORT, DEFAULT_PORT)),
        )

    if mode == "udp":
        return ModbusUdpParams(
            host=data[CONF_HOST],
            port=int(data.get(CONF_PORT, DEFAULT_PORT)),
        )

    if mode == "rtu":
        return ModbusSerialParams(
            device=data[CONF_DEVICE],
            baudrate=int(data.get(CONF_BAUDRATE, DEFAULT_BAUDRATE)),
        )

    raise ValueError(f"Niet-ondersteunde modus: {mode!r}")


def async_setup_unit(
    hass: HomeAssistant,
    entry: ConfigEntry,
    params: ModbusTcpParams | ModbusUdpParams | ModbusSerialParams,
    unit_id: int,
) -> ModbusUnit:
    """Geef een unit terug voor deze config entry.

    # UITLEG: Dit is de kern van de hele ombouw, in twee takken.
    #
    # Op 2026.9+ vraagt `async_get_unit` een unit aan bij Home Assistant. Praten
    # twee integraties met dezelfde gateway, dan krijgen ze allebei een unit op
    # DEZELFDE onderliggende socket en gaan hun requests netjes achter elkaar
    # aan. Precies wat er nodig is om straks de SHT20 en de comfoair samen op
    # één Elfin EW-11 te kunnen hangen. Home Assistant sluit die verbinding zelf
    # zodra de laatste config entry hem loslaat.
    #
    # Op 2026.8 maken we onze eigen verbinding aan. Functioneel identiek, alleen
    # niet gedeeld: elke integratie houdt zijn eigen socket. Dat is het gedrag
    # dat de integratie voorheen altijd had.
    """
    if async_get_unit is not None:
        return async_get_unit(hass, entry, params, unit_id)

    connection = ModbusConnection(params)
    # UITLEG: `async_on_unload` zorgt dat Home Assistant de verbinding sluit als
    # de integratie wordt uitgeladen. Dit verving de handmatige `await
    # hub.close()` in async_unload_entry.
    entry.async_on_unload(connection.close)
    return connection.for_unit(unit_id)


@asynccontextmanager
async def temporary_unit(
    hass: HomeAssistant,
    params: ModbusTcpParams | ModbusUdpParams | ModbusSerialParams,
    unit_id: int,
) -> AsyncIterator[ModbusUnit]:
    """Geef een unit voor de duur van een config flow.

    # UITLEG: De config flow praat met de sensor terwijl er nog geen config
    # entry is om een verbinding aan op te hangen (bij installatie), of terwijl
    # er er al één draait (bij het wijzigen van instellingen). Vroeger bouwde de
    # config flow daarvoor een tweede, eigen hub op en sloot die weer.
    #
    # Dat tweede socket is precies wat een EW-11 niet trekt. Op 2026.9 lost
    # `async_get_temporary_unit` dat op: bestaat er al een verbinding naar dit
    # apparaat, dan lift de config flow daarop mee in plaats van er een tweede
    # naast te zetten. Alleen een verbinding die hier zelf geopend is, wordt bij
    # het verlaten weer gesloten.
    """
    if async_get_temporary_unit is not None:
        async with async_get_temporary_unit(hass, params, unit_id) as unit:
            yield unit
        return

    connection = ModbusConnection(params)
    try:
        yield connection.for_unit(unit_id)
    finally:
        await connection.close()
