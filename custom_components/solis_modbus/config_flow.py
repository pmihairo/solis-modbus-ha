"""Config flow for Solis Modbus integration."""

from __future__ import annotations

import logging

import voluptuous as vol
from pymodbus.client import AsyncModbusTcpClient

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .modbus_helpers import read_input_registers
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
            client = None
            try:
                client = AsyncModbusTcpClient(host=host, port=port, timeout=5)
                await client.connect()
                if not client.connected:
                    errors["base"] = "cannot_connect"
                else:
                    result = await read_input_registers(
                        client, 33000, 1, slave_id
                    )
                    if result.isError():
                        _LOGGER.error(
                            "Modbus read test failed at register 33000: %s", result
                        )
                        errors["base"] = "cannot_connect"
                    else:
                        await self.async_set_unique_id(f"solis_{host}_{slave_id}")
                        self._abort_if_unique_id_configured()
                        return self.async_create_entry(
                            title=f"Solis Inverter ({host})",
                            data=user_input,
                        )
            except Exception as err:
                _LOGGER.error(
                    "Connection test failed (%s): %s", type(err).__name__, err
                )
                errors["base"] = "cannot_connect"
            finally:
                if client:
                    client.close()

        return self.async_show_form(
            step_id="user",
            data_schema=DATA_SCHEMA,
            errors=errors,
        )
