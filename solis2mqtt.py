"""Solis S6 Hybrid Inverter -> MQTT bridge with Home Assistant auto-discovery."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import signal
import struct
import sys
from dataclasses import dataclass

from pymodbus.client import AsyncModbusTcpClient
import aiomqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
_LOGGER = logging.getLogger("solis2mqtt")

MQTT_BASE_TOPIC = "solis"
HA_DISCOVERY_PREFIX = "homeassistant"


# --- Modbus helpers ---

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


# --- Sensor definitions ---

@dataclass
class SensorDef:
    key: str
    name: str
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    icon: str | None = None
    precision: int | None = None


SENSORS: list[SensorDef] = [
    # PV inputs
    SensorDef("dc_voltage_1", "PV1 Voltage", "V", "voltage", "measurement", precision=1),
    SensorDef("dc_current_1", "PV1 Current", "A", "current", "measurement", precision=1),
    SensorDef("dc_voltage_2", "PV2 Voltage", "V", "voltage", "measurement", precision=1),
    SensorDef("dc_current_2", "PV2 Current", "A", "current", "measurement", precision=1),
    SensorDef("dc_voltage_3", "PV3 Voltage", "V", "voltage", "measurement", precision=1),
    SensorDef("dc_current_3", "PV3 Current", "A", "current", "measurement", precision=1),
    SensorDef("dc_voltage_4", "PV4 Voltage", "V", "voltage", "measurement", precision=1),
    SensorDef("dc_current_4", "PV4 Current", "A", "current", "measurement", precision=1),
    SensorDef("total_dc_power", "Total DC Power", "W", "power", "measurement"),
    # AC output
    SensorDef("ac_voltage_a", "AC Voltage Phase A", "V", "voltage", "measurement", precision=1),
    SensorDef("ac_voltage_b", "AC Voltage Phase B", "V", "voltage", "measurement", precision=1),
    SensorDef("ac_voltage_c", "AC Voltage Phase C", "V", "voltage", "measurement", precision=1),
    SensorDef("ac_current_a", "AC Current Phase A", "A", "current", "measurement", precision=1),
    SensorDef("ac_current_b", "AC Current Phase B", "A", "current", "measurement", precision=1),
    SensorDef("ac_current_c", "AC Current Phase C", "A", "current", "measurement", precision=1),
    SensorDef("active_power", "Active Power", "W", "power", "measurement"),
    SensorDef("reactive_power", "Reactive Power", "var", None, "measurement", icon="mdi:flash"),
    SensorDef("apparent_power", "Apparent Power", "VA", "apparent_power", "measurement"),
    SensorDef("grid_frequency", "Grid Frequency", "Hz", "frequency", "measurement", precision=2),
    SensorDef("inverter_temperature", "Inverter Temperature", "°C", "temperature", "measurement", precision=1),
    SensorDef("inverter_status", "Inverter Status", None, None, None, icon="mdi:information-outline"),
    # Battery
    SensorDef("battery_voltage", "Battery Voltage", "V", "voltage", "measurement", precision=1),
    SensorDef("battery_current", "Battery Current", "A", "current", "measurement", precision=1),
    SensorDef("battery_power", "Battery Power", "W", "power", "measurement"),
    SensorDef("battery_soc", "Battery SOC", "%", "battery", "measurement"),
    SensorDef("battery_soh", "Battery SOH", "%", None, "measurement", icon="mdi:battery-heart-variant"),
    # Grid / Meter
    SensorDef("meter_active_power", "Grid Power (Meter)", "W", "power", "measurement"),
    SensorDef("grid_port_power", "Grid Port Power", "W", "power", "measurement"),
    # Loads
    SensorDef("household_load_power", "Household Load Power", "W", "power", "measurement"),
    SensorDef("backup_load_power", "Backup Load Power", "W", "power", "measurement"),
    # Energy - generation
    SensorDef("total_energy", "Total Energy Generated", "kWh", "energy", "total_increasing"),
    SensorDef("today_energy", "Today Energy Generated", "kWh", "energy", "total_increasing", precision=1),
    SensorDef("yesterday_energy", "Yesterday Energy Generated", "kWh", "energy", None, precision=1),
    SensorDef("month_energy", "This Month Energy", "kWh", "energy", None),
    SensorDef("year_energy", "This Year Energy", "kWh", "energy", None),
    # Energy - battery
    SensorDef("battery_total_charge_energy", "Battery Total Charge Energy", "kWh", "energy", "total_increasing"),
    SensorDef("today_battery_charge_energy", "Today Battery Charge Energy", "kWh", "energy", "total_increasing", precision=1),
    SensorDef("battery_total_discharge_energy", "Battery Total Discharge Energy", "kWh", "energy", "total_increasing"),
    SensorDef("today_battery_discharge_energy", "Today Battery Discharge Energy", "kWh", "energy", "total_increasing", precision=1),
    # Energy - grid
    SensorDef("total_grid_import_energy", "Total Grid Import Energy", "kWh", "energy", "total_increasing"),
    SensorDef("today_grid_import_energy", "Today Grid Import Energy", "kWh", "energy", "total_increasing", precision=1),
    SensorDef("total_grid_export_energy", "Total Grid Export Energy", "kWh", "energy", "total_increasing"),
    SensorDef("today_grid_export_energy", "Today Grid Export Energy", "kWh", "energy", "total_increasing", precision=1),
    # Energy - load
    SensorDef("total_load_energy", "Total Load Energy", "kWh", "energy", "total_increasing"),
    SensorDef("today_load_energy", "Today Load Energy", "kWh", "energy", "total_increasing", precision=1),
    # Storage mode
    SensorDef("storage_control_mode", "Storage Control Mode", None, None, None, icon="mdi:battery-sync"),
]

INVERTER_STATUS_MAP = {
    0x0000: "Normal operation",
    0x0001: "Open operating",
    0x0002: "Waiting",
    0x0003: "Generating",
    0x0004: "Bypass inverting running",
    0x0005: "Standby synchro",
    0x0006: "Grid to load",
    0x000F: "Normal running",
    0x1004: "Grid off",
    0x1010: "Grid overvoltage",
    0x1011: "Grid undervoltage",
    0x1012: "Grid overfrequency",
    0x1013: "Grid underfrequency",
    0x1015: "No grid",
}

STORAGE_MODE_FLAGS = {
    0: "Self-consumption",
    1: "Time-charging",
    2: "Off-grid",
    3: "Battery wakeup",
    4: "Battery reserve",
    5: "Grid charge allowed",
}

STORAGE_MODE_REGISTER = 43110  # Holding register for storage control mode

@dataclass
class SwitchDef:
    key: str
    name: str
    bit: int
    icon: str | None = None

STORAGE_SWITCHES: list[SwitchDef] = [
    SwitchDef("storage_time_charging", "Time-Charging Mode", 1, icon="mdi:clock-outline"),
    SwitchDef("storage_off_grid", "Off-Grid Mode", 2, icon="mdi:transmission-tower-off"),
    SwitchDef("storage_battery_wakeup", "Battery Wakeup", 3, icon="mdi:battery-alert"),
    SwitchDef("storage_battery_reserve", "Battery Reserve Mode", 4, icon="mdi:battery-lock"),
    SwitchDef("storage_grid_charge", "Grid Charge Allowed", 5, icon="mdi:battery-charging"),
]


# --- Modbus reading ---

INTER_FRAME_DELAY = 0.35  # >300ms required by datalogger
SLOW_POLL_INTERVAL = 300  # seconds between slow sensor reads


async def _read_regs(client: AsyncModbusTcpClient, slave_id: int,
                     address: int, count: int) -> list[int]:
    result = await client.read_input_registers(address, count=count, device_id=slave_id)
    if result.isError():
        raise RuntimeError(f"Modbus error reading register {address}: {result}")
    if len(result.registers) < count:
        raise RuntimeError(
            f"Short read at register {address}: expected {count}, got {len(result.registers)}"
        )
    await asyncio.sleep(INTER_FRAME_DELAY)
    return result.registers


async def _read_holding(client: AsyncModbusTcpClient, slave_id: int,
                        address: int) -> int:
    result = await client.read_holding_registers(address, count=1, slave=slave_id)
    if result.isError():
        raise RuntimeError(f"Modbus error reading holding register {address}: {result}")
    await asyncio.sleep(INTER_FRAME_DELAY)
    return result.registers[0]


async def _write_holding(client: AsyncModbusTcpClient, slave_id: int,
                         address: int, value: int) -> None:
    result = await client.write_register(address, value, slave=slave_id)
    if result.isError():
        raise RuntimeError(f"Modbus error writing holding register {address}: {result}")
    await asyncio.sleep(INTER_FRAME_DELAY)


async def read_serial(client: AsyncModbusTcpClient, slave_id: int) -> str:
    """Read inverter serial number (once at startup)."""
    regs = await _read_regs(client, slave_id, 33000, 28)
    sn_chars = []
    for i in range(4, 20):
        val = _u16(regs, i)
        high = (val >> 8) & 0xFF
        low = val & 0xFF
        if high > 0:
            sn_chars.append(chr(high))
        if low > 0:
            sn_chars.append(chr(low))
    return "".join(sn_chars)


async def read_fast(client: AsyncModbusTcpClient, slave_id: int) -> dict:
    """Read real-time sensors (~1.4s per cycle, 4 reads)."""
    read = lambda addr, count: _read_regs(client, slave_id, addr, count)
    data = {}

    # DC inputs (33049-33058)
    regs = await read(33049, 10)
    for n in range(4):
        data[f"dc_voltage_{n+1}"] = round(_u16(regs, n * 2) * 0.1, 1)
        data[f"dc_current_{n+1}"] = round(_u16(regs, n * 2 + 1) * 0.1, 1)
    data["total_dc_power"] = _u32(regs, 8)

    # AC output & grid (33071-33095)
    regs = await read(33071, 25)
    data["ac_voltage_a"] = round(_u16(regs, 2) * 0.1, 1)
    data["ac_voltage_b"] = round(_u16(regs, 3) * 0.1, 1)
    data["ac_voltage_c"] = round(_u16(regs, 4) * 0.1, 1)
    data["ac_current_a"] = round(_u16(regs, 5) * 0.1, 1)
    data["ac_current_b"] = round(_u16(regs, 6) * 0.1, 1)
    data["ac_current_c"] = round(_u16(regs, 7) * 0.1, 1)
    data["active_power"] = _s32(regs, 8)
    data["reactive_power"] = _s32(regs, 10)
    data["apparent_power"] = _s32(regs, 12)
    data["inverter_temperature"] = round(_s16(regs, 22) * 0.1, 1)
    data["grid_frequency"] = round(_u16(regs, 23) * 0.01, 2)
    status_raw = _u16(regs, 24)
    data["inverter_status"] = INVERTER_STATUS_MAP.get(status_raw, f"Unknown (0x{status_raw:04X})")

    # Meter & battery (33126-33148) — includes storage mode at 33132
    regs = await read(33126, 23)
    data["meter_active_power"] = _s32(regs, 4)
    mode_raw = _u16(regs, 6)  # 33132
    active = [name for bit, name in STORAGE_MODE_FLAGS.items() if mode_raw & (1 << bit)]
    data["storage_control_mode"] = ", ".join(active) if active else "None"
    data["battery_voltage"] = round(_u16(regs, 7) * 0.1, 1)
    bat_current = _u16(regs, 8) * 0.1
    bat_discharging = _u16(regs, 9) == 1  # 33135: 0=charge, 1=discharge
    data["battery_current"] = round(-bat_current if bat_discharging else bat_current, 1)
    data["battery_soc"] = _u16(regs, 13)
    data["battery_soh"] = _u16(regs, 14)
    data["household_load_power"] = _u16(regs, 21)
    data["backup_load_power"] = _u16(regs, 22)

    # Battery & grid port power (33149-33157)
    regs = await read(33149, 9)
    bat_power = abs(_s32(regs, 0))
    data["battery_power"] = -bat_power if bat_discharging else bat_power
    data["grid_port_power"] = _s32(regs, 2)

    return data


async def read_slow(client: AsyncModbusTcpClient, slave_id: int) -> dict:
    """Read energy counters and slowly-changing sensors (~0.7s, 2 reads)."""
    read = lambda addr, count: _read_regs(client, slave_id, addr, count)
    data = {}

    # Energy generation (33029-33040)
    regs = await read(33029, 12)
    data["total_energy"] = _u32(regs, 0)
    data["month_energy"] = _u32(regs, 2)
    data["today_energy"] = round(_u16(regs, 6) * 0.1, 1)
    data["yesterday_energy"] = round(_u16(regs, 7) * 0.1, 1)
    data["year_energy"] = _u32(regs, 8)

    # Battery/grid/load energy (33161-33180)
    regs = await read(33161, 20)
    data["battery_total_charge_energy"] = _u32(regs, 0)
    data["today_battery_charge_energy"] = round(_u16(regs, 2) * 0.1, 1)
    data["battery_total_discharge_energy"] = _u32(regs, 4)
    data["today_battery_discharge_energy"] = round(_u16(regs, 6) * 0.1, 1)
    data["total_grid_import_energy"] = _u32(regs, 8)
    data["today_grid_import_energy"] = round(_u16(regs, 10) * 0.1, 1)
    data["total_grid_export_energy"] = _u32(regs, 12)
    data["today_grid_export_energy"] = round(_u16(regs, 14) * 0.1, 1)
    data["total_load_energy"] = _u32(regs, 16)
    data["today_load_energy"] = round(_u16(regs, 18) * 0.1, 1)

    return data


# --- MQTT publishing ---

async def publish_ha_discovery(mqtt: aiomqtt.Client, serial: str) -> None:
    """Publish Home Assistant MQTT auto-discovery config for all sensors."""
    device = {
        "identifiers": [f"solis_{serial}"],
        "name": f"Solis Inverter {serial}",
        "manufacturer": "Ginlong Solis",
        "model": "S6 Hybrid",
    }

    for sensor in SENSORS:
        topic = f"{HA_DISCOVERY_PREFIX}/sensor/solis_{serial}/{sensor.key}/config"
        payload = {
            "name": sensor.name,
            "unique_id": f"solis_{serial}_{sensor.key}",
            "state_topic": f"{MQTT_BASE_TOPIC}/{serial}/{sensor.key}",
            "device": device,
            "availability_topic": f"{MQTT_BASE_TOPIC}/{serial}/availability",
        }
        if sensor.unit:
            payload["unit_of_measurement"] = sensor.unit
        if sensor.device_class:
            payload["device_class"] = sensor.device_class
        if sensor.state_class:
            payload["state_class"] = sensor.state_class
        if sensor.icon:
            payload["icon"] = sensor.icon

        await mqtt.publish(topic, json.dumps(payload), retain=True)

    # Switches for storage mode bits
    for sw in STORAGE_SWITCHES:
        topic = f"{HA_DISCOVERY_PREFIX}/switch/solis_{serial}/{sw.key}/config"
        payload = {
            "name": sw.name,
            "unique_id": f"solis_{serial}_{sw.key}",
            "state_topic": f"{MQTT_BASE_TOPIC}/{serial}/{sw.key}/state",
            "command_topic": f"{MQTT_BASE_TOPIC}/{serial}/{sw.key}/set",
            "device": device,
            "availability_topic": f"{MQTT_BASE_TOPIC}/{serial}/availability",
            "payload_on": "ON",
            "payload_off": "OFF",
        }
        if sw.icon:
            payload["icon"] = sw.icon
        await mqtt.publish(topic, json.dumps(payload), retain=True)

    _LOGGER.info("Published HA discovery config for %d sensors + %d switches",
                 len(SENSORS), len(STORAGE_SWITCHES))


async def publish_state(mqtt: aiomqtt.Client, serial: str, data: dict) -> None:
    """Publish sensor values to MQTT."""
    for sensor in SENSORS:
        value = data.get(sensor.key)
        if value is not None:
            topic = f"{MQTT_BASE_TOPIC}/{serial}/{sensor.key}"
            await mqtt.publish(topic, str(value))

    await mqtt.publish(f"{MQTT_BASE_TOPIC}/{serial}/availability", "online", retain=True)


async def publish_switch_states(mqtt: aiomqtt.Client, serial: str,
                                mode_raw: int) -> None:
    """Publish ON/OFF state for each storage mode switch."""
    for sw in STORAGE_SWITCHES:
        state = "ON" if mode_raw & (1 << sw.bit) else "OFF"
        topic = f"{MQTT_BASE_TOPIC}/{serial}/{sw.key}/state"
        await mqtt.publish(topic, state, retain=True)


async def handle_switch_command(
    modbus: AsyncModbusTcpClient,
    slave_id: int,
    mqtt: aiomqtt.Client,
    serial: str,
    switch_key: str,
    payload: str,
) -> None:
    """Handle an ON/OFF command for a storage mode switch."""
    sw = next((s for s in STORAGE_SWITCHES if s.key == switch_key), None)
    if sw is None:
        return

    current = await _read_holding(modbus, slave_id, STORAGE_MODE_REGISTER)
    if payload == "ON":
        new_val = current | (1 << sw.bit)
    else:
        new_val = current & ~(1 << sw.bit)

    if new_val != current:
        await _write_holding(modbus, slave_id, STORAGE_MODE_REGISTER, new_val)
        _LOGGER.info("Storage mode: 0x%04X -> 0x%04X (%s = %s)", current, new_val, sw.name, payload)

    await publish_switch_states(mqtt, serial, new_val)


# --- Main loop ---

async def main(
    modbus_host: str,
    modbus_port: int,
    slave_id: int,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_user: str | None,
    mqtt_pass: str | None,
    interval: int,
):
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop_event.set)

    _LOGGER.info(
        "Starting solis2mqtt: Modbus %s:%d (slave %d) -> MQTT %s:%d (continuous polling)",
        modbus_host, modbus_port, slave_id, mqtt_host, mqtt_port,
    )

    modbus = AsyncModbusTcpClient(host=modbus_host, port=modbus_port, timeout=10)
    serial = None
    last_slow_read = 0.0
    slow_data: dict = {}

    async with aiomqtt.Client(
        hostname=mqtt_host,
        port=mqtt_port,
        username=mqtt_user,
        password=mqtt_pass,
    ) as mqtt:
        # Subscribe to switch command topics (wildcard)
        await mqtt.subscribe(f"{MQTT_BASE_TOPIC}/+/+/set")
        _LOGGER.info("Subscribed to %s/+/+/set for switch commands", MQTT_BASE_TOPIC)

        async def poll_loop():
            nonlocal serial, last_slow_read, slow_data
            while not stop_event.is_set():
                try:
                    if not modbus.connected:
                        await modbus.connect()
                        if not modbus.connected:
                            _LOGGER.error("Cannot connect to inverter, retrying in %ds…", interval)
                            await asyncio.sleep(interval)
                            continue

                    # Read serial once at startup
                    if serial is None:
                        serial = await read_serial(modbus, slave_id)
                        _LOGGER.info("Inverter serial: %s", serial)
                        await publish_ha_discovery(mqtt, serial)

                    # Fast sensors every cycle
                    data = await read_fast(modbus, slave_id)

                    # Read storage mode from holding register and publish switch states
                    storage_mode = await _read_holding(modbus, slave_id, STORAGE_MODE_REGISTER)
                    await publish_switch_states(mqtt, serial, storage_mode)

                    # Slow sensors every SLOW_POLL_INTERVAL seconds
                    now = asyncio.get_event_loop().time()
                    if now - last_slow_read >= SLOW_POLL_INTERVAL:
                        slow_data = await read_slow(modbus, slave_id)
                        last_slow_read = now
                        _LOGGER.debug("Updated slow sensors")

                    data.update(slow_data)
                    await publish_state(mqtt, serial, data)
                    _LOGGER.debug("Published %d sensor values", len(data))

                except Exception:
                    _LOGGER.exception("Error in poll loop")
                    if modbus.connected:
                        modbus.close()
                    await asyncio.sleep(interval)
                    continue

                if stop_event.is_set():
                    break

        async def command_loop():
            async for message in mqtt.messages:
                if stop_event.is_set():
                    break
                topic = message.topic.value
                payload = message.payload.decode()
                # Expected: solis/<serial>/<switch_key>/set
                parts = topic.split("/")
                if len(parts) == 4 and parts[3] == "set" and payload in ("ON", "OFF"):
                    switch_key = parts[2]
                    if serial and modbus.connected:
                        try:
                            await handle_switch_command(
                                modbus, slave_id, mqtt, serial, switch_key, payload,
                            )
                        except Exception:
                            _LOGGER.exception("Error handling command %s=%s", switch_key, payload)

        poll_task = asyncio.create_task(poll_loop())
        command_task = asyncio.create_task(command_loop())

        # Wait for either task to finish (poll_loop exits on stop_event)
        done, pending = await asyncio.wait(
            [poll_task, command_task],
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()

        # Publish offline on clean shutdown
        if serial:
            await mqtt.publish(f"{MQTT_BASE_TOPIC}/{serial}/availability", "offline", retain=True)

    modbus.close()
    _LOGGER.info("Stopped.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Solis S6 Modbus TCP to MQTT bridge")
    parser.add_argument("--modbus-host", required=True, help="Inverter/datalogger IP")
    parser.add_argument("--modbus-port", type=int, default=502)
    parser.add_argument("--slave-id", type=int, default=1)
    parser.add_argument("--mqtt-host", default=os.environ.get("MQTT_HOST", "localhost"))
    parser.add_argument("--mqtt-port", type=int, default=int(os.environ.get("MQTT_PORT", "1883")))
    parser.add_argument("--mqtt-user", default=os.environ.get("MQTT_USER"))
    parser.add_argument("--mqtt-pass", default=os.environ.get("MQTT_PASS"))
    parser.add_argument("--interval", type=int, default=10, help="Retry delay in seconds after errors")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    asyncio.run(main(
        modbus_host=args.modbus_host,
        modbus_port=args.modbus_port,
        slave_id=args.slave_id,
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_user=args.mqtt_user,
        mqtt_pass=args.mqtt_pass,
        interval=args.interval,
    ))
