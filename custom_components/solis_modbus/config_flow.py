"""Config flow for Solis Modbus integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from pymodbus.client import AsyncModbusTcpClient
from pymodbus.exceptions import ModbusException

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import (
    CONF_HOST,
    CONF_PORT,
    CONF_SCAN_INTERVAL,
    CONF_SLAVE_ID,
    DEFAULT_PORT,
    DEFAULT_SCAN_INTERVAL,
    DEFAULT_SLAVE_ID,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Optional(CONF_PORT, default=DEFAULT_PORT): int,
        vol.Optional(CONF_SLAVE_ID, default=DEFAULT_SLAVE_ID): vol.All(
            int, vol.Range(min=1, max=247)
        ),
        vol.Optional(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): vol.All(
            int, vol.Range(min=10, max=300)
        ),
    }
)


class SolisModbusConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Solis Modbus."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]
            slave_id = user_input[CONF_SLAVE_ID]

            # Test connection
            try:
                client = AsyncModbusTcpClient(host=host, port=port, timeout=5)
                await client.connect()
                if not client.connected:
                    errors["base"] = "cannot_connect"
                else:
                    # Try reading the model register to verify it's a Solis inverter
                    result = await client.read_input_registers(
                        address=33000, count=1, slave=slave_id
                    )
                    client.close()
                    if result.isError():
                        errors["base"] = "cannot_connect"
                    else:
                        await self.async_set_unique_id(f"solis_{host}_{slave_id}")
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Solis Inverter ({host})",
                            data=user_input,
                        )
            except (ModbusException, OSError) as err:
                _LOGGER.error("Connection test failed: %s", err)
                errors["base"] = "cannot_connect"

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )
