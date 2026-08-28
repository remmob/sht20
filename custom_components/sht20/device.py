"""Registermodel van de SHT20-sensor.

# UITLEG: DIT BESTAND IS HELEMAAL NIEUW.
#
# Dit is het grote idee van de nieuwe stack. Vroeger stond in hub.py:
#
#     result = await self._read_input_registers(address=1, count=2)
#     return {
#         "temperature": self._to_signed(result.registers[0]),
#         "humidity":    result.registers[1],
#     }
#
# Je gaf dus zelf op wélke registers gelezen moesten worden, in welke volgorde
# ze terugkwamen, en je pelde ze er met de hand weer uit. Bij twee registers
# valt dat mee; bij comfoair zijn dat zeven leesbereiken met een register_map
# eromheen om te onthouden welke index bij welk registernummer hoort.
#
# Hieronder beschrijf je in plaats daarvan alleen nog WAT er op welk adres
# staat. Bij `async_update()` rekent de bibliotheek zelf uit hoe hij dat in zo
# min mogelijk requests kan lezen, doet de reads, en zet de waarden klaar als
# gewone Python-attributen. Geen indexen, geen handmatige conversie.
"""

from __future__ import annotations

from modbus_connection import ModbusUnit
from modbus_connection.model import Component, gauge, integer, raw_register


class Sht20Readings(Component):
    """De meetwaarden: input-registers 1 en 2.

    # UITLEG: `register_space = "input"` bepaalt dat dit input-registers zijn
    # (functiecode 04), niet holding-registers (functiecode 03). Vroeger stond
    # dat verschil impliciet in de methodenaam `_read_input_registers`. Nu staat
    # het bij de definitie, en het zijn voor de bibliotheek twee gescheiden
    # adresruimtes: register 1 hier is iets anders dan register 1 in Settings
    # hieronder, en ze worden nooit in één request samengevoegd.
    """

    register_space = "input"

    # UITLEG: `signed=True` verving de handmatige helper `_to_signed()`:
    #
    #     return val if val < 0x8000 else val - 0x10000
    #
    # Dat kan weg; het veld weet nu zelf dat dit een int16 is en dus onder nul
    # kan komen.
    #
    # Let op: hier staat GEEN schaal. De sensor rapporteert honderdsten (2572
    # betekent 25,72 °C) maar dat omrekenen gebeurt in sensor.py met de
    # instelbare `multiplier`. Zou ik hier gauge(1, 0.01) zetten, dan werd er
    # twee keer geschaald en las je 0,2572 °C. De ruwe waarde blijft dus ruw.
    temperature = integer(1, signed=True)
    """Temperatuur, ruwe registerwaarde (honderdsten van een graad)."""

    humidity = integer(2, signed=False)
    """Relatieve luchtvochtigheid, ruwe registerwaarde (honderdsten procent)."""


class Sht20Settings(Component):
    """De instellingen in de sensor zelf: holding-registers 257 t/m 260.

    # UITLEG: Geen `register_space` hier, want "holding" is de standaard. Dit is
    # wat de oude `read_settings()` deed met één read van adres 257, count 4,
    # waarna raw[0] t/m raw[3] met de hand werden uitgepakt.
    #
    # Deze vier velden zijn `writable=True`, en dat is nieuw gereedschap: met
    # `await settings.write("temp_offset", 0.5)` schrijft de bibliotheek de
    # waarde terug naar het juiste register, inclusief het omgekeerd toepassen
    # van de schaal. Dat verving het handmatig bouwen van een payload.
    """

    device_id = integer(257, signed=False, writable=True)
    """Modbus unit-id waarop de sensor luistert."""

    # UITLEG: `raw_register` en niet `integer`, omdat dit register bewust NIET
    # geïnterpreteerd moet worden. Sommige SHT20's slaan de werkelijke baudrate
    # op (9600), andere een code (0, 1 of 2). Welke van de twee het is, weet je
    # pas als je de waarde ziet. Die logica staat in hub.py en blijft daar; het
    # veld levert alleen het rauwe woord aan.
    #
    # Een `enum()`-veld zou hier verkeerd zijn: dat gaat ervan uit dat de codes
    # vastliggen, en dat is precies wat hier niet zo is.
    baudrate_raw = raw_register(258, writable=True)
    """Baudrate-register: bevat een code óf de baudrate zelf, apparaatafhankelijk."""

    # UITLEG: Hier staat de schaal wél in het veld, anders dan bij de
    # meetwaarden hierboven. Reden: de oude code deed dit ook al zelf
    # (`_to_signed(raw[2]) / 10.0`) en er is geen instelbare multiplier voor.
    # Bij schrijven draait de bibliotheek de formule om, dus 0,5 wordt 5 in het
    # register. Dat verving dit blok uit write_correction_settings():
    #
    #     temp_payload = ModbusTcpClient.convert_to_registers(
    #         [int(temp_offset * 10)],
    #         data_type=ModbusTcpClient.DATATYPE.INT16,
    #         word_order='big',
    #     )
    temp_offset = gauge(259, 0.1, signed=True, writable=True)
    """Temperatuurcorrectie in graden, zoals opgeslagen in de sensor."""

    hum_offset = gauge(260, 0.1, signed=True, writable=True)
    """Vochtigheidscorrectie in procent, zoals opgeslagen in de sensor."""


class Sht20Device:
    """Bundelt de twee componenten rond één unit.

    # UITLEG: Een dun laagje, zodat de rest van de integratie één ding vasthoudt
    # in plaats van twee losse componenten. De twee componenten worden apart
    # bijgewerkt, want ze hebben een heel ander ritme: de meetwaarden elke
    # scan_interval, de instellingen alleen bij het openen van het optiescherm.
    """

    def __init__(self, unit: ModbusUnit) -> None:
        self.unit = unit
        self.readings = Sht20Readings(unit)
        self.settings = Sht20Settings(unit)
