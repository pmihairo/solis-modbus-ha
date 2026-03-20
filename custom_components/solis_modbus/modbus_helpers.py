"""Helpers for pymodbus compatibility across versions."""

from __future__ import annotations

import inspect
import logging

from pymodbus.client import AsyncModbusTcpClient

_LOGGER = logging.getLogger(__name__)

# Detect the right keyword for the slave/unit/device ID parameter.
# pymodbus has renamed this across versions:
#   - 2.x:    unit=
#   - 3.0-3.5: slave=
#   - 3.11+:  device_id=
_DEVICE_ID_KWARG: str | None = None


def _detect_device_id_kwarg() -> str | None:
    """Detect which keyword argument to use for the device ID."""
    global _DEVICE_ID_KWARG
    if _DEVICE_ID_KWARG is not None:
        return _DEVICE_ID_KWARG if _DEVICE_ID_KWARG != "" else None

    try:
        sig = inspect.signature(AsyncModbusTcpClient.read_input_registers)
        params = list(sig.parameters.keys())
        _LOGGER.debug("pymodbus read_input_registers params: %s", params)

        for candidate in ("device_id", "slave", "unit"):
            if candidate in params:
                _DEVICE_ID_KWARG = candidate
                _LOGGER.debug("Using '%s' for device ID parameter", candidate)
                return _DEVICE_ID_KWARG

        _DEVICE_ID_KWARG = ""
    except (ValueError, TypeError):
        _DEVICE_ID_KWARG = ""

    return None


async def read_input_registers(
    client: AsyncModbusTcpClient,
    address: int,
    count: int,
    device_id: int,
):
    """Read input registers with pymodbus version compatibility."""
    kwarg = _detect_device_id_kwarg()
    kwargs = {"count": count}
    if kwarg:
        kwargs[kwarg] = device_id
    return await client.read_input_registers(address, **kwargs)
