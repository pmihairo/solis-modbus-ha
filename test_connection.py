"""Standalone test script for Solis Modbus TCP connection.

Usage:
    pip install pymodbus
    python test_connection.py <host> [--port 502] [--slave-id 1]
"""

import argparse
import asyncio
import struct
import sys

from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException


def _u16(regs, i):
    return regs[i]

def _s16(regs, i):
    val = regs[i]
    return val if val < 0x8000 else val - 0x10000

def _u32(regs, i):
    return (regs[i] << 16) | regs[i + 1]

def _s32(regs, i):
    raw = (regs[i] << 16) | regs[i + 1]
    return struct.unpack(">i", struct.pack(">I", raw))[0]


async def read_registers(client, address, count, slave_id):
    result = await client.read_input_registers(address=address, count=count, slave=slave_id)
    if result.isError():
        print(f"  ERROR reading register {address}: {result}")
        return None
    return result.registers


async def main(host: str, port: int, slave_id: int):
    print(f"Connecting to {host}:{port} (slave ID {slave_id})...")
    client = AsyncModbusTcpClient(host=host, port=port, timeout=10)
    await client.connect()

    if not client.connected:
        print("FAILED to connect.")
        sys.exit(1)

    print("Connected!\n")

    try:
        # --- Inverter model definition ---
        print("=" * 60)
        print("INVERTER MODEL DEFINITION (register 35000)")
        print("=" * 60)
        regs = await read_registers(client, 35000, 1, slave_id)
        if regs:
            val = _u16(regs, 0)
            models = {
                0x0000: "No definition",
                0x1010: "1-phase grid-tied",
                0x1020: "3-phase grid-tied",
                0x2030: "1-phase LV Hybrid",
                0x2031: "1-phase LV AC Couple",
                0x2040: "1-phase HV Hybrid",
                0x2050: "3-phase LV Hybrid",
                0x2060: "3-phase HV Hybrid",
                0x3010: "Off-grid inverter",
            }
            print(f"  Model code: 0x{val:04X} -> {models.get(val, 'Unknown')}")

        # --- Model and serial ---
        print("\n" + "=" * 60)
        print("DEVICE INFO (registers 33000-33027)")
        print("=" * 60)
        regs = await read_registers(client, 33000, 28, slave_id)
        if regs:
            print(f"  Model No:        0x{_u16(regs, 0):04X}")
            print(f"  DSP Version:     0x{_u16(regs, 1):04X}")
            print(f"  HMI Version:     0x{_u16(regs, 2):04X}")
            print(f"  Protocol Ver:    0x{_u16(regs, 3):04X}")

            sn_chars = []
            for i in range(4, 20):
                val = _u16(regs, i)
                high = (val >> 8) & 0xFF
                low = val & 0xFF
                if high > 0:
                    sn_chars.append(chr(high))
                if low > 0:
                    sn_chars.append(chr(low))
            print(f"  Serial Number:   {''.join(sn_chars)}")

        # --- Energy ---
        print("\n" + "=" * 60)
        print("ENERGY (registers 33029-33040)")
        print("=" * 60)
        regs = await read_registers(client, 33029, 12, slave_id)
        if regs:
            print(f"  Total energy:      {_u32(regs, 0)} kWh")
            print(f"  This month:        {_u32(regs, 2)} kWh")
            print(f"  Last month:        {_u32(regs, 4)} kWh")
            print(f"  Today:             {_u16(regs, 6) * 0.1:.1f} kWh")
            print(f"  Yesterday:         {_u16(regs, 7) * 0.1:.1f} kWh")
            print(f"  This year:         {_u32(regs, 8)} kWh")
            print(f"  Last year:         {_u32(regs, 10)} kWh")

        # --- DC inputs ---
        print("\n" + "=" * 60)
        print("DC INPUTS (registers 33049-33058)")
        print("=" * 60)
        regs = await read_registers(client, 33049, 10, slave_id)
        if regs:
            for n in range(4):
                v = _u16(regs, n * 2) * 0.1
                a = _u16(regs, n * 2 + 1) * 0.1
                print(f"  PV{n+1}:  {v:.1f} V  /  {a:.1f} A  ({v * a:.0f} W)")
            print(f"  Total DC Power:  {_u32(regs, 8)} W")

        # --- AC output ---
        print("\n" + "=" * 60)
        print("AC OUTPUT & GRID (registers 33071-33095)")
        print("=" * 60)
        regs = await read_registers(client, 33071, 25, slave_id)
        if regs:
            print(f"  DC Bus Voltage:  {_u16(regs, 0) * 0.1:.1f} V")
            for phase, offset in [("A", 2), ("B", 3), ("C", 4)]:
                v = _u16(regs, offset) * 0.1
                a = _u16(regs, offset + 3) * 0.1
                print(f"  Phase {phase}:  {v:.1f} V  /  {a:.1f} A")
            print(f"  Active Power:    {_s32(regs, 8)} W")
            print(f"  Reactive Power:  {_s32(regs, 10)} var")
            print(f"  Apparent Power:  {_s32(regs, 12)} VA")
            print(f"  Temperature:     {_s16(regs, 22) * 0.1:.1f} C")
            print(f"  Grid Frequency:  {_u16(regs, 23) * 0.01:.2f} Hz")
            status = _u16(regs, 24)
            print(f"  Inverter Status: 0x{status:04X}")

        # --- Meter & Battery ---
        print("\n" + "=" * 60)
        print("METER & BATTERY (registers 33126-33148)")
        print("=" * 60)
        regs = await read_registers(client, 33126, 23, slave_id)
        if regs:
            print(f"  Meter Total Energy:  {_u32(regs, 0)} Wh")
            print(f"  Meter Active Power:  {_s32(regs, 4)} W  (+grid/-load)")
            print(f"  Battery Voltage:     {_u16(regs, 7) * 0.1:.1f} V")
            bat_current = _s16(regs, 8) * 0.1
            direction = "charge" if _u16(regs, 9) == 0 else "discharge"
            print(f"  Battery Current:     {bat_current:.1f} A  ({direction})")
            print(f"  Battery SOC:         {_u16(regs, 13)} %")
            print(f"  Battery SOH:         {_u16(regs, 14)} %")
            print(f"  Household Load:      {_u16(regs, 21)} W")
            print(f"  Backup Load:         {_u16(regs, 22)} W")

        # --- Battery power ---
        print("\n" + "=" * 60)
        print("BATTERY & GRID PORT POWER (registers 33149-33157)")
        print("=" * 60)
        regs = await read_registers(client, 33149, 9, slave_id)
        if regs:
            print(f"  Battery Power:   {_s32(regs, 0)} W")
            gp = _s32(regs, 2)
            print(f"  Grid Port Power: {gp} W  ({'to grid' if gp > 0 else 'from grid'})")

        # --- Battery / Grid / Load energy ---
        print("\n" + "=" * 60)
        print("ENERGY BREAKDOWN (registers 33161-33180)")
        print("=" * 60)
        regs = await read_registers(client, 33161, 20, slave_id)
        if regs:
            print(f"  Battery Charge Total:     {_u32(regs, 0)} kWh")
            print(f"  Battery Charge Today:     {_u16(regs, 2) * 0.1:.1f} kWh")
            print(f"  Battery Discharge Total:  {_u32(regs, 4)} kWh")
            print(f"  Battery Discharge Today:  {_u16(regs, 6) * 0.1:.1f} kWh")
            print(f"  Grid Import Total:        {_u32(regs, 8)} kWh")
            print(f"  Grid Import Today:        {_u16(regs, 10) * 0.1:.1f} kWh")
            print(f"  Grid Export Total:         {_u32(regs, 12)} kWh")
            print(f"  Grid Export Today:         {_u16(regs, 14) * 0.1:.1f} kWh")
            print(f"  Load Total:               {_u32(regs, 16)} kWh")
            print(f"  Load Today:               {_u16(regs, 18) * 0.1:.1f} kWh")

        # --- Storage control mode ---
        print("\n" + "=" * 60)
        print("STORAGE CONTROL MODE (register 33132)")
        print("=" * 60)
        regs = await read_registers(client, 33132, 1, slave_id)
        if regs:
            val = _u16(regs, 0)
            flags = {
                0: "Self-consumption",
                1: "Time-charging",
                2: "Off-grid",
                3: "Battery wakeup",
                4: "Battery reserve",
                5: "Grid charge allowed",
            }
            active = [name for bit, name in flags.items() if val & (1 << bit)]
            print(f"  Raw: 0x{val:04X}  ->  {', '.join(active) if active else 'None'}")

        print("\n" + "=" * 60)
        print("ALL DONE - connection and registers look good!")
        print("=" * 60)

    except (ModbusException, OSError) as err:
        print(f"\nERROR during read: {err}")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test Solis inverter Modbus TCP connection")
    parser.add_argument("host", help="Datalogger IP address")
    parser.add_argument("--port", type=int, default=502, help="Modbus TCP port (default: 502)")
    parser.add_argument("--slave-id", type=int, default=1, help="Modbus slave ID (default: 1)")
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port, args.slave_id))
