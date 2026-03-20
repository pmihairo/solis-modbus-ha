"""Helpers for pymodbus compatibility across versions."""

from __future__ import annotations

import inspect
import logging

from pymodbus.client import AsyncModbusTcpClient

_LOGGER = logging.getLogger(__name__)

# Detect the right way to pass slave/unit ID to pymodbus read calls.
# Different pymodbus versions use different signatures:
#   - 2.x: read_input_registers(address, count=1, unit=0)
#   - 3.0-3.5: read_input_registers(address, count=1, slave=0)
#   - 3.6+: read_input_registers(address, *, count=1, slave=1)
#   - Some HA-bundled versions: read_input_registers(address, count=1) with no slave arg
_SLAVE_KWARG: str | None = None


def _detect_slave_kwarg() -> str | None:
    """Detect which keyword argument to use for slave ID."""
    global _SLAVE_KWARG
    if _SLAVE_KWARG is not None:
        return _SLAVE_KWARG if _SLAVE_KWARG != "" else None

    try:
        sig = inspect.signature(AsyncModbusTcpClient.read_input_registers)
        params = list(sig.parameters.keys())
        _LOGGER.debug("pymodbus read_input_registers params: %s", params)

        if "slave" in params:
            _SLAVE_KWARG = "slave"
        elif "unit" in params:
            _SLAVE_KWARG = "unit"
        else:
            # No slave/unit param — check if **kwargs is accepted
            for p in sig.parameters.values():
                if p.kind == inspect.Parameter.VAR_KEYWORD:
                    # Has **kwargs, try 'slave' first (newer convention)
                    _SLAVE_KWARG = "slave"
                    return _SLAVE_KWARG
            _SLAVE_KWARG = ""  # No way to pass slave ID
    except (ValueError, TypeError):
        _SLAVE_KWARG = ""

    return _SLAVE_KWARG if _SLAVE_KWARG != "" else None


async def read_input_registers(
    client: AsyncModbusTcpClient,
    address: int,
    count: int,
    slave_id: int,
):
    """Read input registers with pymodbus version compatibility."""
    kwarg = _detect_slave_kwarg()
    kwargs = {"count": count}
    if kwarg:
        kwargs[kwarg] = slave_id

    try:
        return await client.read_input_registers(address, **kwargs)
    except TypeError:
        # count might also not be a valid kwarg in some versions
        _LOGGER.debug("Retrying read_input_registers with positional count")
        try:
            if kwarg:
                return await client.read_input_registers(
                    address, count, **{kwarg: slave_id}
                )
            else:
                return await client.read_input_registers(address, count)
        except TypeError:
            # Last resort: just address and count, no slave
            return await client.read_input_registers(address, count)
