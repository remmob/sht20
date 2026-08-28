"""Leest en schrijft de SHT20 via een Modbus-unit.

# UITLEG: DIT BESTAND IS VRIJWEL HELEMAAL HERSCHREVEN. Van ~230 regels naar ~110,
# en een flink deel daarvan is commentaar.
#
# Wat er UIT is gegaan, en waarom:
#
#   connect() / close() / _reset_client()
#       Wij bezitten de verbinding niet meer. Die komt van buiten binnen als
#       "unit" en wordt beheerd door Home Assistant of door connection.py.
#       Verbinden gebeurt vanzelf bij de eerste read.
#
#   _read_input_registers() met zijn client-beheer
#       Dat waren ~45 regels: verbinden, bij elke fout de client weggooien en
#       opnieuw opbouwen. Het herverbinden doet de bibliotheek nu zelf.
#
#       LET OP: het HERPROBEREN doet ze NIET. Uit de documentatie van
#       modbus-connection: "Neither backend retries timeouts, dropped links, or
#       other exception responses." Alleen een SERVER_DEVICE_BUSY-antwoord wordt
#       herhaald. Een time-out komt er dus meteen uit.
#
#       Daarom is de retry-lus hieronder bewust BEHOUDEN, in een veel kortere
#       vorm (_update_with_retry). Zonder die lus zou één verstoorde meting
#       direct een verbindingsfout-melding opleveren, want ConnectionMonitor
#       rekent bij scan_interval 60 en delay 60 uit dat één mislukking genoeg is.
#       MAX_READ_RETRIES en RETRY_DELAY_SECONDS blijven dus in gebruik.
#
#   De "stale connection"-controle
#       Vijf minuten geen succesvolle read betekende: forceer een reconnect.
#       Dat was een pleister op een client die er levend uitzag maar dood was.
#       Niet meer nodig, dus STALE_CONNECTION_SECONDS wordt niet meer gebruikt.
#
#   _to_signed()
#       Vervangen door signed=True op het veld in device.py.
#
#   Het convert_to_registers-blok in write_correction_settings()
#       Handmatig een int16-payload bouwen om twee registers te schrijven.
#       Vervangen door één write() per veld.
#
#   De import van pymodbus
#       Helemaal weg. Dat repareert meteen een sluimerende fout: manifest.json
#       gaf pymodbus nergens op als requirement, dus deze integratie werkte
#       alleen doordat een ándere integratie op dezelfde machine pymodbus
#       binnenhaalde. Op een schone installatie ging dat mis.
#
# Wat er IN is gebleven: de baudrate-eigenaardigheid. Sommige sensoren slaan de
# werkelijke baudrate op, andere een code. Dat is apparaatkennis, geen
# transportkennis, en hoort dus hier thuis.
"""

from __future__ import annotations

import asyncio
import logging

from modbus_connection import ModbusError, ModbusUnit

from .const import (
    BAUDRATE_CODES,
    BAUDRATE_VALUES,
    MAX_READ_RETRIES,
    RETRY_DELAY_SECONDS,
)
from .device import Sht20Device

_LOGGER = logging.getLogger(__name__)


