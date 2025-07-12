"""Support for Dreo select entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DreoConfigEntry
from .const import (
    CIR_FAN_DEVICE_TYPE,
    CIR_FAN_SWING_ENTITY,
    ERROR_SET_RGB_SPEED_FAILED,
    ERROR_SET_SWING_FAILED,
)
from .coordinator import DreoCirculationFanDeviceData, DreoDataUpdateCoordinator
from .entity import DreoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Dreo select entities from a config entry."""

    @callback
    def async_add_select_entities() -> None:
        """Add select entities."""
        new_selects: list[DreoOscillationSelect | DreoRgbSpeedSelect] = []

        for device in config_entry.runtime_data.devices:
            device_type = device.get("deviceType")
            if device_type != CIR_FAN_DEVICE_TYPE:
                continue

            device_id = device.get("deviceSn")
            if not device_id:
                continue

            if Platform.SELECT not in device.get("config", {}).get(
                "entitySupports", []
            ):
                _LOGGER.warning(
                    "No select entity support for model %s", device.get("model")
                )
                continue

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for device %s", device_id)
                continue

            config = coordinator.model_config
            select_options = config.get("selectOptions", [])
            if len(select_options) > 1:
                select_entity = DreoOscillationSelect(device, coordinator)
                new_selects.append(select_entity)

            # Add RGB light speed select for circulation fans
            light_modes = config.get("light_modes", [])
            if (
                light_modes
                and any(mode in ["Cycle", "Fade"] for mode in light_modes)
                and Platform.SELECT
                in device.get("config", {}).get("entitySupports", [])
            ):
                speed_select_entity = DreoRgbSpeedSelect(device, coordinator)
                new_selects.append(speed_select_entity)

        if new_selects:
            async_add_entities(new_selects)

    async_add_select_entities()


