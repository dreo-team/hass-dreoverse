"""Support for Dreo humidifier entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.humidifier import (
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DreoConfigEntry
from .const import (
    ERROR_SET_HEC_HUMIDITY_FAILED,
    ERROR_SET_HUMIDIFIER_MODE_FAILED,
    ERROR_TURN_OFF_FAILED,
    ERROR_TURN_ON_FAILED,
    HEC_DEVICE_TYPE,
)
from .coordinator import DreoDataUpdateCoordinator, DreoHecDeviceData
from .entity import DreoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Dreo humidifier entities from a config entry."""

    @callback
    def async_add_humidifier_entities() -> None:
        """Add humidifier entities."""
        new_humidifiers: list[DreoHecHumidifier] = []

        for device in config_entry.runtime_data.devices:
            device_type = device.get("deviceType")
            if device_type != HEC_DEVICE_TYPE:
                continue

            device_id = device.get("deviceSn")
            if not device_id:
                continue

            # Debug entity support check
            device_config = device.get("config", {})
            entity_supports = device_config.get("entitySupports", [])
            device_model = device.get("model")

            _LOGGER.debug("Device %s config: %s", device_model, device_config)
            _LOGGER.debug("Device %s entitySupports: %s", device_model, entity_supports)
            _LOGGER.debug("Platform.HUMIDIFIER value: %s", Platform.HUMIDIFIER)

            if Platform.HUMIDIFIER not in entity_supports:
                _LOGGER.warning(
                    "No humidifier entity support for model %s (entitySupports: %s)",
                    device_model,
                    entity_supports,
                )
                continue

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for device %s", device_id)
                continue

            humidifier_entity = DreoHecHumidifier(device, coordinator)
            new_humidifiers.append(humidifier_entity)

        if new_humidifiers:
            async_add_entities(new_humidifiers)

    async_add_humidifier_entities()


class DreoHecHumidifier(DreoEntity, HumidifierEntity):
    """Dreo HEC (Hybrid Evaporative Cooler) humidifier entity."""

    _attr_supported_features = HumidifierEntityFeature.MODES
    _attr_is_on = False
    _attr_mode: str | None = None
    _attr_current_humidity: int | None = None
    _attr_target_humidity: int | None = None
    _attr_available_modes: list[str] = []

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the Dreo HEC humidifier."""
        super().__init__(device, coordinator, "humidifier", "Humidifier")

        model_config = coordinator.model_config

        humidity_range = model_config.get("humidity_range")
        if humidity_range and len(humidity_range) >= 2:
            self._attr_min_humidity = int(humidity_range[0])
            self._attr_max_humidity = int(humidity_range[1])

        self._attr_available_modes = model_config.get("preset_modes") or []

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attributes()
        super()._handle_coordinator_update()

    def _update_attributes(self) -> None:
        """Update attributes from coordinator data."""
        if not self.coordinator.data:
            return

        if not isinstance(self.coordinator.data, DreoHecDeviceData):
            return

        hec_data = self.coordinator.data
        self._attr_available = hec_data.available
        self._attr_is_on = hec_data.is_on

        if hec_data.target_humidity is not None:
            self._attr_target_humidity = int(hec_data.target_humidity)

        if (
            hec_data.mode
            and self._attr_available_modes
            and hec_data.mode in self._attr_available_modes
        ):
            self._attr_mode = hec_data.mode
        else:
            self._attr_mode = "Normal"

    @property
    def is_on(self) -> bool:
        """Return True if the humidifier is on."""
        return self._attr_is_on

    @property
    def mode(self) -> str | None:
        """Return the current mode."""
        return self._attr_mode

    @property
    def target_humidity(self) -> int | None:
        """Return the target humidity."""
        return self._attr_target_humidity

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the humidifier on."""
        await self.async_send_command_and_update(
            ERROR_TURN_ON_FAILED, power_switch=True
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the humidifier off."""
        await self.async_send_command_and_update(
            ERROR_TURN_OFF_FAILED, power_switch=False
        )

    async def async_set_humidity(self, humidity: int) -> None:
        """Set the target humidity."""
        if not (self._attr_min_humidity <= humidity <= self._attr_max_humidity):
            _LOGGER.error(
                "Humidity %d is out of range [%d-%d]",
                humidity,
                self._attr_min_humidity,
                self._attr_max_humidity,
            )
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params["power_switch"] = True

        command_params["humidity"] = int(humidity)

        await self.async_send_command_and_update(
            ERROR_SET_HEC_HUMIDITY_FAILED, **command_params
        )

    async def async_set_mode(self, mode: str) -> None:
        """Set the mode of the humidifier."""
        if not self._attr_available_modes or mode not in self._attr_available_modes:
            _LOGGER.error("Mode %s is not available", mode)
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params["power_switch"] = True

        command_params["mode"] = mode.capitalize()

        await self.async_send_command_and_update(
            ERROR_SET_HUMIDIFIER_MODE_FAILED, **command_params
        )
