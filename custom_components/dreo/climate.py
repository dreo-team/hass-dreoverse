"""Support for Dreo climate entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    ClimateEntity,
    ClimateEntityFeature,
    HVACMode,
)
from homeassistant.const import ATTR_TEMPERATURE, Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DreoConfigEntry
from .const import (
    DOMAIN,
    ERROR_SET_FAN_MODE_FAILED,
    ERROR_SET_HUMIDITY_FAILED,
    ERROR_SET_HVAC_MODE_FAILED,
    ERROR_SET_TEMPERATURE_FAILED,
    ERROR_TURN_OFF_FAILED,
    ERROR_TURN_ON_FAILED,
    HAC_DEVICE_TYPE,
)
from .coordinator import DreoDataUpdateCoordinator, DreoHacDeviceData
from .entity import DreoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Dreo climate entities from a config entry."""

    @callback
    def async_add_climate_entities() -> None:
        """Add climate entities."""
        new_climates: list[DreoHacClimate] = []

        for device in config_entry.runtime_data.devices:
            device_type = device.get("deviceType")
            if device_type != HAC_DEVICE_TYPE:
                continue

            device_id = device.get("deviceSn")
            if not device_id:
                continue

            if Platform.CLIMATE not in device.get("config", {}).get(
                "entitySupports", []
            ):
                _LOGGER.warning(
                    "No climate entity support for model %s", device.get("model")
                )
                continue

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for device %s", device_id)
                continue

            climate_entity = DreoHacClimate(device, coordinator)
            new_climates.append(climate_entity)

        if new_climates:
            async_add_entities(new_climates)

    async_add_climate_entities()


class DreoHacClimate(DreoEntity, ClimateEntity):
    """Dreo HAC (Air Conditioner) climate entity."""

    _attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY, HVACMode.FAN_ONLY]
    _attr_target_temperature_step = 1.0
    _attr_target_humidity_step = 5.0
    _attr_hvac_mode = HVACMode.OFF
    _attr_fan_mode: str | None = None
    _attr_preset_mode: str | None = None

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the Dreo HAC climate entity."""
        super().__init__(device, coordinator, "climate", None)

        config = coordinator.model_config

        self._attr_preset_modes = config.get("preset_modes", [])

        temp_range = config.get("temperature_range", [])
        if temp_range and len(temp_range) >= 2:
            self._attr_min_temp = float(temp_range[0])
            self._attr_max_temp = float(temp_range[1])

        humidity_range = config.get("humidity_range", [])
        if humidity_range and len(humidity_range) >= 2:
            self._attr_min_humidity = float(humidity_range[0])
            self._attr_max_humidity = float(humidity_range[1])

        speed_range = config.get("speed_range", [])
        self._speed_range = tuple(speed_range)

        max_speed = self._speed_range[1]
        self._attr_fan_modes = []
        for i in range(1, max_speed + 1):
            self._attr_fan_modes.append(str(i))

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attributes()
        super()._handle_coordinator_update()

    def _update_attributes(self) -> None:
        """Update attributes from coordinator data."""
        if not self.coordinator.data:
            return

        if not isinstance(self.coordinator.data, DreoHacDeviceData):
            return

        hac_data = self.coordinator.data
        self._attr_available = hac_data.available

        previous_hvac_mode = self._attr_hvac_mode

        if not hac_data.is_on:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = None
            self._attr_current_temperature = None
        else:
            device_mode = hac_data.mode
            hvac_mode = hac_data.hvac_mode

            if hvac_mode and hvac_mode in [mode.value for mode in HVACMode]:
                self._attr_hvac_mode = HVACMode(hvac_mode)
            else:
                self._attr_hvac_mode = HVACMode.COOL

            self._attr_preset_mode = None

            if self._attr_preset_modes and device_mode in self._attr_preset_modes:
                self._attr_preset_mode = device_mode
                self._attr_hvac_mode = HVACMode.COOL

            if hac_data.speed_level:
                self._attr_fan_mode = str(hac_data.speed_level)
            else:
                self._attr_fan_mode = "1"

            if hac_data.current_temperature is not None:
                self._attr_current_temperature = hac_data.current_temperature

        if hac_data.target_temperature is not None:
            self._attr_target_temperature = hac_data.target_temperature

        if hac_data.target_humidity is not None:
            self._attr_target_humidity = hac_data.target_humidity

        if previous_hvac_mode != self._attr_hvac_mode:
            if self._attr_hvac_mode in (HVACMode.DRY, HVACMode.COOL):
                pass

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_send_command_and_update(
                ERROR_TURN_OFF_FAILED, power_switch=False
            )
        else:
            command_params: dict[str, Any] = {}

            if not self.is_on:
                command_params["power_switch"] = True

            if hvac_mode in self._attr_hvac_modes:
                command_params["hvacmode"] = hvac_mode

            await self.async_send_command_and_update(
                ERROR_SET_HVAC_MODE_FAILED, **command_params
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if self._attr_preset_modes and preset_mode not in self._attr_preset_modes:
            _LOGGER.error("Invalid preset mode: %s", preset_mode)
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params["power_switch"] = True

        if self._attr_hvac_mode != HVACMode.COOL:
            raise ValueError("Preset mode can only be set in Cool mode")

        command_params["mode"] = preset_mode

        await self.async_send_command_and_update(
            ERROR_SET_HVAC_MODE_FAILED, **command_params
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        if self._attr_fan_modes and fan_mode not in self._attr_fan_modes:
            _LOGGER.error("Invalid fan mode: %s", fan_mode)
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params["power_switch"] = True

        command_params["speed"] = int(fan_mode)

        await self.async_send_command_and_update(
            ERROR_SET_FAN_MODE_FAILED, **command_params
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        if self._attr_hvac_mode != HVACMode.COOL:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key=ERROR_SET_TEMPERATURE_FAILED
            )

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params["power_switch"] = True

        command_params["temperature"] = int(temperature)

        await self.async_send_command_and_update(
            ERROR_SET_TEMPERATURE_FAILED, **command_params
        )

    async def async_set_humidity(self, humidity: int) -> None:
        """Set new target humidity."""

        if self._attr_hvac_mode != HVACMode.DRY:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key=ERROR_SET_HUMIDITY_FAILED
            )
        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params["power_switch"] = True

        command_params["humidity"] = int(humidity)

        await self.async_send_command_and_update(
            ERROR_SET_HUMIDITY_FAILED, **command_params
        )

    async def async_turn_on(self) -> None:
        """Turn the device on."""
        await self.async_send_command_and_update(
            ERROR_TURN_ON_FAILED, power_switch=True
        )

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        await self.async_send_command_and_update(
            ERROR_TURN_OFF_FAILED, power_switch=False
        )

    @property
    def is_on(self) -> bool:
        """Return if entity is on."""
        return self._attr_hvac_mode != HVACMode.OFF

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return (
            self.coordinator.last_update_success
            and self.coordinator.data is not None
            and self.coordinator.data.available
        )

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Return the list of supported features based on current mode."""
        base_features = (
            ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
        )

        if self._attr_hvac_mode == HVACMode.COOL:
            base_features |= ClimateEntityFeature.TARGET_TEMPERATURE
            base_features |= ClimateEntityFeature.PRESET_MODE
        elif self._attr_hvac_mode == HVACMode.DRY:
            base_features |= ClimateEntityFeature.TARGET_HUMIDITY

        return base_features
