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


INTER_FRAME_DELAY = 0.35  # >300ms required by datalogger


async def read_registers(client, address, count, slave_id):
    result = await client.read_input_registers(address=address, count=count, slave=slave_id)
    if result.isError():
        print(f"  ERROR reading register {address}: {result}")
        return None
    await asyncio.sleep(INTER_FRAME_DELAY)
    return result.registers


def section(title):
    print(f"\n{'=' * 60}")
    print(title)
    print("=" * 60)


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
        section("INVERTER MODEL DEFINITION (register 35000)")
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
        section("DEVICE INFO (registers 33000-33027)")
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

            startup = _u16(regs, 20)
            print(f"  Startup Setting: {'Completed' if startup == 1 else 'Not done'} ({startup})")

            year = _u16(regs, 22)
            month = _u16(regs, 23)
            day = _u16(regs, 24)
            hour = _u16(regs, 25)
            minute = _u16(regs, 26)
            second = _u16(regs, 27)
            print(f"  Inverter Clock:  20{year:02d}-{month:02d}-{day:02d} {hour:02d}:{minute:02d}:{second:02d}")

        # --- AC/DC type ---
        section("AC/DC TYPE (registers 33047-33048)")
        regs = await read_registers(client, 33047, 2, slave_id)
        if regs:
            ac_types = {0: "Single Phase", 1: "3P four wires", 2: "3P three wires", 3: "3P four wires OR 3P three wires"}
            dc_types = {0: "0-1 input", 1: "1-2 inputs", 2: "2-3 inputs", 3: "3-4 inputs"}
            print(f"  AC Output Type:  {ac_types.get(_u16(regs, 0), f'Unknown ({_u16(regs, 0)})')}")
            print(f"  DC Input Type:   {dc_types.get(_u16(regs, 1), f'Unknown ({_u16(regs, 1)})')}")

        # --- Energy ---
        section("ENERGY (registers 33029-33040)")
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
        section("DC INPUTS (registers 33049-33058)")
        regs = await read_registers(client, 33049, 10, slave_id)
        if regs:
            for n in range(4):
                v = _u16(regs, n * 2) * 0.1
                a = _u16(regs, n * 2 + 1) * 0.1
                print(f"  PV{n+1}:  {v:.1f} V  /  {a:.1f} A  ({v * a:.0f} W)")
            print(f"  Total DC Power:  {_u32(regs, 8)} W")

        # --- AC output ---
        section("AC OUTPUT & GRID (registers 33071-33096)")
        regs = await read_registers(client, 33071, 26, slave_id)
        if regs:
            print(f"  DC Bus Voltage:      {_u16(regs, 0) * 0.1:.1f} V")
            print(f"  DC Bus Half Voltage: {_u16(regs, 1) * 0.1:.1f} V")
            for phase, offset in [("A", 2), ("B", 3), ("C", 4)]:
                v = _u16(regs, offset) * 0.1
                a = _u16(regs, offset + 3) * 0.1
                print(f"  Phase {phase}:  {v:.1f} V  /  {a:.1f} A")
            print(f"  Active Power:        {_s32(regs, 8)} W")
            print(f"  Reactive Power:      {_s32(regs, 10)} var")
            print(f"  Apparent Power:      {_s32(regs, 12)} VA")

            working_modes = {
                0: "No response mode", 1: "Volt-watt default", 2: "Volt-var",
                3: "Fixed power factor", 4: "Fix reactive power", 5: "Power-PF",
                6: "Rule21 Volt-watt",
            }
            wm = _u16(regs, 20)
            print(f"  Working Mode:        {working_modes.get(wm, f'Unknown ({wm})')}")

            print(f"  Temperature:         {_s16(regs, 22) * 0.1:.1f} °C")
            print(f"  Grid Frequency:      {_u16(regs, 23) * 0.01:.2f} Hz")
            status = _u16(regs, 24)
            print(f"  Inverter Status:     0x{status:04X}")
            print(f"  Lead-acid Bat Temp:  {_s16(regs, 25) * 0.1:.1f} °C")

        # --- Power limits ---
        section("POWER LIMITS (registers 33100-33106)")
        regs = await read_registers(client, 33100, 7, slave_id)
        if regs:
            print(f"  Limit Active Power:      {_s32(regs, 0)} W")
            print(f"  Limit Reactive Power:    {_s32(regs, 2)} var")
            print(f"  Limited Power Actual:    {_u16(regs, 4)}%")
            print(f"  PF Adjustment Actual:    {_s16(regs, 5) * 0.01:.2f}")
            print(f"  Limited Reactive Power:  {_s16(regs, 6)}%")

        # --- Fault codes & operating status ---
        section("FAULT CODES & STATUS (registers 33115-33121)")
        regs = await read_registers(client, 33115, 7, slave_id)
        if regs:
            print(f"  Setting Flag Bit:  0x{_u16(regs, 0):04X}")
            for i in range(1, 6):
                fc = _u16(regs, i)
                if fc:
                    print(f"  Fault Code {i:02d}:    0x{fc:04X}")
                else:
                    print(f"  Fault Code {i:02d}:    None")

            op_status = _u16(regs, 6)
            print(f"  Operating Status:  0x{op_status:04X}")
            op_flags = {
                0: "Normal Operation", 1: "Initializing", 2: "Controlled turning OFF",
                3: "Fault leads to turning OFF", 4: "Stand-by",
                5: "Limited (temp/freq)", 6: "Limited (external)",
                7: "Backup overload", 8: "Load fault (grid normal)",
                9: "Grid fault (grid normal)", 10: "Battery fault (battery normal)",
                12: "Grid Surge (Warn)", 13: "Fan fault (Warn)",
            }
            active = [name for bit, name in op_flags.items() if op_status & (1 << bit)]
            print(f"    Active: {', '.join(active) if active else 'None'}")

        # --- Meter & Battery ---
        section("METER & BATTERY (registers 33126-33148)")
        regs = await read_registers(client, 33126, 23, slave_id)
        if regs:
            print(f"  Meter Total Energy:  {_u32(regs, 0)} Wh")
            print(f"  Meter Active Power:  {_s32(regs, 4)} W  (+grid/-load)")

            # Storage control mode (33132)
            mode_val = _u16(regs, 6)
            flags = {
                0: "Self-consumption", 1: "Time-charging", 2: "Off-grid",
                3: "Battery wakeup", 4: "Battery reserve", 5: "Grid charge allowed",
            }
            active = [name for bit, name in flags.items() if mode_val & (1 << bit)]
            print(f"  Storage Mode:        0x{mode_val:04X} -> {', '.join(active) if active else 'None'}")

            print(f"  Battery Voltage:     {_u16(regs, 7) * 0.1:.1f} V")
            bat_current = _s16(regs, 8) * 0.1
            direction = "charge" if _u16(regs, 9) == 0 else "discharge"
            print(f"  Battery Current:     {bat_current:.1f} A  ({direction})")

            print(f"  LLC Bus Voltage:     {_u16(regs, 10) * 0.1:.1f} V")
            print(f"  Backup AC V (A):     {_u16(regs, 11) * 0.1:.1f} V")
            print(f"  Backup AC I (A):     {_u16(regs, 12) * 0.1:.1f} A")

            print(f"  Battery SOC:         {_u16(regs, 13)}%")
            print(f"  Battery SOH:         {_u16(regs, 14)}%")

            # BMS data (33141-33144)
            print(f"  BMS Bat Voltage:     {_u16(regs, 15) * 0.01:.2f} V")
            print(f"  BMS Bat Current:     {_s16(regs, 16) * 0.1:.1f} A")
            print(f"  BMS Charge Limit:    {_u16(regs, 17) * 0.1:.1f} A")
            print(f"  BMS Discharge Limit: {_u16(regs, 18) * 0.1:.1f} A")

            # Battery fault status
            bfs1 = _u16(regs, 19)
            bfs2 = _u16(regs, 20)
            print(f"  Battery Fault 01:    0x{bfs1:04X}")
            print(f"  Battery Fault 02:    0x{bfs2:04X}")

            print(f"  Household Load:      {_u16(regs, 21)} W")
            print(f"  Backup Load:         {_u16(regs, 22)} W")

        # --- Battery power & backup phases ---
        section("BATTERY, GRID PORT & BACKUP (registers 33149-33160)")
        regs = await read_registers(client, 33149, 12, slave_id)
        if regs:
            print(f"  Battery Power:       {_s32(regs, 0)} W")
            gp = _s32(regs, 2)
            print(f"  Grid Port Power:     {gp} W  ({'to grid' if gp > 0 else 'from grid'})")
            print(f"  Backup AC V (B):     {_u16(regs, 4) * 0.1:.1f} V")
            print(f"  Backup AC I (B):     {_u16(regs, 5) * 0.1:.1f} A")
            print(f"  Backup AC V (C):     {_u16(regs, 6) * 0.1:.1f} V")
            print(f"  Backup AC I (C):     {_u16(regs, 7) * 0.1:.1f} A")
            inv_power = _s16(regs, 8) * 10
            print(f"  Inverting/Rect Power:{inv_power} W")

            bat_detected = _u16(regs, 10)
            print(f"  Battery Detected:    {'Yes' if bat_detected == 1 else 'No'} ({bat_detected})")

            bat_models_lv = {
                0x0000: "No battery", 0x0001: "PYLON_LV", 0x0002: "User define",
                0x0003: "B_BOX_LV BYD",
            }
            bat_models_hv = {
                0x0000: "No battery", 0x0100: "PYLON_HV", 0x0200: "User define",
                0x0300: "B_BOX_HV BYD", 0x0400: "LG_HV LG", 0x0500: "SOLUNA_HV",
            }
            bm = _u16(regs, 11)
            name = bat_models_lv.get(bm) or bat_models_hv.get(bm) or f"Unknown (0x{bm:04X})"
            print(f"  Battery Model:       {name}")

        # --- Battery / Grid / Load energy ---
        section("ENERGY BREAKDOWN (registers 33161-33181)")
        regs = await read_registers(client, 33161, 21, slave_id)
        if regs:
            print(f"  Battery Charge Total:     {_u32(regs, 0)} kWh")
            print(f"  Battery Charge Today:     {_u16(regs, 2) * 0.1:.1f} kWh")
            print(f"  Battery Charge Yesterday: {_u16(regs, 3) * 0.1:.1f} kWh")
            print(f"  Battery Discharge Total:  {_u32(regs, 4)} kWh")
            print(f"  Battery Discharge Today:  {_u16(regs, 6) * 0.1:.1f} kWh")
            print(f"  Battery Discharge Yester: {_u16(regs, 7) * 0.1:.1f} kWh")
            print(f"  Grid Import Total:        {_u32(regs, 8)} kWh")
            print(f"  Grid Import Today:        {_u16(regs, 10) * 0.1:.1f} kWh")
            print(f"  Grid Import Yesterday:    {_u16(regs, 11) * 0.1:.1f} kWh")
            print(f"  Grid Export Total:        {_u32(regs, 12)} kWh")
            print(f"  Grid Export Today:        {_u16(regs, 14) * 0.1:.1f} kWh")
            print(f"  Grid Export Yesterday:    {_u16(regs, 15) * 0.1:.1f} kWh")
            print(f"  Load Total:               {_u32(regs, 16)} kWh")
            print(f"  Load Today:               {_u16(regs, 18) * 0.1:.1f} kWh")
            print(f"  Load Yesterday:           {_u16(regs, 19) * 0.1:.1f} kWh")
            print(f"  Clear Energy Record:      {_u16(regs, 20)}%")

        # --- Battery/backup settings ---
        section("BATTERY & BACKUP SETTINGS (registers 33200-33214)")
        regs = await read_registers(client, 33200, 15, slave_id)
        if regs:
            print(f"  Backup Circuit:      {'Enabled' if _u16(regs, 0) == 1 else 'Disabled'}")
            print(f"  Backup Ref Voltage:  {_u16(regs, 1) * 0.1:.1f} V")
            print(f"  Backup Ref Freq:     {_u16(regs, 2) * 0.01:.2f} Hz")
            print(f"  Bat Charge Enable:   {'Enabled' if _u16(regs, 3) == 1 else 'Disabled'}")
            charge_dir = _u16(regs, 4)
            print(f"  Bat Charge Dir:      {'Charge' if charge_dir == 0 else 'Discharge'}")
            print(f"  Bat Charge Current:  {_u16(regs, 5) * 0.1:.1f} A")
            print(f"  Max Charge Current:  {_u16(regs, 6) * 0.1:.1f} A")
            print(f"  Max Discharge Curr:  {_u16(regs, 7) * 0.1:.1f} A")
            print(f"  Bat Undervolt Prot:  {_u16(regs, 8) * 0.1:.1f} V")
            print(f"  Bat Float Charge V:  {_u16(regs, 9) * 0.1:.1f} V")
            print(f"  Bat Equal Charge V:  {_u16(regs, 10) * 0.1:.1f} V")
            print(f"  Bat Overvolt Prot:   {_u16(regs, 11) * 0.1:.1f} V")
            print(f"  Voltage Droop:       {'Enabled' if _u16(regs, 12) == 1 else 'Disabled'}")
            print(f"  Over Discharge SOC:  {_u16(regs, 13)}%")
            print(f"  Force Charge SOC:    {_u16(regs, 14)}%")

        # --- EPM data ---
        section("EPM DATA (registers 33247-33250)")
        regs = await read_registers(client, 33247, 4, slave_id)
        if regs:
            backflow = _s16(regs, 0) * 100
            print(f"  EPM Backflow Power:  {backflow} W")
            epm_val = _u16(regs, 1)
            print(f"  EPM/FailSafe Switch: 0x{epm_val:04X}")
            print(f"    EPM switch:    {'ON' if epm_val & 0x01 else 'OFF'}")
            print(f"    FailSafe:      {'ON' if epm_val & 0x02 else 'OFF'}")
            rt_backflow = _s16(regs, 2) * 100
            print(f"  EPM RT Backflow:     {rt_backflow} W")
            meter_pos = _u16(regs, 3)
            print(f"  Meter/CT Position:   0x{meter_pos:04X}")
            print(f"    Meter in load: {'Yes' if meter_pos & 0x01 else 'No'}")
            print(f"    Meter in grid: {'Yes' if meter_pos & 0x02 else 'No'}")
            print(f"    CT in grid:    {'Yes' if meter_pos & 0x04 else 'No'}")
            print(f"    EPM switch:    {'ON' if meter_pos & 0x10 else 'OFF'}")
            print(f"    FailSafe:      {'ON' if meter_pos & 0x20 else 'OFF'}")

        # --- Meter per-phase data ---
        section("METER DETAILED (registers 33251-33286)")
        regs = await read_registers(client, 33251, 36, slave_id)
        if regs:
            for i, phase in enumerate(["A", "B", "C"]):
                v = _u16(regs, i * 2) * 0.1
                a = _u16(regs, i * 2 + 1) * 0.01
                print(f"  Meter Phase {phase}:  {v:.1f} V  /  {a:.2f} A")
            for i, phase in enumerate(["A", "B", "C"]):
                p = _s32(regs, 6 + i * 2) * 0.001
                print(f"  Meter Active {phase}:     {p:.3f} kW")
            total_active = _s32(regs, 12) * 0.001
            print(f"  Meter Active Total:  {total_active:.3f} kW")
            for i, phase in enumerate(["A", "B", "C"]):
                p = _s32(regs, 14 + i * 2)
                print(f"  Meter Reactive {phase}:   {p} var")
            total_reactive = _s32(regs, 20)
            print(f"  Meter Reactive Total:{total_reactive} var")
            for i, phase in enumerate(["A", "B", "C"]):
                p = _s32(regs, 22 + i * 2)
                print(f"  Meter Apparent {phase}:   {p} VA")
            total_apparent = _s32(regs, 28)
            print(f"  Meter Apparent Total:{total_apparent} VA")
            pf = _s16(regs, 30) * 0.01
            print(f"  Meter PF:            {pf:.2f}")
            freq = _u16(regs, 31) * 0.01
            print(f"  Meter Grid Freq:     {freq:.2f} Hz")
            meter_import = _u32(regs, 32) * 0.01
            print(f"  Meter Import Total:  {meter_import:.2f} kWh")
            meter_export = _u32(regs, 34) * 0.01
            print(f"  Meter Export Total:  {meter_export:.2f} kWh")

        # --- DOD / EPS settings ---
        section("DOD & EPS SETTINGS (registers 33297-33299)")
        regs = await read_registers(client, 33297, 3, slave_id)
        if regs:
            print(f"  Off-grid DOD:        {_u16(regs, 0)}%")
            print(f"  EPS DOD:             {_u16(regs, 1)}%")
            epstime = _u16(regs, 2) * 10
            print(f"  EPS Switching Time:  {epstime} ms" + (" (invalid - 0 means params invalid)" if epstime == 0 else ""))

        # --- Meter2 (if present) ---
        section("METER 2 (registers 33300-33338)")
        regs = await read_registers(client, 33300, 39, slave_id)
        if regs:
            m1_type = _u16(regs, 0)
            location_map = {0x0100: "Grid", 0x0200: "Load", 0x0300: "Grid+PV (Two Meter)"}
            meter_map = {0x0001: "General 1Ph", 0x0002: "Acrel 3Ph", 0x0003: "General 3Ph",
                         0x0004: "Standard Eastron 1Ph", 0x0005: "Standard Eastron 3Ph", 0x0006: "No Meter"}
            loc = location_map.get(m1_type & 0xFF00, f"Unknown (0x{m1_type & 0xFF00:04X})")
            mtype = meter_map.get(m1_type & 0x00FF, f"Unknown (0x{m1_type & 0x00FF:04X})")
            print(f"  Meter1 Type/Loc:     {loc} / {mtype} (0x{m1_type:04X})")

            m2_type = _u16(regs, 1)
            if m2_type != 0:
                loc2 = location_map.get(m2_type & 0xFF00, f"Unknown (0x{m2_type & 0xFF00:04X})")
                mtype2 = meter_map.get(m2_type & 0x00FF, f"Unknown (0x{m2_type & 0x00FF:04X})")
                print(f"  Meter2 Type/Loc:     {loc2} / {mtype2} (0x{m2_type:04X})")
                for i, phase in enumerate(["A", "B", "C"]):
                    v = _u16(regs, 2 + i * 2) * 0.1
                    a = _u16(regs, 3 + i * 2) * 0.01
                    print(f"  Meter2 Phase {phase}:  {v:.1f} V / {a:.2f} A")
                for i, phase in enumerate(["A", "B", "C"]):
                    p = _s32(regs, 8 + i * 2) * 0.001
                    print(f"  Meter2 Active {phase}:    {p:.3f} kW")
                m2_total = _s32(regs, 14) * 0.001
                print(f"  Meter2 Active Total: {m2_total:.3f} kW")
                m2_pf = _s16(regs, 32) * 0.01 if regs[32] != 0 else 0
                print(f"  Meter2 PF:           {m2_pf:.2f}")
                m2_freq = _u16(regs, 33) * 0.01
                print(f"  Meter2 Grid Freq:    {m2_freq:.2f} Hz")
                m2_import = _u32(regs, 34) * 0.01
                print(f"  Meter2 Import Total: {m2_import:.2f} kWh")
                m2_export = _u32(regs, 36) * 0.01
                print(f"  Meter2 Export Total: {m2_export:.2f} kWh")
            else:
                print(f"  Meter2:              Not configured")

        section("ALL DONE - connection and registers look good!")

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
