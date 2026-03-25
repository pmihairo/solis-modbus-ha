"""Test writable registers on a Solis hybrid inverter.

For each register:
  1. Read the current value
  2. Write a safe test value (slightly offset from current)
  3. Read back to verify the write took
  4. Revert to the original value
  5. Read back to verify the revert

Tested registers:
  - 33206-33207: Battery max charge/discharge current (via fc 0x03/0x06, hybrid doc)
  - 33213-33214: Over-discharge SOC / Force charge SOC (via fc 0x03/0x06, hybrid doc)
  - 43117-43118: Max charge/discharge limits (via fc 0x03/0x06, grid-tied doc)

Usage:
    python test_writable_registers.py <host> [--port 502] [--slave-id 1] [--dry-run]
"""

import argparse
import asyncio
import sys

from pymodbus.client import AsyncModbusTcpClient

INTER_FRAME_DELAY = 0.35  # >300ms required by datalogger


class RegisterTest:
    """Definition of a single register to test."""

    def __init__(self, address, name, unit, scale, min_val, max_val, default,
                 fc_read=0x03, fc_write=0x06):
        self.address = address
        self.name = name
        self.unit = unit
        self.scale = scale        # multiply raw register by this for display
        self.min_val = min_val    # raw min
        self.max_val = max_val    # raw max
        self.default = default    # documented default (raw)
        self.fc_read = fc_read
        self.fc_write = fc_write


# --- Register definitions ---

TESTS = [
    # Battery max charge/discharge current (hybrid doc page 17, 33200 range)
    # Readable at 33206 via fc 0x04, writable at 43206 via fc 0x06
    # Also readable at 43206 via fc 0x03
    RegisterTest(
        address=43206,
        name="Battery Max Charge Current",
        unit="A", scale=0.1,
        min_val=0, max_val=700, default=700,  # 700 * 0.1 = 70A
    ),
    RegisterTest(
        address=43207,
        name="Battery Max Discharge Current",
        unit="A", scale=0.1,
        min_val=0, max_val=700, default=700,
    ),

    # Over-discharge SOC / Force charge SOC (hybrid doc page 17)
    # Readable at 33213 via fc 0x04, writable at 43213 via fc 0x06
    RegisterTest(
        address=43213,
        name="Over-discharge SOC",
        unit="%", scale=1,
        min_val=0, max_val=100, default=20,
    ),
    RegisterTest(
        address=43214,
        name="Force Charge SOC",
        unit="%", scale=1,
        min_val=0, max_val=100, default=10,
    ),

    # Max charge/discharge limits (grid-tied doc revision history: 43117-43118)
    RegisterTest(
        address=43117,
        name="Max Charge Limit",
        unit="A", scale=0.1,
        min_val=0, max_val=700, default=None,  # unknown default
    ),
    RegisterTest(
        address=43118,
        name="Max Discharge Limit",
        unit="A", scale=0.1,
        min_val=0, max_val=700, default=None,
    ),
]

# Corresponding input registers (fc 0x04) to verify the inverter applied the value
# Maps holding register address -> input register address
VERIFY_INPUT_MAP = {
    43206: 33206,  # Battery max charge current
    43207: 33207,  # Battery max discharge current
    43213: 33213,  # Over-discharge SOC
    43214: 33214,  # Force charge SOC
    # 43117/43118 don't have known input register mirrors
}


def fmt_val(raw, scale, unit):
    """Format a raw register value for display."""
    if scale == 1:
        return f"{raw}{unit}"
    return f"{raw * scale:.1f}{unit}"


async def read_holding(client, address, slave_id):
    """Read a single holding register (fc 0x03)."""
    result = await client.read_holding_registers(address=address, count=1, slave=slave_id)
    await asyncio.sleep(INTER_FRAME_DELAY)
    if result.isError():
        return None
    return result.registers[0]


async def read_input(client, address, slave_id):
    """Read a single input register (fc 0x04)."""
    result = await client.read_input_registers(address=address, count=1, slave=slave_id)
    await asyncio.sleep(INTER_FRAME_DELAY)
    if result.isError():
        return None
    return result.registers[0]


async def write_holding(client, address, value, slave_id):
    """Write a single holding register (fc 0x06)."""
    result = await client.write_register(address=address, value=value, slave=slave_id)
    await asyncio.sleep(INTER_FRAME_DELAY)
    if result.isError():
        return False
    return True


def pick_test_value(current, min_val, max_val):
    """Choose a test value that differs from current but stays in range.

    Strategy: offset by +1 if possible, otherwise -1.
    """
    if current + 1 <= max_val:
        return current + 1
    if current - 1 >= min_val:
        return current - 1
    # Range is a single value; can't change it
    return None