class DreoOscillationSelect(DreoEntity, SelectEntity):
    """Dreo circulation fan oscillation direction select."""

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the oscillation select."""
        super().__init__(device, coordinator, CIR_FAN_DEVICE_TYPE, CIR_FAN_SWING_ENTITY)

        select_options = coordinator.model_config.get("selectOptions", [])

        self._select_options = select_options
        self._attr_options = []

        direction_labels = coordinator.model_config.get("selectOptionLabel", {})

        for direction in select_options:
            label = direction_labels.get(direction, direction)
            self._attr_options.append(label)

        self._attr_name = CIR_FAN_SWING_ENTITY
        self._attr_icon = "mdi:fan-chevron-up"

        self._attr_current_option = (
            self._attr_options[0] if self._attr_options else None
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            return

        device_state_data = self.coordinator.data
        self._attr_available = device_state_data.available

        if (
            hasattr(device_state_data, "swing_direction")
            and device_state_data.swing_direction is not None
        ):
            current_mode = device_state_data.swing_direction

            if current_mode in self._select_options:
                index = self._select_options.index(current_mode)
                self._attr_current_option = self._attr_options[index]
            else:
                _LOGGER.warning(
                    "DreoOscillationSelect: swing_direction '%s' not found in select_options",
                    current_mode,
                )
                self._attr_current_option = (
                    self._attr_options[0] if self._attr_options else None
                )
        else:
            self._attr_current_option = (
                self._attr_options[0] if self._attr_options else None
            )

        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if option not in self._attr_options:
            _LOGGER.error(
                "Invalid oscillation option: %s, available options: %s",
                option,
                self._attr_options,
            )
            return

        command_params: dict[str, Any] = {}

        if not self.coordinator.data or not self.coordinator.data.is_on:
            command_params["power_switch"] = True

        option_index = self._attr_options.index(option)
        select_option = self._select_options[option_index]

        direction_modes = self.coordinator.model_config.get("selectOptions", [])

        if select_option in direction_modes:
            command_params["oscmode"] = select_option
        else:
            _LOGGER.warning(
                "DreoOscillationSelect: select_option '%s' not found in direction_modes",
                select_option,
            )

        await self.async_send_command_and_update(
            ERROR_SET_SWING_FAILED, **command_params
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.available
        )

    def _update_attributes(self) -> None:
        """Update attributes from coordinator data."""
        if not self.coordinator.data:
            return

        circulation_fan_data = self.coordinator.data
        self._attr_available = circulation_fan_data.available

        if circulation_fan_data.is_on:
            swing_direction = getattr(circulation_fan_data, "swing_direction", None)
            if swing_direction and swing_direction in self._select_options:
                # Map swing_direction to the corresponding display label
                index = self._select_options.index(swing_direction)
                self._attr_current_option = self._attr_options[index]
            else:
                self._attr_current_option = (
                    self._attr_options[0] if self._attr_options else "Fixed"
                )
        else:
            self._attr_current_option = None


class DreoRgbSpeedSelect(DreoEntity, SelectEntity):
    """Dreo circulation fan RGB light speed select."""

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the RGB speed select."""
        super().__init__(device, coordinator, "select", "RGB Light Speed")

        device_id = device.get("deviceSn")
        self._attr_unique_id = f"{device_id}_rgb_speed"
        self._attr_name = "RGB Light Speed"
        self._attr_icon = "mdi:speedometer"

        # Speed options
        self._attr_options = ["Slow", "Medium", "Fast"]
        self._speed_mapping = {
            "Slow": 1,
            "Medium": 2,
            "Fast": 3,
        }
        self._reverse_speed_mapping = {1: "Slow", 2: "Medium", 3: "Fast"}

        # Get speed range from config
        speed_range = coordinator.model_config.get("light_speed_range", [1, 3])
        self._speed_range = tuple(speed_range)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            return

        device_state_data = self.coordinator.data
        self._attr_available = device_state_data.available

        # Only show as available if RGB light is on and in Cycle/Fade mode
        if (
            isinstance(device_state_data, DreoCirculationFanDeviceData)
            and device_state_data.rgb_state
            and device_state_data.rgb_mode in ["Cycle", "Fade"]
        ):
            self._attr_available = True

            # Update current speed
            if device_state_data.rgb_speed is not None:
                current_speed = device_state_data.rgb_speed
                self._attr_current_option = self._reverse_speed_mapping.get(
                    current_speed, "Medium"
                )
            else:
                self._attr_current_option = "Medium"
        else:
            # Hide the entity when RGB light is off or not in speed-controllable mode
            self._attr_available = False
            self._attr_current_option = None

        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Change the selected speed option."""
        if option not in self._attr_options:
            _LOGGER.error("Invalid speed option: %s", option)
            return

        if not self.coordinator.data:
            return

        device_state_data = self.coordinator.data
        if not isinstance(device_state_data, DreoCirculationFanDeviceData):
            _LOGGER.warning("RGB speed control is only available for circulation fans")
            return

        if not device_state_data.rgb_state:
            _LOGGER.warning("RGB light must be on to change speed")
            return

        if device_state_data.rgb_mode not in ["Cycle", "Fade"]:
            _LOGGER.warning("Speed can only be changed in Cycle or Fade mode")
            return

        speed_value = self._speed_mapping[option]

        command_params: dict[str, Any] = {"atmspeed": speed_value}

        await self.async_send_command_and_update(
            ERROR_SET_RGB_SPEED_FAILED, **command_params
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        if not (
            self.coordinator.last_update_success and self.coordinator.data is not None
        ):
            return False

        device_state_data = self.coordinator.data
        if not device_state_data.available:
            return False

        # Only available when RGB light is on and in Cycle/Fade mode
        if not isinstance(device_state_data, DreoCirculationFanDeviceData):
            return False

        return (
            device_state_data.rgb_state is not None
            and device_state_data.rgb_state
            and device_state_data.rgb_mode in ["Cycle", "Fade"]
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the optional state attributes."""
        if not hasattr(self.coordinator, "data") or self.coordinator.data is None:
            return None

        fan_data = self.coordinator.data
        attrs: dict[str, Any] = {}

        # Show current mode
        if (
            isinstance(fan_data, DreoCirculationFanDeviceData)
            and fan_data.rgb_mode is not None
        ):
            attrs["rgb_mode"] = fan_data.rgb_mode

        # Show speed range
        attrs["speed_range"] = f"{self._speed_range[0]}-{self._speed_range[1]}"

        # Show usage hint
        attrs["usage_hint"] = "Available only in Cycle and Fade modes"

        return attrs if attrs else None