class ShtModbusHub:
    """Dunne laag rond het registermodel van de sensor."""

    def __init__(self, name: str, unit: ModbusUnit, unit_id: int) -> None:
        # UITLEG: De constructor nam vroeger hass, name, mode, device_id, host,
        # port, device en baudrate. Alles wat met de verbinding te maken had is
        # weg; er komt nu één kant-en-klare unit binnen. Wie die unit maakt en
        # hoe, staat in connection.py.
        #
        # unit_id houden we alleen bij om te weten op welk adres we praten, voor
        # logging en bij het wijzigen van het device-id.
        self.name = name
        self.unit_id = unit_id
        self._device = Sht20Device(unit)

    # ------------------------------------------------------------------ lezen

    async def _update_with_retry(self, component, what: str) -> None:
        """Werk een component bij, met dezelfde pogingen als voorheen.

        # UITLEG: Dit is wat er over is van de oude retry-lus van ~45 regels.
        # De bibliotheek herverbindt zelf, dus het weggooien en opnieuw opbouwen
        # van de client is weg. Wat blijft is het herproberen zelf, want dat doet
        # de bibliotheek nadrukkelijk NIET voor time-outs.
        #
        # Zonder dit zou één hapering meteen doorslaan naar UpdateFailed: de
        # entiteiten worden "niet beschikbaar" en ConnectionMonitor stuurt een
        # verbindingsfout. Dat is precies het gedrag dat v1.1.0 niet had, en dat
        # willen we niet stilletjes veranderen.
        """
        last_error: ModbusError | None = None

        for attempt in range(MAX_READ_RETRIES):
            try:
                await component.async_update()
                return
            except ModbusError as err:
                last_error = err
                _LOGGER.debug(
                    "Lezen van %s mislukt (poging %s/%s): %s",
                    what, attempt + 1, MAX_READ_RETRIES, err,
                )
                if attempt < MAX_READ_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)

        _LOGGER.warning(
            "Lezen van %s mislukt na %s pogingen: %s",
            what, MAX_READ_RETRIES, last_error,
        )
        raise last_error

    async def read_realtime_data(self) -> dict:
        """Lees temperatuur en luchtvochtigheid als ruwe registerwaarden.

        # UITLEG: Dit was een read van adres 1 met count 2, gevolgd door het met
        # de hand uitpakken van result.registers[0] en [1]. Nu haalt
        # async_update() de hele component op en staan de waarden als gewone
        # attributen klaar.
        #
        # De asyncio.sleep(0.1) die hier stond is weg. Die gaf de bus even rust;
        # daar heeft de bibliotheek `message_spacing` voor, in te stellen per
        # unit. Nu niet nodig, en als de bus straks twee apparaten draagt is dát
        # de plek om aan te draaien.
        #
        # De sleutels van dit dict blijven exact hetzelfde, want sensor.py
        # gebruikt ze om zijn entiteiten aan te maken. Zou ik ze hernoemen, dan
        # kregen alle sensoren een nieuwe entity-ID.
        """
        await self._update_with_retry(self._device.readings, "meetwaarden")

        return {
            "temperature": self._device.readings.temperature,
            "humidity": self._device.readings.humidity,
        }

    async def read_settings(self) -> dict:
        """Lees de vier instellingen die in de sensor zelf staan."""
        await self._update_with_retry(self._device.settings, "instellingen")
        settings = self._device.settings

        return {
            "device_id": settings.device_id,
            "baudrate": self._decode_baudrate(settings.baudrate_raw),
            "temp_offset": settings.temp_offset,
            "hum_offset": settings.hum_offset,
        }

    # -------------------------------------------------------------- schrijven

    async def write_correction_settings(
        self, temp_offset: float, hum_offset: float
    ) -> None:
        """Schrijf de twee correctiewaarden naar de sensor.

        # UITLEG: Vroeger werden deze twee in één keer geschreven (functiecode
        # 16, twee registers tegelijk) met een zelfgebouwde payload. Nu zijn het
        # twee losse schrijfacties (functiecode 06). Dat is één request meer,
        # maar het resultaat in de sensor is hetzelfde, en de omrekening van
        # 0,5 naar registerwaarde 5 doet het veld zelf.
        """
        await self._device.settings.write("temp_offset", temp_offset)
        await self._device.settings.write("hum_offset", hum_offset)

    async def write_device_id(self, device_id: int) -> None:
        """Schrijf een nieuw Modbus-adres naar de sensor.

        # UITLEG: LET OP, dit is het gevoeligste stuk van de integratie. Na deze
        # schrijfactie luistert de sensor op een ánder adres. Alles wat daarna
        # nog via deze hub gaat, praat tegen een adres waar niemand antwoordt.
        #
        # Vroeger loste hub.py dat zelf op met `self.unit = device_id`, waarna
        # de volgende schrijfactie automatisch het nieuwe adres gebruikte. Dat
        # kan nu niet meer: de unit komt van buiten en zit vast aan het adres
        # waarmee hij is opgevraagd.
        #
        # Daarom is dit gesplitst van write_baudrate(), wat vroeger één methode
        # write_device_settings() was. De aanroeper in config_flow.py vraagt na
        # deze schrijfactie een níeuwe unit aan op het nieuwe adres.
        """
        _LOGGER.debug("Schrijf nieuw device-id %s (was %s)", device_id, self.unit_id)
        await self._device.settings.write("device_id", device_id)

    async def write_baudrate(self, baudrate: int) -> None:
        """Schrijf een nieuwe baudrate naar de sensor.

        # UITLEG: Ook dit breekt de verbinding, en wel tot de gateway op
        # dezelfde snelheid staat. Daarom gebeurt dit altijd als laatste.
        """
        if baudrate not in BAUDRATE_VALUES:
            raise ValueError(f"Niet-ondersteunde baudrate: {baudrate}")

        await self._device.settings.write(
            "baudrate_raw", await self._encode_baudrate(baudrate)
        )

    # ---------------------------------------------------- baudrate-vertaling

    @staticmethod
    def _decode_baudrate(raw: int | None) -> int | None:
        """Zet de ruwe registerwaarde om naar een baudrate.

        # UITLEG: Ongewijzigd overgenomen uit de oude read_settings(). Sommige
        # sensoren zetten er 9600 in, andere de code 0. Staat er een bekende
        # baudrate, dan is dat het antwoord; anders lezen we het als code.
        """
        if raw is None:
            return None
        if raw in BAUDRATE_VALUES:
            return raw

        baudrate = BAUDRATE_CODES.get(raw)
        if baudrate is None:
            _LOGGER.warning("Onbekende baudrate in het instellingenregister: %s", raw)
        return baudrate

    async def _encode_baudrate(self, baudrate: int) -> int:
        """Bepaal wat er in het register moet, in het formaat van dit apparaat.

        # UITLEG: Ongewijzigd van opzet. We lezen eerst wat er nu staat om te
        # zien welk van de twee formaten deze sensor gebruikt, en schrijven dan
        # in datzelfde formaat terug. Het verschil met vroeger is alleen hóe we
        # dat lezen: toen een losse read_holding_registers, nu een async_update()
        # van de component.
        """
        await self._device.settings.async_update()
        current = self._device.settings.baudrate_raw

        if current in BAUDRATE_CODES:
            # Deze sensor slaat een code op in plaats van de baudrate zelf
            return BAUDRATE_VALUES[baudrate]
        return baudrate
