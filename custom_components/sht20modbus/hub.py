from pymodbus.client import AsyncModbusSerialClient
from pymodbus.client.tcp    import AsyncModbusTcpClient
from pymodbus.client import ModbusTcpClient
from pymodbus.constants import Endian


import asyncio, logging

_LOGGER = logging.getLogger(__name__)

class ShtModbusHub:
    def __init__(self, hass, name, mode, unit_id, host=None, port=None, device=None, baudrate=None, multiplier=0.1):
        self.hass     = hass
        self.name     = name
        self.mode     = mode
        self.unit     = unit_id
        self.host     = host
        self.port     = port
        self.device   = device
        self.baudrate = baudrate
        self.multiplier = multiplier
        self._client  = None

    async def connect(self):
        if self._client and self._client.connected:
            return

        if self.mode == "tcp":
            self._client = AsyncModbusTcpClient(host=self.host, port=self.port)
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
        await self._client.close()
        self._client = None
        
    async def read_realtime_data(self):
        await self.connect()
        result = await self._client.read_input_registers(
            1, count=2, slave=self.unit
        )
        if result.isError():
            raise Exception(f"Modbus read error (realtime): {result}")

        await asyncio.sleep(0.1)
        return {
            "temperature": result.registers[0] * self.multiplier,
            "humidity":    result.registers[1] * self.multiplier,
        }
    
    @staticmethod
    def _to_signed(val):
        return val if val < 0x8000 else val - 0x10000

    async def read_settings(self):
        await self.connect()
        result = await self._client.read_holding_registers(
            257, count=4, slave=self.unit
        )
        if result.isError():
            raise Exception(f"Modbus read error (settings): {result}")

        raw = result.registers
        
        return {
            "device_id": raw[0],
            "baudrate":  raw[1],
            "temp_offset": self._to_signed(raw[2]) / 10.0,
            "hum_offset":  self._to_signed(raw[3]) / 10.0,
        }       

    async def write_device_settings(self, device_id: int, baudrate: int):
        await self.connect()
        for addr, val in ((257, device_id), (258, baudrate)):  # Let op: correcte adressen!
            val_unsigned = val & 0xFFFF
            res = await self._client.write_register(addr, val_unsigned, slave=self.unit)
            if res.isError():
                raise Exception(f"Failed to write register {addr}: {res}")
        

    async def write_correction_settings(self, temp_offset: int, hum_offset: int):
        await self.connect()

        try:
            payload = ModbusTcpClient.convert_to_registers(
                [int(temp_offset * 10), int(hum_offset * 10)],
                data_type=ModbusTcpClient.DATATYPE.INT16,
                word_order=Endian.BIG,
            )

            
            res = await self._client.write_registers(259, payload, slave=self.unit)
            if res.isError():
                raise Exception(f"Modbus write error: {res}")

        except Exception as e:
            _LOGGER.warning("Unable to write correction offsets to the sensor: %s", e)
            raise