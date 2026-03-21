"""Enable or disable grid charging on a Solis hybrid inverter.

Toggles BIT05 (Allow grid to charge battery) in the storage control
mode register (43110) without affecting other mode bits.

Usage:
    python set_grid_charge.py <host> on
    python set_grid_charge.py <host> off
    python set_grid_charge.py <host> status
"""

import argparse
import asyncio
import sys

from pymodbus.client import AsyncModbusTcpClient

REGISTER = 43110
INTER_FRAME_DELAY = 0.35
BIT_GRID_CHARGE = 5  # BIT05: Allow grid to charge battery

STORAGE_MODE_FLAGS = {
    0: "Self-consumption",
    1: "Time-charging",
    2: "Off-grid",
    3: "Battery wakeup",
    4: "Battery reserve",
    5: "Grid charge allowed",
}


def decode_mode(val):
    active = [name for bit, name in STORAGE_MODE_FLAGS.items() if val & (1 << bit)]
    return ", ".join(active) if active else "None"


async def main(host: str, port: int, slave_id: int, action: str):
    client = AsyncModbusTcpClient(host=host, port=port, timeout=10)
    await client.connect()
    if not client.connected:
        print("Failed to connect.")
        sys.exit(1)

    try:
        # Read current value
        result = await client.read_holding_registers(address=REGISTER, count=1, slave=slave_id)
        if result.isError():
            print(f"Error reading register {REGISTER}: {result}")
            sys.exit(1)
        await asyncio.sleep(INTER_FRAME_DELAY)

        current = result.registers[0]
        print(f"Current storage mode: 0x{current:04X} ({current}) -> {decode_mode(current)}")

        if action == "status":
            grid_charge = bool(current & (1 << BIT_GRID_CHARGE))
            print(f"Grid charging: {'ON' if grid_charge else 'OFF'}")
            return

        # Calculate new value
        if action == "on":
            new_val = current | (1 << BIT_GRID_CHARGE)
        else:
            new_val = current & ~(1 << BIT_GRID_CHARGE)

        if new_val == current:
            print(f"Grid charging is already {'ON' if action == 'on' else 'OFF'}, no change needed.")
            return

        # Write new value
        print(f"Setting storage mode: 0x{new_val:04X} ({new_val}) -> {decode_mode(new_val)}")
        result = await client.write_register(address=REGISTER, value=new_val, slave=slave_id)
        if result.isError():
            print(f"Error writing register {REGISTER}: {result}")
            sys.exit(1)
        await asyncio.sleep(INTER_FRAME_DELAY)

        # Verify
        result = await client.read_holding_registers(address=REGISTER, count=1, slave=slave_id)
        if result.isError():
            print(f"Error verifying register {REGISTER}: {result}")
            sys.exit(1)

        verified = result.registers[0]
        if verified == new_val:
            print(f"Verified: 0x{verified:04X} -> {decode_mode(verified)}")
        else:
            print(f"WARNING: Read back 0x{verified:04X} ({decode_mode(verified)}), expected 0x{new_val:04X}")

    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enable/disable grid charging on Solis hybrid inverter")
    parser.add_argument("host", help="Inverter/datalogger IP address")
    parser.add_argument("action", choices=["on", "off", "status"], help="on/off/status")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--slave-id", type=int, default=1)
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port, args.slave_id, args.action))
