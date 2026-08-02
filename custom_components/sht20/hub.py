from pymodbus.client import AsyncModbusSerialClient
from pymodbus.client.tcp import AsyncModbusTcpClient
from pymodbus.client import ModbusTcpClient
import asyncio, inspect, logging

try:
    from pymodbus.client.udp import AsyncModbusUdpClient
except ImportError:
    # Older pymodbus versions have no UDP client; tcp and rtu keep working
    AsyncModbusUdpClient = None

from datetime import datetime

from .const import (
    BAUDRATE_CODES,
    BAUDRATE_VALUES,
    MAX_READ_RETRIES,
    RETRY_DELAY_SECONDS,
    STALE_CONNECTION_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

# Holding register addresses
REG_DEVICE_ID = 257
REG_BAUDRATE = 258
REG_TEMP_OFFSET = 259

class ShtModbusHub:
    def __init__(self, hass, name, mode, device_id, host=None, port=None, device=None, baudrate=None):
        self.hass     = hass
        self.name     = name
        self.mode     = mode
        self.unit     = device_id
        self.host     = host
        self.port     = port
        self.device   = device
        self.baudrate = baudrate
        self._client  = None
        self._last_successful_read = None

    async def connect(self):
        if self._client and self._client.connected:
            return

        if self.mode == "tcp":
            self._client = AsyncModbusTcpClient(host=self.host, port=self.port)
        elif self.mode == "udp":
            # UDP is connectionless, so the gateway has no limit on the number
            # of clients. There is no delivery guarantee, the retries cover that.
            if AsyncModbusUdpClient is None:
                raise ValueError("UDP is not supported by this pymodbus version")
            self._client = AsyncModbusUdpClient(host=self.host, port=self.port)
        elif self.mode == "rtu":
            self._client = AsyncModbusSerialClient(
                port=self.device,
                baudrate=self.baudrate,
                timeout=3
            )
        else:
            raise ValueError(f"Unsupported mode: {self.mode}")

        await self._client.connect()
        
    async def close(self):
        if not self._client:
            return
        # Depending on the pymodbus version close() is either sync or a coroutine
        result = self._client.close()
        if inspect.isawaitable(result):
            await result
        self._client = None
        
    async def _reset_client(self):
        """Drop the client so the next attempt sets up a fresh connection."""
        if self._client is None:
            return
        try:
            await self.close()
        except Exception:
            self._client = None

    async def _read_input_registers(self, address: int, count: int):
        """Read input registers, retrying and reconnecting on failure."""
        # A long silence usually means the connection is dead but looks alive
        if self._last_successful_read is not None:
            stale_for = (datetime.now() - self._last_successful_read).total_seconds()
            if stale_for > STALE_CONNECTION_SECONDS:
                _LOGGER.warning(
                    "No successful reads for %ss, forcing reconnect", int(stale_for)
                )
                await self._reset_client()

        last_error = None

        for attempt in range(MAX_READ_RETRIES):
            try:
                await self.connect()
                result = await self._client.read_input_registers(
                    address=address,
                    count=count,
                    device_id=self.unit
                )

                if result is None or result.isError():
                    last_error = f"Modbus error frame: {result}"
                    _LOGGER.warning(
                        "Read of %s-%s failed (attempt %s/%s), forcing reconnect",
                        address, address + count - 1, attempt + 1, MAX_READ_RETRIES,
                    )
                    await self._reset_client()
                else:
                    self._last_successful_read = datetime.now()
                    return result

            except Exception as err:
                last_error = err
                _LOGGER.warning(
                    "Modbus communication error on %s-%s (attempt %s/%s): %s",
                    address, address + count - 1, attempt + 1, MAX_READ_RETRIES, err,
                )
                await self._reset_client()

            if attempt < MAX_READ_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        raise Exception(f"Modbus read error after {MAX_READ_RETRIES} attempts: {last_error}")

    async def read_realtime_data(self):
        """Read the raw registers. Scaling is applied by the sensor entities."""
        result = await self._read_input_registers(address=1, count=2)

        await asyncio.sleep(0.1)
        return {
            # The temperature register is signed so it can report below zero
            "temperature": self._to_signed(result.registers[0]),
            "humidity":    result.registers[1],
        }
    
    @staticmethod
    def _to_signed(val):
        return val if val < 0x8000 else val - 0x10000

    async def read_settings(self):
        await self.connect()
        client = self._client

        result = await client.read_holding_registers(
            address=REG_DEVICE_ID,
            count=4,
            device_id=self.unit
        )
        if result.isError():
            raise Exception(f"Modbus read error (settings): {result}")

        raw = result.registers

        # Some sensors store the actual baud rate, others a code (0/1/2)
        if raw[1] in BAUDRATE_VALUES:
            baudrate = raw[1]
        else:
            baudrate = BAUDRATE_CODES.get(raw[1])
            if baudrate is None:
                _LOGGER.warning("Unknown baud rate in the settings register: %s", raw[1])

        return {
            "device_id": raw[0],
            "baudrate":  baudrate,
            "temp_offset": self._to_signed(raw[2]) / 10.0,
            "hum_offset":  self._to_signed(raw[3]) / 10.0,
        }       

    async def write_device_settings(self, device_id: int = None, baudrate: int = None):
        """Write the device ID and/or the baud rate. Only given values are written."""
        await self.connect()

        if device_id is not None:
            await self._write_register(REG_DEVICE_ID, device_id)
            # Any further write has to address the sensor on its new device ID
            self.unit = device_id

        if baudrate is not None:
            if baudrate not in BAUDRATE_VALUES:
                raise ValueError(f"Unsupported baud rate: {baudrate}")
            # The sensor answers on the new baud rate from here on
            await self._write_register(REG_BAUDRATE, await self._baudrate_register_value(baudrate))
            self.baudrate = baudrate

    async def _baudrate_register_value(self, baudrate: int) -> int:
        """Return the value to write, in the same format the sensor uses itself."""
        current = await self._client.read_holding_registers(
            address=REG_BAUDRATE,
            count=1,
            device_id=self.unit
        )
        if not current.isError() and current.registers[0] in BAUDRATE_CODES:
            # This sensor stores a code instead of the actual baud rate
            return BAUDRATE_VALUES[baudrate]
        return baudrate

    async def _write_register(self, address: int, value: int):
        res = await self._client.write_register(
            address=address,
            value=value & 0xFFFF,
            device_id=self.unit
        )
        if res.isError():
            raise Exception(f"Failed to write register {address}: {res}")


    async def write_correction_settings(self, temp_offset: int, hum_offset: int):
        await self.connect()
        client = self._client

        try:
            temp_payload = ModbusTcpClient.convert_to_registers(
                [int(temp_offset * 10)],
                data_type=ModbusTcpClient.DATATYPE.INT16,
                word_order='big',
            )

            hum_payload = ModbusTcpClient.convert_to_registers(
                [int(hum_offset * 10)],
                data_type=ModbusTcpClient.DATATYPE.INT16,
                word_order='big',
            )

            payload = temp_payload + hum_payload

            res = await client.write_registers(
                address=REG_TEMP_OFFSET,
                values=payload,
                device_id=self.unit
            )
            if res.isError():
                raise Exception(f"Modbus write error: {res}")

        except Exception as e:
            _LOGGER.warning("Unable to write correction offsets to the sensor: %s", e)
            raise
