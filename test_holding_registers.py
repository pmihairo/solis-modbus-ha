"""Probe Solis hybrid inverter holding registers (43xxx range) via function code 0x03.

Discovers which writable/control registers the inverter responds to.

Usage:
    pip install pymodbus
    python test_holding_registers.py <host> [--port 502] [--slave-id 1]
"""

import argparse
import asyncio
import struct
import sys

from pymodbus.client import AsyncModbusTcpClient


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


INTER_FRAME_DELAY = 0.35  # >300ms required by datalogger


async def read_holding(client, address, count, slave_id):
    """Read holding registers using function code 0x03."""
    result = await client.read_holding_registers(address=address, count=count, slave=slave_id)
    if result.isError():
        return None
    await asyncio.sleep(INTER_FRAME_DELAY)
    return result.registers


def section(title):
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


async def probe_range(client, slave_id, start, count, label):
    """Probe a range of holding registers and print any that respond."""
    section(f"{label} (registers {start}-{start + count - 1})")
    regs = await read_holding(client, start, count, slave_id)
    if regs is None:
        print("  No response (registers not supported)")
        return None
    for i, val in enumerate(regs):
        addr = start + i
        if val != 0:
            print(f"  {addr}: 0x{val:04X} ({val})")
        else:
            print(f"  {addr}: 0")
    return regs


STORAGE_MODE_FLAGS = {
    0: "Self-consumption",
    1: "Time-charging",
    2: "Off-grid",
    3: "Battery wakeup",
    4: "Battery reserve",
    5: "Grid charge allowed",
}


