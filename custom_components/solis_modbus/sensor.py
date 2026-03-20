"""Sensor platform for Solis Modbus integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfFrequency,
    UnitOfPower,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import SolisModbusConfigEntry
from .coordinator import SolisModbusCoordinator

INVERTER_STATUS_MAP = {
    0x0000: "Normal operation",
    0x0001: "Open operating",
    0x0002: "Waiting",
    0x0003: "Initializing",
    0x0004: "Bypass inverting running",
    0x0005: "Bypass inverting synchronize",
    0x0006: "Bypass grid running",
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


@dataclass(frozen=True, kw_only=True)
class SolisSensorEntityDescription(SensorEntityDescription):
    """Describe a Solis sensor."""

    data_key: str
    precision: int | None = None


SENSOR_DESCRIPTIONS: tuple[SolisSensorEntityDescription, ...] = (
    # PV / DC inputs
    SolisSensorEntityDescription(
        key="dc_voltage_1",
        data_key="dc_voltage_1",
        translation_key="dc_voltage_1",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="dc_current_1",
        data_key="dc_current_1",
        translation_key="dc_current_1",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="dc_voltage_2",
        data_key="dc_voltage_2",
        translation_key="dc_voltage_2",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="dc_current_2",
        data_key="dc_current_2",
        translation_key="dc_current_2",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="dc_voltage_3",
        data_key="dc_voltage_3",
        translation_key="dc_voltage_3",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="dc_current_3",
        data_key="dc_current_3",
        translation_key="dc_current_3",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="dc_voltage_4",
        data_key="dc_voltage_4",
        translation_key="dc_voltage_4",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="dc_current_4",
        data_key="dc_current_4",
        translation_key="dc_current_4",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="total_dc_power",
        data_key="total_dc_power",
        translation_key="total_dc_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # AC output
    SolisSensorEntityDescription(
        key="ac_voltage_a",
        data_key="ac_voltage_a",
        translation_key="ac_voltage_a",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="ac_voltage_b",
        data_key="ac_voltage_b",
        translation_key="ac_voltage_b",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="ac_voltage_c",
        data_key="ac_voltage_c",
        translation_key="ac_voltage_c",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="ac_current_a",
        data_key="ac_current_a",
        translation_key="ac_current_a",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="ac_current_b",
        data_key="ac_current_b",
        translation_key="ac_current_b",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="ac_current_c",
        data_key="ac_current_c",
        translation_key="ac_current_c",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="active_power",
        data_key="active_power",
        translation_key="active_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolisSensorEntityDescription(
        key="reactive_power",
        data_key="reactive_power",
        translation_key="reactive_power",
        native_unit_of_measurement="var",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolisSensorEntityDescription(
        key="apparent_power",
        data_key="apparent_power",
        translation_key="apparent_power",
        native_unit_of_measurement=UnitOfPower.VOLT_AMPERE,
        device_class=SensorDeviceClass.APPARENT_POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolisSensorEntityDescription(
        key="grid_frequency",
        data_key="grid_frequency",
        translation_key="grid_frequency",
        native_unit_of_measurement=UnitOfFrequency.HERTZ,
        device_class=SensorDeviceClass.FREQUENCY,
        state_class=SensorStateClass.MEASUREMENT,
        precision=2,
    ),
    SolisSensorEntityDescription(
        key="inverter_temperature",
        data_key="inverter_temperature",
        translation_key="inverter_temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    # Inverter status
    SolisSensorEntityDescription(
        key="inverter_status",
        data_key="inverter_status",
        translation_key="inverter_status",
    ),
    # Battery
    SolisSensorEntityDescription(
        key="battery_voltage",
        data_key="battery_voltage",
        translation_key="battery_voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="battery_current",
        data_key="battery_current",
        translation_key="battery_current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="battery_power",
        data_key="battery_power",
        translation_key="battery_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolisSensorEntityDescription(
        key="battery_soc",
        data_key="battery_soc",
        translation_key="battery_soc",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolisSensorEntityDescription(
        key="battery_soh",
        data_key="battery_soh",
        translation_key="battery_soh",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Grid / Meter
    SolisSensorEntityDescription(
        key="meter_active_power",
        data_key="meter_active_power",
        translation_key="meter_active_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolisSensorEntityDescription(
        key="grid_port_power",
        data_key="grid_port_power",
        translation_key="grid_port_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Loads
    SolisSensorEntityDescription(
        key="household_load_power",
        data_key="household_load_power",
        translation_key="household_load_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    SolisSensorEntityDescription(
        key="backup_load_power",
        data_key="backup_load_power",
        translation_key="backup_load_power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Energy totals
    SolisSensorEntityDescription(
        key="total_energy",
        data_key="total_energy",
        translation_key="total_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SolisSensorEntityDescription(
        key="today_energy",
        data_key="today_energy",
        translation_key="today_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="yesterday_energy",
        data_key="yesterday_energy",
        translation_key="yesterday_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="month_energy",
        data_key="month_energy",
        translation_key="month_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
    ),
    SolisSensorEntityDescription(
        key="year_energy",
        data_key="year_energy",
        translation_key="year_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
    ),
    # Battery energy
    SolisSensorEntityDescription(
        key="battery_total_charge_energy",
        data_key="battery_total_charge_energy",
        translation_key="battery_total_charge_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SolisSensorEntityDescription(
        key="today_battery_charge_energy",
        data_key="today_battery_charge_energy",
        translation_key="today_battery_charge_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="battery_total_discharge_energy",
        data_key="battery_total_discharge_energy",
        translation_key="battery_total_discharge_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SolisSensorEntityDescription(
        key="today_battery_discharge_energy",
        data_key="today_battery_discharge_energy",
        translation_key="today_battery_discharge_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        precision=1,
    ),
    # Grid import/export energy
    SolisSensorEntityDescription(
        key="total_grid_import_energy",
        data_key="total_grid_import_energy",
        translation_key="total_grid_import_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SolisSensorEntityDescription(
        key="today_grid_import_energy",
        data_key="today_grid_import_energy",
        translation_key="today_grid_import_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        precision=1,
    ),
    SolisSensorEntityDescription(
        key="total_grid_export_energy",
        data_key="total_grid_export_energy",
        translation_key="total_grid_export_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SolisSensorEntityDescription(
        key="today_grid_export_energy",
        data_key="today_grid_export_energy",
        translation_key="today_grid_export_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        precision=1,
    ),
    # Load energy
    SolisSensorEntityDescription(
        key="total_load_energy",
        data_key="total_load_energy",
        translation_key="total_load_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    SolisSensorEntityDescription(
        key="today_load_energy",
        data_key="today_load_energy",
        translation_key="today_load_energy",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        precision=1,
    ),
    # Storage mode
    SolisSensorEntityDescription(
        key="storage_control_mode",
        data_key="storage_control_mode",
        translation_key="storage_control_mode",
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SolisModbusConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Solis sensors from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        SolisSensor(coordinator, description, entry.entry_id)
        for description in SENSOR_DESCRIPTIONS
    )


class SolisSensor(CoordinatorEntity[SolisModbusCoordinator], SensorEntity):
    """Representation of a Solis inverter sensor."""

    entity_description: SolisSensorEntityDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: SolisModbusCoordinator,
        description: SolisSensorEntityDescription,
        entry_id: str,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        serial = coordinator.data.get("serial_number", "solis")
        self._attr_unique_id = f"{serial}_{description.key}"
        self._attr_device_info = {
            "identifiers": {("solis_modbus", serial)},
            "name": f"Solis Inverter {serial}",
            "manufacturer": "Ginlong Solis",
            "model": "S6 Hybrid",
        }

    @property
    def native_value(self):
        """Return the sensor value."""
        if self.coordinator.data is None:
            return None

        value = self.coordinator.data.get(self.entity_description.data_key)
        if value is None:
            return None

        # Special formatting for status sensors
        if self.entity_description.key == "inverter_status":
            return INVERTER_STATUS_MAP.get(value, f"Unknown (0x{value:04X})")

        if self.entity_description.key == "storage_control_mode":
            active = []
            for bit, name in STORAGE_MODE_FLAGS.items():
                if value & (1 << bit):
                    active.append(name)
            return ", ".join(active) if active else "None"

        if self.entity_description.precision is not None:
            return round(value, self.entity_description.precision)

        return value
