"""Support for Dreo HAP toggles as switch entities (LED, light sensor, mute)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DreoConfigEntry
from .const import DreoEntityConfigSpec, DreoErrorCode
from .coordinator import DreoDataUpdateCoordinator
from .entity import DreoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Dreo switches from a config entry."""

    @callback
    def async_add_switch_entities() -> None:
        entities: list[DreoToggleSwitch] = []

        for device in config_entry.runtime_data.devices:
            device_id = device.get("deviceSn")
            if not device_id:
                continue

            device_config = device.get(DreoEntityConfigSpec.TOP_CONFIG, {})
            if Platform.SWITCH not in device_config.get("entitySupports", []):
                _LOGGER.warning(
                    "No switch entity support for model %s", device.get("model")
                )
                continue

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                continue

            toggle_switches = device_config.get(
                DreoEntityConfigSpec.TOGGLE_ENTITY_CONF, {}
            )
            if not toggle_switches:
                _LOGGER.warning("No switches found for model %s", device.get("model"))
                continue

            # Create switches dynamically based on device_config['switches'] mapping
            error_map = {
                "led_switch": DreoErrorCode.SET_LED_SWITCH_FAILED,
                "lightsensor_switch": DreoErrorCode.SET_LIGHTSENSOR_SWITCH_FAILED,
                "mute_switch": DreoErrorCode.SET_MUTE_SWITCH_FAILED,
            }

            for toggle_switch in toggle_switches.values():
                field = toggle_switch.get("field")

                if not field:
                    _LOGGER.warning(
                        "Skipping toggle switch with missing field in model %s",
                        device.get("model"),
                    )
                    continue
                data = DreoToggleSwitchData(
                    field=field,
                    name=toggle_switch.get("labelName") or field,
                    operable_when_off=toggle_switch.get("operableWhenOff", False),
                    error_key=error_map.get(field)
                    or DreoErrorCode.SET_LED_SWITCH_FAILED,
                )

                entities.append(DreoToggleSwitch(device, coordinator, data))

        if entities:
            async_add_entities(entities)

    async_add_switch_entities()


class DreoToggleSwitchData:
    """Base data for all Dreo toggle switches."""

    field: str
    name: str | None
    operable_when_off: bool
    error_key: str

    def __init__(
        self, field: str, name: str | None, operable_when_off: bool, error_key: str
    ) -> None:
        """Initialize toggle switch data container."""
        self.field = field
        self.name = name
        self.operable_when_off = operable_when_off
        self.error_key = error_key


class DreoToggleSwitch(DreoEntity, SwitchEntity):
    """Generic toggle switch for Dreo HAP device properties."""

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
        data: DreoToggleSwitchData,
    ) -> None:
        """Initialize the toggle switch entity for a given HAP device field."""

        super().__init__(device, coordinator, "switch", data.name)
        self._field = data.field
        self._error_key = data.error_key
        self._operable_when_off = data.operable_when_off
        self._attr_unique_id = f"{device.get('deviceSn')}_{self._field}"

    def _is_ui_available(self) -> bool:
        """Return if UI should allow interaction for this switch."""

        base_available = super().available
        data = getattr(self.coordinator, "data", None)
        if not data:
            return base_available
        device_available = bool(getattr(data, "available", False))
        if not device_available:
            return False

        if self._operable_when_off:
            return base_available and device_available
        device_on = bool(getattr(data, "is_on", True))
        return base_available and device_on

    @property
    def available(self) -> bool:
        """Return if the entity is available (online and power policy)."""
        return self._is_ui_available()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updates from the coordinator to refresh on/off state."""

        state = bool(getattr(self.coordinator.data, self._field, True))
        self._attr_is_on = bool(state) if state is not None else False
        super()._handle_coordinator_update()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""

        if not self._is_ui_available():
            _LOGGER.debug(
                "Ignoring turn_on for %s because device is unavailable or power policy blocks it",
                self.entity_id,
            )
            return
        await self.async_send_command_and_update(self._error_key, **{self._field: True})

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""

        if not self._is_ui_available():
            _LOGGER.debug(
                "Ignoring turn_off for %s because device is unavailable or power policy blocks it",
                self.entity_id,
            )
            return
        await self.async_send_command_and_update(
            self._error_key, **{self._field: False}
        )

    @property
    def icon(self) -> str | None:
        """Return a more distinctive icon per switch and state."""

        is_on = getattr(self, "_attr_is_on", False)
        if self._field == "led_switch":
            return "mdi:led-on" if is_on else "mdi:led-off"
        if self._field == "lightsensor_switch":
            return "mdi:brightness-auto" if is_on else "mdi:brightness-5"
        if self._field == "mute_switch":
            return "mdi:volume-high" if is_on else "mdi:volume-mute"
        if self._field == "childlock_switch":
            return "mdi:lock" if is_on else "mdi:lock-open-variant"
        if self._field == "fanOnTempMet_switch":
            return "mdi:weather-windy" if is_on else "mdi:air-filter"
        return None
