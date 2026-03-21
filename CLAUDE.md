# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Standalone Python bridge that reads data from a Solis S6 hybrid inverter via Modbus TCP (through a datalogger) and publishes sensor values to MQTT with Home Assistant auto-discovery. Not a HA custom integration — runs as an independent Docker container or Python script.

## Commands

```bash
# Run directly
pip install -r requirements.txt
python solis2mqtt.py --modbus-host <IP> --mqtt-host <BROKER_IP> --mqtt-user <user> --mqtt-pass <pass>

# Docker
docker build -t solis2mqtt .
docker run -d --network host --name solis2mqtt solis2mqtt --modbus-host <IP> --mqtt-host <BROKER_IP>

# Test Modbus connectivity (no MQTT needed)
python test_connection.py <INVERTER_IP>
```

No test suite or linter is configured.

## Architecture

Single-file application (`solis2mqtt.py`) with a straightforward async loop:

1. **Startup**: Connect to inverter via Modbus TCP, read serial number (register 33000), publish HA MQTT discovery configs
2. **Fast poll loop** (`read_fast`): Reads real-time sensors every cycle (~1.4s for 4 Modbus reads) — PV inputs, AC output, battery, grid, loads
3. **Slow poll** (`read_slow`): Reads energy counters every 300s (2 Modbus reads) — generation totals, battery/grid/load energy
4. **Publish**: Each sensor gets its own MQTT topic under `solis/<serial>/<sensor_key>`

Key data flow: Modbus registers -> `_u16`/`_s16`/`_u32`/`_s32` helpers -> `data` dict -> MQTT publish as `str(value)`

`test_connection.py` is a diagnostic tool that reads and displays all known registers — useful for verifying register behavior before changing `solis2mqtt.py`.

## Modbus Protocol Details

- Function code 0x04 (read input registers), addresses used directly (no offset)
- Connects via datalogger over TCP port 502, not direct RS-485
- Inter-frame delay >300ms required, max 50 registers per read
- Battery current (33134) is unsigned magnitude; direction comes from register 33135 (0=charge, 1=discharge). Battery power (33149-33150) follows the same pattern. Code negates values on discharge.
- Grid port power (33151-33152) is natively signed S32 (+: to grid, -: from grid)
- Reference PDF: `_Without Control Hybrid EN...pdf` (hybrid inverter register map, "Without Control" version — does not include 43xxx writable register addresses)
- Writable/control registers are in the 43xxx range (function codes 0x06/0x10) but not fully documented in the available PDF

## Sensor Definitions

Sensors are defined as `SensorDef` dataclass instances in the `SENSORS` list. Adding a sensor requires:
1. Add `SensorDef` entry to `SENSORS` list (key, name, unit, device_class, state_class)
2. Populate `data[key]` in `read_fast` or `read_slow`
3. The HA discovery and MQTT publishing are automatic from the `SENSORS` list
