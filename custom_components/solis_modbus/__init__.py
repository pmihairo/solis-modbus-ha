"""The Solis Modbus integration."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, CONF_SLAVE_ID, DEFAULT_PORT, DEFAULT_SCAN_INTERVAL, DEFAULT_SLAVE_ID
from .coordinator import SolisModbusCoordinator

PLATFORMS = ["sensor"]

type SolisModbusConfigEntry = ConfigEntry[SolisModbusCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: SolisModbusConfigEntry) -> bool:
    """Set up Solis Modbus from a config entry."""
    config = {
        CONF_HOST: entry.data[CONF_HOST],
        CONF_PORT: entry.data.get(CONF_PORT, DEFAULT_PORT),
        CONF_SLAVE_ID: entry.data.get(CONF_SLAVE_ID, DEFAULT_SLAVE_ID),
        CONF_SCAN_INTERVAL: entry.data.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL),
    }

    coordinator = SolisModbusCoordinator(hass, config)
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SolisModbusConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_shutdown()
    return unload_ok
