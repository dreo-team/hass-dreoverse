"""Support for Dreo select entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DreoConfigEntry
from .const import DreoDirective, DreoEntityConfigSpec, DreoErrorCode, DreoFeatureSpec
from .coordinator import (
    DreoCeilingFanDeviceData,
    DreoCirculationFanDeviceData,
    DreoDataUpdateCoordinator,
    DreoGenericDeviceData,
)
from .entity import DreoEntity
from .status_dependency import DreotStatusDependency

_LOGGER = logging.getLogger(__name__)


def _has_rgb_features(device_data: DreoGenericDeviceData) -> bool:
    """Check if device data has RGB features."""
    return isinstance(
        device_data, (DreoCirculationFanDeviceData, DreoCeilingFanDeviceData)
    )


ALLOWED_SELECT_CLASSES: set[str] = {"DreoGenericModeSelect", "DreoRgbSpeedSelect"}


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Dreo select entities from a config entry."""

    @callback
    def async_add_select_entities() -> None:
        """Add select entities."""
        selects: list[DreoRgbSpeedSelect | DreoGenericModeSelect] = []

        for device in config_entry.runtime_data.devices:
            # Do not gate by device_type here; rely on entitySupports and capabilities

            device_id = device.get("deviceSn")
            if not device_id:
                continue

            has_select_support = Platform.SELECT in device.get(
                DreoEntityConfigSpec.TOP_CONFIG, {}
            ).get("entitySupports", [])
            if not has_select_support:
                _LOGGER.debug(
                    "Model %s does not advertise select support; will infer from capabilities",
                    device.get("model"),
                )

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for device %s", device_id)
                continue

            config = coordinator.model_config
            entity_supports = config.get("entitySupports", [])
            if Platform.SELECT not in entity_supports:
                _LOGGER.warning(
                    "Model %s does not advertise select support; will infer from capabilities",
                    device.get("model"),
                )

            select_supports = config.get(DreoEntityConfigSpec.SELECT_ENTITY_CONF, [])
            for support in select_supports:
                select_name = support.get("selector")
                select_mappings = support.get("selector_mappings")

                if not select_name or select_name not in ALLOWED_SELECT_CLASSES:
                    _LOGGER.warning(
                        "Unsupported select class '%s' in config for model %s",
                        select_name,
                        device.get("model"),
                    )
                    continue

                cls = globals().get(select_name)
                if cls is None or not callable(cls):
                    _LOGGER.error(
                        "Select class '%s' not found or not callable", select_name
                    )
                    continue

                try:
                    entity = cls(device, coordinator, select_mappings)
                    selects.append(entity)
                except TypeError:
                    _LOGGER.error(
                        "Select class '%s' not found or not callable", select_name
                    )

        if selects:
            async_add_entities(selects)

    async_add_select_entities()


class DreoRgbSpeedSelect(DreoEntity, SelectEntity):
    """Dreo circulation fan RGB light speed select."""

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
        select_mappings: dict[str, Any],
    ) -> None:
        """Initialize the RGB speed select."""
        super().__init__(
            device,
            coordinator,
            "select",
            select_mappings.get(DreoFeatureSpec.ATTR_NAME),
        )

        device_id = device.get("deviceSn")
        self._attr_unique_id = f"{device_id}_rgb_speed"
        self._attr_name = select_mappings.get(DreoFeatureSpec.ATTR_NAME)
        self._attr_icon = select_mappings.get(DreoFeatureSpec.ATTR_ICON)
        self._status_dependency = DreotStatusDependency(
            select_mappings.get(DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, [])
        )

        self._attr_options = select_mappings.get("options", [])
        self._speed_mapping = select_mappings.get("value_map", {})
        self._attr_current_option = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            return

        device_state_data = self.coordinator.data
        match_depend = self._status_dependency(device_state_data)

        # Check if device has RGB features
        has_rgb = _has_rgb_features(device_state_data)
        rgb_state = getattr(device_state_data, "rgb_state", None) if has_rgb else None
        rgb_speed = getattr(device_state_data, "rgb_speed", None) if has_rgb else None

        self._attr_available = (
            device_state_data.available and bool(rgb_state) and match_depend
        )

        self._attr_current_option = rgb_speed if self._attr_available else None

        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Change the selected speed option."""
        if option not in self._attr_options:
            _LOGGER.error("Invalid speed option: %s", option)
            return

        if not self.coordinator.data:
            return

        device_state_data = self.coordinator.data
        has_rgb = _has_rgb_features(device_state_data)
        rgb_state = getattr(device_state_data, "rgb_state", None) if has_rgb else None

        if not rgb_state:
            _LOGGER.warning("RGB light must be on to change speed")
            return

        if not self._status_dependency(device_state_data):
            _LOGGER.warning("RGB speed can only be changed in allowed modes")
            return

        speed_value = self._speed_mapping.get(option, option)

        command_params: dict[str, Any] = {DreoDirective.AMBIENT_RGB_SPEED: speed_value}

        await self.async_send_command_and_update(
            DreoErrorCode.SET_RGB_SPEED_FAILED, **command_params
        )


class DreoGenericModeSelect(DreoEntity, SelectEntity):
    """Dreo generic mode select."""

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
        select_mappings: dict[str, Any],
    ) -> None:
        """Initialize the Generic Mode Select."""
        super().__init__(
            device, coordinator, "select", select_mappings.get("attr_name")
        )
        device_id = device.get("deviceSn")
        self._attr_unique_id = f"{device_id}_{self._attr_name}"

        self._directive_name = select_mappings.get("directive_name")
        self._attr_name = select_mappings.get("attr_name")
        self._attr_icon = select_mappings.get("attr_icon")
        self._state_attr_name = select_mappings.get("state_attr_name")
        self._status_dependency = DreotStatusDependency(
            select_mappings.get("status_available_dependencies", [])
        )

        self._attr_options = select_mappings.get("options", [])

        self._attr_current_option = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            return
        device_state_data = self.coordinator.data
        available_depend = self._status_dependency(device_state_data)
        self._attr_available = device_state_data.available and available_depend

        attr_name = self._state_attr_name
        current = getattr(device_state_data, attr_name, None) if attr_name else None
        self._attr_current_option = current
        super()._handle_coordinator_update()

    async def async_select_option(self, option: str) -> None:
        """Change the selected generic mode option."""
        if option not in self._attr_options:
            _LOGGER.error("Invalid generic mode option: %s", option)
            return

        directive_name = self._directive_name
        command_params: dict[str, Any] = (
            {directive_name: option} if directive_name else {}
        )
        if not self.coordinator.data or not getattr(
            self.coordinator.data, "is_on", False
        ):
            command_params[DreoDirective.POWER_SWITCH] = True

        await self.async_send_command_and_update(
            DreoErrorCode.SET_SWING_FAILED, **command_params
        )

    @property
    def available(self) -> bool:
        """Entity is available based on status dependency configuration."""
        if not super().available:
            return False
        data = self.coordinator.data
        if not data:
            return False
        return self._status_dependency(data)
