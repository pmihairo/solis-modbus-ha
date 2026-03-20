# Solis S6 Modbus TCP to MQTT Bridge

A standalone bridge that reads data from a Solis S6 hybrid inverter via Modbus TCP (through the datalogger) and publishes it to MQTT with Home Assistant auto-discovery.

## Sensors

46 sensors covering:

| Category | Sensors |
|----------|---------|
| **PV/DC** | PV1-PV4 voltage & current, total DC power |
| **AC Output** | Phase A/B/C voltage & current, active/reactive/apparent power |
| **Grid** | Grid frequency, meter active power, grid port power |
| **Battery** | Voltage, current, power, SOC, SOH |
| **Loads** | Household load power, backup load power |
| **Energy** | Today/total for: generation, battery charge/discharge, grid import/export, load consumption |
| **Status** | Inverter status, storage control mode |

All sensors are auto-discovered by Home Assistant via MQTT — no custom integration or HACS required.

## Requirements

- Solis S6 hybrid inverter with a datalogger connected to your network
- Modbus TCP enabled on the datalogger (port 502)
- An MQTT broker (e.g. Mosquitto)
- Home Assistant with MQTT integration configured

## Quick Start

### Docker (recommended)

```bash
docker build -t solis2mqtt .
docker run -d --network host --name solis2mqtt solis2mqtt \
  --modbus-host <INVERTER_IP> \
  --mqtt-host <MQTT_BROKER_IP> \
  --mqtt-user <user> \
  --mqtt-pass <pass>
```

### Python

```bash
pip install -r requirements.txt
python solis2mqtt.py \
  --modbus-host <INVERTER_IP> \
  --mqtt-host <MQTT_BROKER_IP> \
  --mqtt-user <user> \
  --mqtt-pass <pass>
```

## Options

| Argument | Default | Description |
|----------|---------|-------------|
| `--modbus-host` | *(required)* | Inverter/datalogger IP address |
| `--modbus-port` | `502` | Modbus TCP port |
| `--slave-id` | `1` | Modbus slave ID |
| `--mqtt-host` | `localhost` | MQTT broker host (or `MQTT_HOST` env var) |
| `--mqtt-port` | `1883` | MQTT broker port (or `MQTT_PORT` env var) |
| `--mqtt-user` | | MQTT username (or `MQTT_USER` env var) |
| `--mqtt-pass` | | MQTT password (or `MQTT_PASS` env var) |
| `--interval` | `30` | Poll interval in seconds |
| `--debug` | | Enable debug logging |

## Testing Without MQTT

Use the included test script to verify Modbus connectivity:

```bash
pip install pymodbus
python test_connection.py <INVERTER_IP>
```

## MQTT Topics

```
solis/<serial>/availability       # online/offline
solis/<serial>/battery_soc        # individual sensor values
solis/<serial>/active_power
...
homeassistant/sensor/solis_<serial>/*/config  # HA auto-discovery
```

## Register Reference

Based on the Solis RS485 MODBUS hybrid inverter protocol (function code 0x04):

- `33000-33019` — Model, versions, serial number
- `33029-33040` — Energy generation totals
- `33049-33058` — DC inputs (PV1-PV4), total DC power
- `33071-33095` — AC output, grid frequency, temperature, status
- `33126-33148` — Meter data, battery, load power
- `33149-33157` — Battery power, grid port power
- `33161-33180` — Battery/grid/load energy totals
- `33132` — Storage control mode
