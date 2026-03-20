"""DataUpdateCoordinator for Solis Modbus."""

from __future__ import annotations

import logging
import struct
from datetime import timedelta

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_HOST, CONF_PORT, CONF_SLAVE_ID, CONF_SCAN_INTERVAL
from .modbus_helpers import read_input_registers

_LOGGER = logging.getLogger(__name__)


def _u16(registers: list[int], index: int) -> int:
    """Read unsigned 16-bit value."""
    return registers[index]


def _s16(registers: list[int], index: int) -> int:
    """Read signed 16-bit value."""
    val = registers[index]
    return val if val < 0x8000 else val - 0x10000


def _u32(registers: list[int], index: int) -> int:
    """Read unsigned 32-bit value (high word first)."""
    return (registers[index] << 16) | registers[index + 1]


def _s32(registers: list[int], index: int) -> int:
    """Read signed 32-bit value (high word first)."""
    raw = (registers[index] << 16) | registers[index + 1]
    return struct.unpack(">i", struct.pack(">I", raw))[0]


class SolisModbusCoordinator(DataUpdateCoordinator):
    """Coordinator to manage fetching Solis inverter data via Modbus TCP."""

    def __init__(self, hass: HomeAssistant, config: dict) -> None:
        """Initialize the coordinator."""
        self._host = config[CONF_HOST]
        self._port = config[CONF_PORT]
        self._slave_id = config[CONF_SLAVE_ID]
        self._client: AsyncModbusTcpClient | None = None

        super().__init__(
            hass,
            _LOGGER,
            name="Solis Modbus",
            update_interval=timedelta(seconds=config[CONF_SCAN_INTERVAL]),
        )

    async def _async_setup(self) -> None:
        """Set up the Modbus client."""
        self._client = AsyncModbusTcpClient(
            host=self._host,
            port=self._port,
            timeout=10,
        )

    async def _ensure_connected(self) -> None:
        """Ensure the Modbus client is connected."""
        if self._client is None:
            await self._async_setup()
        if not self._client.connected:
            await self._client.connect()
            if not self._client.connected:
                raise UpdateFailed(
                    f"Unable to connect to Solis inverter at {self._host}:{self._port}"
                )

    async def _read_input_registers(self, address: int, count: int) -> list[int]:
        """Read input registers (function code 0x04)."""
        result = await read_input_registers(
            self._client, address, count, self._slave_id
        )
        if result.isError():
            raise UpdateFailed(f"Modbus error reading register {address}: {result}")
        return result.registers

    async def _async_update_data(self) -> dict:
        """Fetch data from the inverter."""
        try:
            await self._ensure_connected()
        except Exception as err:
            raise UpdateFailed(f"Connection error: {err}") from err

        data = {}
        try:
            # Block 1: Model and serial info (33000-33027)
            regs = await self._read_input_registers(33000, 28)
            data["model_no"] = _u16(regs, 0)
            data["dsp_version"] = _u16(regs, 1)

            # Serial number (33004-33019) - 16 registers, 2 ASCII chars each
            sn_chars = []
            for i in range(4, 20):
                val = _u16(regs, i)
                high = (val >> 8) & 0xFF
                low = val & 0xFF
                if high > 0:
                    sn_chars.append(chr(high))
                if low > 0:
                    sn_chars.append(chr(low))
            data["serial_number"] = "".join(sn_chars)

            # Block 2: Energy data (33029-33040)
            regs = await self._read_input_registers(33029, 12)
            data["total_energy"] = _u32(regs, 0)  # kWh
            data["month_energy"] = _u32(regs, 2)  # kWh
            data["last_month_energy"] = _u32(regs, 4)  # kWh
            data["today_energy"] = _u16(regs, 6) * 0.1  # kWh
            data["yesterday_energy"] = _u16(regs, 7) * 0.1  # kWh
            data["year_energy"] = _u32(regs, 8)  # kWh
            data["last_year_energy"] = _u32(regs, 10)  # kWh

            # Block 3: DC inputs and power (33049-33058)
            regs = await self._read_input_registers(33049, 10)
            data["dc_voltage_1"] = _u16(regs, 0) * 0.1  # V
            data["dc_current_1"] = _u16(regs, 1) * 0.1  # A
            data["dc_voltage_2"] = _u16(regs, 2) * 0.1  # V
            data["dc_current_2"] = _u16(regs, 3) * 0.1  # A
            data["dc_voltage_3"] = _u16(regs, 4) * 0.1  # V
            data["dc_current_3"] = _u16(regs, 5) * 0.1  # A
            data["dc_voltage_4"] = _u16(regs, 6) * 0.1  # V
            data["dc_current_4"] = _u16(regs, 7) * 0.1  # A
            data["total_dc_power"] = _u32(regs, 8)  # W

            # Block 4: AC output, grid, temperature (33071-33095)
            regs = await self._read_input_registers(33071, 25)
            data["dc_bus_voltage"] = _u16(regs, 0) * 0.1  # V
            data["ac_voltage_a"] = _u16(regs, 2) * 0.1  # V
            data["ac_voltage_b"] = _u16(regs, 3) * 0.1  # V
            data["ac_voltage_c"] = _u16(regs, 4) * 0.1  # V
            data["ac_current_a"] = _u16(regs, 5) * 0.1  # A
            data["ac_current_b"] = _u16(regs, 6) * 0.1  # A
            data["ac_current_c"] = _u16(regs, 7) * 0.1  # A
            data["active_power"] = _s32(regs, 8)  # W
            data["reactive_power"] = _s32(regs, 10)  # Var
            data["apparent_power"] = _s32(regs, 12)  # VA
            data["inverter_temperature"] = _s16(regs, 22) * 0.1  # °C
            data["grid_frequency"] = _u16(regs, 23) * 0.01  # Hz
            data["inverter_status"] = _u16(regs, 24)

            # Block 5: Meter and battery (33126-33148)
            regs = await self._read_input_registers(33126, 23)
            data["meter_total_active_energy"] = _u32(regs, 0)  # Wh
            data["meter_active_power"] = _s32(regs, 4)  # W
            data["battery_voltage"] = _u16(regs, 7) * 0.1  # V
            data["battery_current"] = _s16(regs, 8) * 0.1  # A
            data["battery_current_direction"] = _u16(regs, 9)  # 0=charge, 1=discharge
            data["battery_soc"] = _u16(regs, 13)  # %
            data["battery_soh"] = _u16(regs, 14)  # %
            data["household_load_power"] = _u16(regs, 21)  # W
            data["backup_load_power"] = _u16(regs, 22)  # W

            # Block 6: Battery power and inverting power (33149-33157)
            regs = await self._read_input_registers(33149, 9)
            data["battery_power"] = _s32(regs, 0)  # W
            data["grid_port_power"] = _s32(regs, 2)  # W (+ to grid, - from grid)

            # Block 7: Battery energy (33161-33180)
            regs = await self._read_input_registers(33161, 20)
            data["battery_total_charge_energy"] = _u32(regs, 0)  # kWh
            data["today_battery_charge_energy"] = _u16(regs, 2) * 0.1  # kWh
            data["battery_total_discharge_energy"] = _u32(regs, 4)  # kWh
            data["today_battery_discharge_energy"] = _u16(regs, 6) * 0.1  # kWh
            data["total_grid_import_energy"] = _u32(regs, 8)  # kWh
            data["today_grid_import_energy"] = _u16(regs, 10) * 0.1  # kWh
            data["total_grid_export_energy"] = _u32(regs, 12)  # kWh
            data["today_grid_export_energy"] = _u16(regs, 14) * 0.1  # kWh
            data["total_load_energy"] = _u32(regs, 16)  # kWh
            data["today_load_energy"] = _u16(regs, 18) * 0.1  # kWh

            # Block 8: Storage control mode (33132)
            regs = await self._read_input_registers(33132, 1)
            data["storage_control_mode"] = _u16(regs, 0)

        except Exception as err:
            raise UpdateFailed(f"Error reading data: {err}") from err

        return data

    async def async_shutdown(self) -> None:
        """Close the Modbus connection."""
        if self._client and self._client.connected:
            self._client.close()