async def run_test(client, slave_id, reg, dry_run=False):
    """Run the read-write-verify-revert cycle for one register."""
    print(f"\n{'─' * 60}")
    print(f"  {reg.address}: {reg.name}")
    print(f"{'─' * 60}")

    # Step 1: Read current value from holding register
    current = await read_holding(client, reg.address, slave_id)
    if current is None:
        print(f"  READ FAILED — register not supported or not accessible")
        return False

    print(f"  Current value:  {fmt_val(current, reg.scale, reg.unit)}  (raw: {current})")

    # Also read the corresponding input register if available
    input_addr = VERIFY_INPUT_MAP.get(reg.address)
    if input_addr:
        input_val = await read_input(client, input_addr, slave_id)
        if input_val is not None:
            print(f"  Input reg {input_addr}: {fmt_val(input_val, reg.scale, reg.unit)}  (raw: {input_val})")

    if dry_run:
        print(f"  [DRY RUN] Skipping write/revert")
        return True

    # Step 2: Pick a test value and write it
    test_val = pick_test_value(current, reg.min_val, reg.max_val)
    if test_val is None:
        print(f"  SKIP — cannot pick a different test value (range is single value)")
        return True

    print(f"  Writing test:   {fmt_val(test_val, reg.scale, reg.unit)}  (raw: {test_val})")
    ok = await write_holding(client, reg.address, test_val, slave_id)
    if not ok:
        print(f"  WRITE FAILED")
        return False

    # Step 3: Read back holding register to verify write
    readback = await read_holding(client, reg.address, slave_id)
    if readback is None:
        print(f"  VERIFY FAILED — could not read back after write")
        # Try to revert anyway
    elif readback == test_val:
        print(f"  Holding verify: OK  ({fmt_val(readback, reg.scale, reg.unit)})")
    else:
        print(f"  Holding verify: MISMATCH  expected raw {test_val}, got {readback}")

    # Step 4: Check input register to see if inverter applied the change
    if input_addr:
        # Give the inverter a moment to apply
        await asyncio.sleep(0.5)
        input_after = await read_input(client, input_addr, slave_id)
        if input_after is not None:
            if input_after == test_val:
                print(f"  Input verify:   OK  (reg {input_addr} = {fmt_val(input_after, reg.scale, reg.unit)})")
            else:
                print(f"  Input verify:   MISMATCH  reg {input_addr} = raw {input_after}, expected {test_val}")
                print(f"                  (inverter may not have applied yet or register is read-only)")

    # Step 5: Wait for user to verify inverter behaviour
    input("  >>> Press Enter when ready to revert...")

    # Step 6: Revert to original value
    print(f"  Reverting to:   {fmt_val(current, reg.scale, reg.unit)}  (raw: {current})")
    ok = await write_holding(client, reg.address, current, slave_id)
    if not ok:
        print(f"  REVERT FAILED — register may be stuck at test value!")
        return False

    # Step 7: Verify revert
    final = await read_holding(client, reg.address, slave_id)
    if final is None:
        print(f"  REVERT VERIFY FAILED — could not read back")
        return False
    elif final == current:
        print(f"  Revert verify:  OK")
    else:
        print(f"  Revert verify:  MISMATCH  expected raw {current}, got {final}")
        return False

    return True


async def main(host: str, port: int, slave_id: int, dry_run: bool):
    print(f"Connecting to {host}:{port} (slave ID {slave_id})...")
    client = AsyncModbusTcpClient(host=host, port=port, timeout=10)
    await client.connect()

    if not client.connected:
        print("FAILED to connect.")
        sys.exit(1)

    print("Connected!")
    if dry_run:
        print("DRY RUN mode — will only read, no writes.")

    print(f"\nTesting {len(TESTS)} writable registers...")

    results = {}
    try:
        for reg in TESTS:
            ok = await run_test(client, slave_id, reg, dry_run)
            results[reg.address] = (reg.name, ok)
    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        client.close()

    # Summary
    print(f"\n{'=' * 60}")
    print("SUMMARY")
    print(f"{'=' * 60}")
    for addr, (name, ok) in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  {addr} {name:.<40s} {status}")

    failed = sum(1 for _, ok in results.values() if not ok)
    print(f"\n{len(results)} tested, {len(results) - failed} passed, {failed} failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Test writable registers on Solis hybrid inverter")
    parser.add_argument("host", help="Inverter/datalogger IP address")
    parser.add_argument("--port", type=int, default=502)
    parser.add_argument("--slave-id", type=int, default=1)
    parser.add_argument("--dry-run", action="store_true",
                        help="Only read registers, do not write")
    args = parser.parse_args()

    asyncio.run(main(args.host, args.port, args.slave_id, args.dry_run))