async def main(host: str, port: int, slave_id: int):
    print(f"Connecting to {host}:{port} (slave ID {slave_id})...")
    client = AsyncModbusTcpClient(host=host, port=port, timeout=10)
    await client.connect()

    if not client.connected:
        print("FAILED to connect.")
        sys.exit(1)

    print("Connected!\n")
    print("Probing holding registers (function code 0x03)...")
    print("Registers that return errors are not supported by this inverter.")

    try:
        # --- Battery settings (from hybrid doc page 17, readable at 33200-33214) ---
        # Try the corresponding holding register addresses
        section("BATTERY SETTINGS - try 43200 range")
        regs = await read_holding(client, 43200, 15, slave_id)
        if regs:
            print(f"  43200 Backup circuit enable:    0x{_u16(regs, 0):04X} (0=disable, 1=enable)")
            print(f"  43201 Backup ref voltage:       {_u16(regs, 1) * 0.1:.1f} V")
            print(f"  43202 Backup ref frequency:     {_u16(regs, 2) * 0.01:.2f} Hz")
            print(f"  43203 Bat charge/discharge en:  0x{_u16(regs, 3):04X} (0=disable, 1=enable)")
            print(f"  43204 Bat charge/discharge dir: 0x{_u16(regs, 4):04X} (0=charge, 1=discharge)")
            print(f"  43205 Bat charge/discharge I:   {_u16(regs, 5) * 0.1:.1f} A")
            print(f"  43206 Bat max charge current:   {_u16(regs, 6) * 0.1:.1f} A")
            print(f"  43207 Bat max discharge current:{_u16(regs, 7) * 0.1:.1f} A")
            print(f"  43208 Bat undervoltage prot:    {_u16(regs, 8) * 0.1:.1f} V")
            print(f"  43209 Bat floating-charge V:    {_u16(regs, 9) * 0.1:.1f} V")
            print(f"  43210 Bat equal-charge V:       {_u16(regs, 10) * 0.1:.1f} V")
            print(f"  43211 Bat overvoltage prot:     {_u16(regs, 11) * 0.1:.1f} V")
            print(f"  43212 Voltage droop:            0x{_u16(regs, 12):04X} (0=disable, 1=enable)")
            print(f"  43213 Over discharge SOC:       {_u16(regs, 13)}%")
            print(f"  43214 Force charge SOC:         {_u16(regs, 14)}%")
        else:
            print("  No response at 43200 range")

        # --- Try the same settings at 33200 range with function code 0x03 ---
        section("BATTERY SETTINGS - try 33200 range (fc 0x03)")
        regs = await read_holding(client, 33200, 15, slave_id)
        if regs:
            print(f"  33200 Backup circuit enable:    0x{_u16(regs, 0):04X} (0=disable, 1=enable)")
            print(f"  33201 Backup ref voltage:       {_u16(regs, 1) * 0.1:.1f} V")
            print(f"  33202 Backup ref frequency:     {_u16(regs, 2) * 0.01:.2f} Hz")
            print(f"  33203 Bat charge/discharge en:  0x{_u16(regs, 3):04X} (0=disable, 1=enable)")
            print(f"  33204 Bat charge/discharge dir: 0x{_u16(regs, 4):04X} (0=charge, 1=discharge)")
            print(f"  33205 Bat charge/discharge I:   {_u16(regs, 5) * 0.1:.1f} A")
            print(f"  33206 Bat max charge current:   {_u16(regs, 6) * 0.1:.1f} A")
            print(f"  33207 Bat max discharge current:{_u16(regs, 7) * 0.1:.1f} A")
            print(f"  33208 Bat undervoltage prot:    {_u16(regs, 8) * 0.1:.1f} V")
            print(f"  33209 Bat floating-charge V:    {_u16(regs, 9) * 0.1:.1f} V")
            print(f"  33210 Bat equal-charge V:       {_u16(regs, 10) * 0.1:.1f} V")
            print(f"  33211 Bat overvoltage prot:     {_u16(regs, 11) * 0.1:.1f} V")
            print(f"  33212 Voltage droop:            0x{_u16(regs, 12):04X} (0=disable, 1=enable)")
            print(f"  33213 Over discharge SOC:       {_u16(regs, 13)}%")
            print(f"  33214 Force charge SOC:         {_u16(regs, 14)}%")
        else:
            print("  No response at 33200 range")

        # --- Storage control / remote control (from revision history: 43132-43136) ---
        section("STORAGE CONTROL - try 43132 range")
        regs = await read_holding(client, 43132, 10, slave_id)
        if regs:
            mode_val = _u16(regs, 0)
            active = [name for bit, name in STORAGE_MODE_FLAGS.items() if mode_val & (1 << bit)]
            print(f"  43132 Storage control mode:     0x{mode_val:04X} -> {', '.join(active) if active else 'None'}")
            for i in range(1, min(len(regs), 10)):
                addr = 43132 + i
                val = _u16(regs, i)
                print(f"  {addr}: 0x{val:04X} ({val})")
        else:
            print("  No response at 43132 range")

        # --- Try storage control at 33132 with fc 0x03 ---
        section("STORAGE CONTROL - try 33132 range (fc 0x03)")
        regs = await read_holding(client, 33132, 10, slave_id)
        if regs:
            mode_val = _u16(regs, 0)
            active = [name for bit, name in STORAGE_MODE_FLAGS.items() if mode_val & (1 << bit)]
            print(f"  33132 Storage control mode:     0x{mode_val:04X} -> {', '.join(active) if active else 'None'}")
            for i in range(1, min(len(regs), 10)):
                addr = 33132 + i
                val = _u16(regs, i)
                print(f"  {addr}: 0x{val:04X} ({val})")
        else:
            print("  No response at 33132 range")

        # --- Max charge/discharge limits (from revision history: 43117-43118) ---
        section("CHARGE/DISCHARGE LIMITS - try 43117 range")
        regs = await read_holding(client, 43117, 2, slave_id)
        if regs:
            print(f"  43117 Max charge limit:         {_u16(regs, 0) * 0.1:.1f} A")
            print(f"  43118 Max discharge limit:      {_u16(regs, 1) * 0.1:.1f} A")
        else:
            print("  No response at 43117 range")

        # --- Time-of-use / time-charging registers (commonly 43353-43400 in Solis hybrids) ---
        section("TIME-OF-USE SETTINGS - try 43353 range")
        regs = await read_holding(client, 43353, 20, slave_id)
        if regs:
            for i, val in enumerate(regs):
                addr = 43353 + i
                print(f"  {addr}: 0x{val:04X} ({val})")
        else:
            print("  No response at 43353 range")

        # --- Inverter ON/OFF (function code 0x05 equivalent, try as holding) ---
        section("INVERTER ON/OFF - try 43007-43009")
        regs = await read_holding(client, 43007, 3, slave_id)
        if regs:
            for i, val in enumerate(regs):
                addr = 43007 + i
                label = {0: "ON/OFF", 1: "Reserve", 2: "Battery model"}.get(i, "")
                print(f"  {addr} {label}: 0x{val:04X} ({val})")
        else:
            print("  No response at 43007 range")

        # --- Working mode (from grid-tied doc, may apply to hybrid) ---
        section("WORKING MODE - try 43050-43055")
        regs = await read_holding(client, 43050, 6, slave_id)
        if regs:
            modes = {0: "No response", 1: "Volt-watt default", 2: "Volt-var",
                     3: "Fixed PF", 4: "Fix reactive", 5: "Power-PF", 6: "Rule21 Volt-watt"}
            val = _u16(regs, 0)
            print(f"  43050 Working mode:             {val} -> {modes.get(val, 'Unknown')}")
            for i in range(1, len(regs)):
                addr = 43050 + i
                print(f"  {addr}: 0x{_u16(regs, i):04X} ({_u16(regs, i)})")
        else:
            print("  No response at 43050 range")

        # --- Broad scan of 43000-43020 ---
        await probe_range(client, slave_id, 43000, 20, "BROAD SCAN 43000-43019")

        # --- Broad scan of 43100-43150 ---
        await probe_range(client, slave_id, 43100, 50, "BROAD SCAN 43100-43149")

        # --- Broad scan of 43300-43400 (time-of-use often lives here) ---
        await probe_range(client, slave_id, 43300, 50, "BROAD SCAN 43300-43349")
        await probe_range(client, slave_id, 43350, 50, "BROAD SCAN 43350-43399")

    except Exception as e:
        print(f"\nError: {e}")

    finally:
        client.close()
        print("\nDone.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Probe Solis holding registers (43xxx)")
    parser.add_argument("host", help="Inverter/datalogger IP address")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--slave-id", type=int, default=1)
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port, args.slave_id))
