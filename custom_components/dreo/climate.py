"""Support for Dreo climate entities."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.climate import (
    SWING_OFF,
    SWING_ON,
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
    DreoDeviceType,
    DreoDirective,
    DreoEntityConfigSpec,
    DreoErrorCode,
    DreoFeatureSpec,
)
from .coordinator import (
    DreoDataUpdateCoordinator,
    DreoHacDeviceData,
    DreoHeaterDeviceData,
)
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
        climates: list[DreoHacClimate | DreoHeaterClimate] = []

        for device in config_entry.runtime_data.devices:
            device_type = device.get("deviceType")
            if device_type not in (DreoDeviceType.HAC, DreoDeviceType.HEATER):
                continue

            device_id = device.get("deviceSn")
            if not device_id:
                continue

            has_climate_support = Platform.CLIMATE in device.get(
                DreoEntityConfigSpec.TOP_CONFIG, {}
            ).get(DreoEntityConfigSpec.ENTITY_SUPPORTS, [])

            if not has_climate_support and device_type != DreoDeviceType.HEATER:
                _LOGGER.warning(
                    "No climate entity support for model %s", device.get("model")
                )
                continue

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for device %s", device_id)
                continue

            climate_entity: ClimateEntity
            if device_type == DreoDeviceType.HAC:
                climate_entity = DreoHacClimate(device, coordinator)
            elif device_type == DreoDeviceType.HEATER:
                climate_entity = DreoHeaterClimate(device, coordinator)
            else:
                continue
            climates.append(climate_entity)

        if climates:
            async_add_entities(climates)

    async_add_climate_entities()


class DreoHacClimate(DreoEntity, ClimateEntity):
    """Dreo HAC (Air Conditioner) climate entity."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.COOL, HVACMode.DRY, HVACMode.FAN_ONLY]
    _attr_target_temperature_step = 1.0
    _attr_target_humidity_step = 5.0
    _attr_hvac_mode = HVACMode.OFF
    _attr_fan_mode: str | None = None
    _attr_preset_mode: str | None = None
    _attr_swing_mode: str | None = None
    _attr_swing_modes = [SWING_OFF, SWING_ON]

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the Dreo HAC climate entity."""
        super().__init__(device, coordinator, "climate", None)

        fan_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF.value, {}
        )
        self._attr_preset_modes = fan_config.get(DreoFeatureSpec.PRESET_MODES, [])

        # Get temperature unit from fan config, default to system unit
        temp_unit = fan_config.get("temperature_unit")
        if temp_unit == "celsius":
            self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        elif temp_unit == "fahrenheit":
            self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
        else:
            # Default to system unit preference
            self._attr_temperature_unit = coordinator.hass.config.units.temperature_unit
        # Enable swing feature for HAC
        self._attr_supported_features = (
            ClimateEntityFeature.FAN_MODE
            | ClimateEntityFeature.TURN_ON
            | ClimateEntityFeature.TURN_OFF
            | ClimateEntityFeature.SWING_MODE
        )

        temp_range = fan_config.get(DreoFeatureSpec.TEMPERATURE_RANGE, [])
        if temp_range and len(temp_range) >= 2:
            self._attr_min_temp = float(temp_range[0])
            self._attr_max_temp = float(temp_range[1])

        humidity_range = fan_config.get(DreoFeatureSpec.HUMIDITY_RANGE, [])
        if humidity_range and len(humidity_range) >= 2:
            self._attr_min_humidity = float(humidity_range[0])
            self._attr_max_humidity = float(humidity_range[1])

        speed_range = fan_config.get(DreoFeatureSpec.SPEED_RANGE, [])
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

        if not hac_data.is_on:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = None
            self._attr_current_temperature = None
        else:
            hvac_mode = hac_data.hvac_mode
            self._attr_hvac_mode = (
                HVACMode(hvac_mode)
                if hvac_mode and hvac_mode in [mode.value for mode in HVACMode]
                else HVACMode.COOL
            )

            self._attr_preset_mode = None

            device_mode = hac_data.mode
            if self._attr_preset_modes and device_mode in self._attr_preset_modes:
                self._attr_preset_mode = device_mode
                self._attr_hvac_mode = HVACMode.COOL

            self._attr_fan_mode = (
                str(hac_data.speed_level) if hac_data.speed_level else "1"
            )

            osc = getattr(hac_data, DreoDirective.OSCILLATE, None)
            self._attr_swing_mode = (
                None if osc is None else (SWING_ON if osc else SWING_OFF)
            )

            self._attr_current_temperature = (
                hac_data.current_temperature
                if hac_data.current_temperature is not None
                else self._attr_current_temperature
            )

        if hac_data.target_temperature is not None:
            self._attr_target_temperature = hac_data.target_temperature

        if hac_data.target_humidity is not None:
            self._attr_target_humidity = hac_data.target_humidity

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_send_command_and_update(
                DreoErrorCode.TURN_OFF_FAILED, power_switch=False
            )
        else:
            command_params: dict[str, Any] = {}

            if not self.is_on:
                command_params[DreoDirective.POWER_SWITCH] = True

            if hvac_mode in self._attr_hvac_modes:
                command_params[DreoDirective.HVAC_MODE] = hvac_mode

            await self.async_send_command_and_update(
                DreoErrorCode.SET_HVAC_MODE_FAILED, **command_params
            )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if self._attr_preset_modes and preset_mode not in self._attr_preset_modes:
            _LOGGER.error("Invalid preset mode: %s", preset_mode)
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params[DreoDirective.POWER_SWITCH] = True

        if self._attr_hvac_mode != HVACMode.COOL:
            raise ValueError("Preset mode can only be set in Cool mode")

        command_params[DreoDirective.MODE] = preset_mode

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HVAC_MODE_FAILED, **command_params
        )

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Set new target fan mode."""
        if self._attr_fan_modes and fan_mode not in self._attr_fan_modes:
            _LOGGER.error("Invalid fan mode: %s", fan_mode)
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params[DreoDirective.POWER_SWITCH] = True

        command_params[DreoDirective.SPEED] = int(fan_mode)

        await self.async_send_command_and_update(
            DreoErrorCode.SET_FAN_MODE_FAILED, **command_params
        )

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Set swing (oscillation) on or off."""
        if swing_mode not in (SWING_ON, SWING_OFF):
            _LOGGER.error("Invalid swing mode: %s", swing_mode)
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params[DreoDirective.POWER_SWITCH] = True

        command_params[DreoDirective.SWING_SWITCH] = swing_mode == SWING_ON

        await self.async_send_command_and_update(
            DreoErrorCode.SET_SWING_FAILED, **command_params
        )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature is None:
            return

        if self._attr_hvac_mode != HVACMode.COOL:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=DreoErrorCode.SET_TEMPERATURE_FAILED,
            )

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params[DreoDirective.POWER_SWITCH] = True

        command_params[DreoDirective.TEMPERATURE] = int(temperature)

        await self.async_send_command_and_update(
            DreoErrorCode.SET_TEMPERATURE_FAILED, **command_params
        )

    async def async_set_humidity(self, humidity: int) -> None:
        """Set new target humidity."""
        if self._attr_hvac_mode != HVACMode.DRY:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=DreoErrorCode.SET_HUMIDITY_FAILED,
            )
        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params[DreoDirective.POWER_SWITCH] = True

        command_params[DreoDirective.HUMIDITY] = int(humidity)

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HUMIDITY_FAILED, **command_params
        )

    async def async_turn_on(self) -> None:
        """Turn the device on."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_ON_FAILED, power_switch=True
        )

    async def async_turn_off(self) -> None:
        """Turn the device off."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_OFF_FAILED, power_switch=False
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
        base = self._attr_supported_features

        if self._attr_hvac_mode == HVACMode.COOL:
            base |= ClimateEntityFeature.TARGET_TEMPERATURE
            base |= ClimateEntityFeature.PRESET_MODE
        elif self._attr_hvac_mode == HVACMode.DRY:
            base |= ClimateEntityFeature.TARGET_HUMIDITY

        return base


class DreoHeaterClimate(DreoEntity, ClimateEntity):
    """Dreo Heater climate entity."""

    _attr_hvac_modes = [HVACMode.OFF, HVACMode.HEAT, HVACMode.FAN_ONLY]
    _attr_target_temperature_step = 1.0
    _attr_hvac_mode = HVACMode.OFF
    _attr_preset_mode: str | None = None
    _attr_current_temperature: float | None = None
    _attr_target_temperature: float | None = None
    _attr_hvac_mode_relate_map: dict[str, Any] | None = None

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the Dreo heater climate entity."""
        super().__init__(device, coordinator, "climate", None)

        heater_config = coordinator.model_config.get(
            DreoEntityConfigSpec.HEATER_ENTITY_CONF, {}
        )
        self._attr_hvac_modes = heater_config.get(DreoFeatureSpec.HVAC_MODES, [])
        self._attr_hvac_mode_relate_map = heater_config.get(
            DreoFeatureSpec.HVAC_MODE_RELATE_MAP, {}
        )

        self._attr_preset_modes = heater_config.get(DreoFeatureSpec.PRESET_MODES, [])

        temp_unit = heater_config.get("temperature_unit")
        if temp_unit == "celsius":
            self._attr_temperature_unit = UnitOfTemperature.CELSIUS
        elif temp_unit == "fahrenheit":
            self._attr_temperature_unit = UnitOfTemperature.FAHRENHEIT
        else:
            self._attr_temperature_unit = coordinator.hass.config.units.temperature_unit

        temp_range = heater_config.get(DreoFeatureSpec.TEMPERATURE_RANGE, [])
        if isinstance(temp_range, (list, tuple)) and len(temp_range) >= 2:
            self._attr_min_temp = float(temp_range[0])
            self._attr_max_temp = float(temp_range[1])
        else:
            self._attr_min_temp = 41
            self._attr_max_temp = 85

        if isinstance(coordinator.data, DreoHeaterDeviceData):
            self._attr_target_temperature = coordinator.data.target_temperature
            self._attr_current_temperature = coordinator.data.current_temperature
        else:
            self._attr_target_temperature = None
            self._attr_current_temperature = None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        if not isinstance(data, DreoHeaterDeviceData):
            return

        self._attr_available = data.available

        self._attr_supported_features = (
            ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
        )

        if not data.is_on:
            self._attr_hvac_mode = HVACMode.OFF
            self._attr_preset_mode = None
        else:
            mode_config = (
                self._attr_hvac_mode_relate_map.get(data.hvac_mode, {})
                if self._attr_hvac_mode_relate_map and data.hvac_mode
                else {}
            )

            if supported_features := mode_config.get(
                DreoFeatureSpec.SUPPORTED_FEATURES, []
            ):
                for feature in supported_features:
                    self._attr_supported_features |= feature

            if hvac_mode_mapping := mode_config.get(DreoFeatureSpec.HVAC_MODE_REPORT):
                if isinstance(hvac_mode_mapping, dict):
                    self._attr_preset_mode = hvac_mode_mapping.get(
                        DreoFeatureSpec.DIRECTIVE_VALUE
                    )
                    if hvac_mode_value := hvac_mode_mapping.get(
                        DreoFeatureSpec.HVAC_MODE_VALUE
                    ):
                        self._attr_hvac_mode = HVACMode(hvac_mode_value)
            else:
                self._attr_preset_mode = data.mode
                if data.hvac_mode:
                    self._attr_hvac_mode = HVACMode(data.hvac_mode)

            if self._attr_hvac_mode in [HVACMode.HEAT]:
                self._attr_supported_features |= ClimateEntityFeature.PRESET_MODE

        self._attr_current_temperature = (
            data.current_temperature
            if data.current_temperature is not None
            else self._attr_current_temperature
        )

        if data.target_temperature is not None:
            self._attr_target_temperature = data.target_temperature

        super()._handle_coordinator_update()
        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set new target hvac mode."""
        if hvac_mode == HVACMode.OFF:
            await self.async_send_command_and_update(
                DreoErrorCode.TURN_OFF_FAILED, power_switch=False
            )
        else:
            await self.async_send_command_and_update(
                DreoErrorCode.TURN_ON_FAILED, power_switch=True, hvacmode=hvac_mode
            )

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set new target temperature."""
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is None:
            return

        temperature = max(self._attr_min_temp, min(self._attr_max_temp, temperature))

        await self.async_send_command_and_update(
            DreoErrorCode.SET_TEMPERATURE_FAILED, ecolevel=int(temperature)
        )

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Set new preset mode."""
        if not self._attr_preset_modes or preset_mode not in self._attr_preset_modes:
            return

        command_dict = {}
        preset_mode_controls = []
        if self._attr_hvac_mode_relate_map:
            mode_config = self._attr_hvac_mode_relate_map.get(preset_mode, {})
            if isinstance(mode_config, dict):
                preset_mode_controls = mode_config.get(
                    DreoFeatureSpec.PRESET_MODE_CONTROL, []
                )
        for control in preset_mode_controls:
            directive_name = control.get(DreoFeatureSpec.DIRECTIVE_NAME)
            directive_value = control.get(DreoFeatureSpec.DIRECTIVE_VALUE)
            if directive_name and directive_value:
                command_dict[directive_name] = directive_value

        if command_dict:
            await self.async_send_command_and_update(
                DreoErrorCode.SET_PRESET_MODE_FAILED, **command_dict
            )
