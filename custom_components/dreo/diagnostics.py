"""Diagnostics support for Dreo."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from . import DreoConfigEntry

TO_REDACT_CONFIG = {CONF_USERNAME, CONF_PASSWORD}
TO_REDACT_DEVICE = {"deviceSn", "wifi_ssid", "wifi_bssid"}


async def async_get_config_entry_diagnostics(
    hass: Any,
    entry: DreoConfigEntry,
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    data = entry.runtime_data

    device_diags = []
    for device in data.devices:
        redacted = async_redact_data(device, TO_REDACT_DEVICE)
        device_sn = device.get("deviceSn", "")
        coordinator = data.coordinators.get(device_sn)
        redacted["coordinator_has_data"] = (
            coordinator is not None and coordinator.data is not None
        )
        device_diags.append(redacted)

    return {
        "config_entry_data": async_redact_data(dict(entry.data), TO_REDACT_CONFIG),
        "websocket_connected": (
            data.websocket.connected if data.websocket is not None else False
        ),
        "devices": device_diags,
    }
