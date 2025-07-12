"""Support for Dreo device RGB lights."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_EFFECT,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
    LightEntityFeature,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DreoConfigEntry
from .const import (
    CEILING_FAN_DEVICE_TYPE,
    CIR_FAN_DEVICE_TYPE,
    ERROR_TURN_OFF_FAILED,
    ERROR_TURN_ON_FAILED,
)
from .coordinator import (
    DreoCeilingFanDeviceData,
    DreoCirculationFanDeviceData,
    DreoDataUpdateCoordinator,
)
from .entity import DreoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Light from a config entry."""

    @callback
    def async_add_light_devices() -> None:
        """Add light devices."""
        new_lights: list[DreoCirculationFanLight | DreoCeilingFanLight] = []

        for device in config_entry.runtime_data.devices:
            device_type = device.get("deviceType")
            if device_type not in [CIR_FAN_DEVICE_TYPE, CEILING_FAN_DEVICE_TYPE]:
                continue

            device_id = device.get("deviceSn")
            if not device_id:
                continue

            if Platform.LIGHT not in device.get("config", {}).get("entitySupports", []):
                _LOGGER.warning(
                    "No light entity support for model %s", device.get("model")
                )
                continue

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for light device %s", device_id)
                continue

            if device_type == CIR_FAN_DEVICE_TYPE:
                new_lights.append(DreoCirculationFanLight(device, coordinator))
            elif device_type == CEILING_FAN_DEVICE_TYPE:
                new_lights.append(DreoCeilingFanLight(device, coordinator))
        if new_lights:
            async_add_entities(new_lights)

    async_add_light_devices()


class DreoCirculationFanLight(DreoEntity, LightEntity):
    """Dreo Circulation Fan RGB Light."""

    _attr_supported_features = LightEntityFeature.TRANSITION | LightEntityFeature.EFFECT
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB
    _attr_is_on = False
    _attr_brightness = None
    _attr_rgb_color = None
    _attr_effect = None

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the Dreo circulation fan RGB light."""
        super().__init__(device, coordinator, "light", "RGB Light")

        device_id = device.get("deviceSn")
        self._attr_unique_id = f"{device_id}_rgb_light"

        model_config = coordinator.model_config
        self._attr_effect_list = model_config.get("light_modes")

        self._brightness_range = tuple(model_config.get("brightness_range", [1, 3]))
        self._speed_range = tuple(model_config.get("light_speed_range", [1, 3]))

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        self._update_attributes()
        super()._handle_coordinator_update()

    def _update_attributes(self):
        """Update attributes from coordinator data."""
        if not self.coordinator.data:
            return

        fan_data = self.coordinator.data
        if fan_data.available is None:
            self._attr_available = False
            return

        self._attr_available = fan_data.available

        # Only handle RGB attributes for circulation fans
        if not isinstance(fan_data, DreoCirculationFanDeviceData):
            self._attr_is_on = False
            self._attr_rgb_color = None
            self._attr_brightness = None
            self._attr_effect = None
            return

        # 处理RGB开关状态
        if fan_data.rgb_state is not None:
            self._attr_is_on = fan_data.rgb_state
        else:
            self._attr_is_on = False

        # 处理RGB颜色 (0-16777215 -> RGB tuple)
        if fan_data.rgb_color is not None:
            color_int = fan_data.rgb_color
            r = (color_int >> 16) & 255
            g = (color_int >> 8) & 255
            b = color_int & 255
            self._attr_rgb_color = (r, g, b)
        else:
            self._attr_rgb_color = None

        # 处理亮度 (1-3 -> 0-255)
        if fan_data.rgb_brightness is not None:
            brightness_level = fan_data.rgb_brightness
            max_brightness = self._brightness_range[1]
            brightness_percent = (brightness_level / max_brightness) * 100
            self._attr_brightness = int((brightness_percent / 100) * 255)
        else:
            self._attr_brightness = None

        # 处理灯光效果
        if fan_data.rgb_mode is not None:
            self._attr_effect = fan_data.rgb_mode
        else:
            self._attr_effect = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the RGB light."""
        command_params: dict[str, Any] = {"ambient_switch": True}

        if ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            color_int = (r << 16) | (g << 8) | b
            command_params["atmcolor"] = color_int

        if ATTR_BRIGHTNESS in kwargs:
            brightness_255 = kwargs[ATTR_BRIGHTNESS]
            brightness_percent = (brightness_255 / 255) * 100
            max_brightness = self._brightness_range[1]
            brightness_level = max(1, int((brightness_percent / 100) * max_brightness))
            command_params["atmbri"] = brightness_level

        if ATTR_EFFECT in kwargs:
            effect = kwargs[ATTR_EFFECT]
            if self._attr_effect_list and effect in self._attr_effect_list:
                command_params["atmmode"] = effect
                if effect in ["Cycle", "Fade"]:
                    current_speed = None
                    if (
                        self.coordinator.data
                        and isinstance(
                            self.coordinator.data, DreoCirculationFanDeviceData
                        )
                        and self.coordinator.data.rgb_speed is not None
                    ):
                        current_speed = self.coordinator.data.rgb_speed
                    else:
                        current_speed = 2
                    command_params["atmspeed"] = current_speed

        await self.async_send_command_and_update(ERROR_TURN_ON_FAILED, **command_params)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the RGB light."""
        await self.async_send_command_and_update(
            ERROR_TURN_OFF_FAILED, ambient_switch=False
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Return the optional state attributes."""
        if not hasattr(self.coordinator, "data") or self.coordinator.data is None:
            return None

        fan_data = self.coordinator.data
        attrs: dict[str, Any] = {}

        if (
            isinstance(fan_data, DreoCirculationFanDeviceData)
            and fan_data.rgb_mode is not None
        ):
            mode = fan_data.rgb_mode
            attrs["current_mode"] = mode

            features = []
            if mode in ["SteadyOn", "Fade"]:
                features.append("color")
            if mode in ["SteadyOn", "Cycle"]:
                features.append("brightness")
            if mode in ["Cycle", "Fade"]:
                features.append("speed")
            attrs["available_features"] = features

        if (
            isinstance(fan_data, DreoCirculationFanDeviceData)
            and fan_data.rgb_speed is not None
            and fan_data.rgb_mode in ["Cycle", "Fade"]
        ):
            attrs["light_speed"] = fan_data.rgb_speed
            attrs["speed_range"] = f"{self._speed_range[0]}-{self._speed_range[1]}"

        if isinstance(fan_data, DreoCirculationFanDeviceData) and fan_data.rgb_mode in [
            "Cycle",
            "Fade",
        ]:
            attrs["speed_service"] = (
                "Use 'dreo.set_light_speed' service to change speed"
            )

        return attrs if attrs else None

    async def async_set_light_speed(self, speed: int) -> None:
        """Set the light animation speed (for Cycle and Fade modes)."""
        if not (self._speed_range[0] <= speed <= self._speed_range[1]):
            _LOGGER.error(
                "Speed %d is out of range [%d-%d]",
                speed,
                self._speed_range[0],
                self._speed_range[1],
            )
            return

        if (
            self.coordinator.data
            and isinstance(self.coordinator.data, DreoCirculationFanDeviceData)
            and self.coordinator.data.rgb_mode in ["Cycle", "Fade"]
        ):
            command_params: dict[str, Any] = {"atmspeed": speed}
            await self.async_send_command_and_update(
                ERROR_TURN_ON_FAILED, **command_params
            )
        else:
            _LOGGER.warning(
                "Light speed can only be set in Cycle or Fade mode. Current mode: %s",
                getattr(self.coordinator.data, "rgb_mode", "Unknown"),
            )


class DreoCeilingFanLight(DreoEntity, LightEntity):
    """Dreo Ceiling Fan Light."""

    _attr_supported_features = LightEntityFeature.TRANSITION
    _attr_supported_color_modes = {ColorMode.COLOR_TEMP}
    _attr_color_mode = ColorMode.COLOR_TEMP
    _attr_is_on = False
    _attr_brightness = None
    _attr_color_temp_kelvin = None
    _attr_min_color_temp_kelvin = 2700  # warm white
    _attr_max_color_temp_kelvin = 6500  # cold white

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the Dreo ceiling fan light."""
        super().__init__(device, coordinator, "light", "Light")

        device_id = device.get("deviceSn")
        self._attr_unique_id = f"{device_id}_light"

        model_config = coordinator.model_config
        brightness_range = model_config.get("brightness_range", [1, 100])
        color_temp_range = model_config.get("color_temperature", [1, 100])

        self._brightness_range = tuple(brightness_range)
        self._color_temp_range = tuple(color_temp_range)

    @callback
    def _handle_coordinator_update(self):
        """Handle updated data from the coordinator."""
        self._update_attributes()
        super()._handle_coordinator_update()

    def _update_attributes(self):
        """Update attributes from coordinator data."""
        if not self.coordinator.data:
            return

        if not isinstance(self.coordinator.data, DreoCeilingFanDeviceData):
            _LOGGER.warning(
                "Expected DreoCeilingFanDeviceData, got %s", type(self.coordinator.data)
            )
            return

        ceiling_fan_data = self.coordinator.data
        self._attr_available = ceiling_fan_data.available

        if (
            hasattr(ceiling_fan_data, "light_switch")
            and ceiling_fan_data.light_switch is not None
        ):
            self._attr_is_on = ceiling_fan_data.light_switch
        else:
            self._attr_is_on = False

        # deal with brightness (1-100 -> 0-255)
        if (
            hasattr(ceiling_fan_data, "light_brightness")
            and ceiling_fan_data.light_brightness is not None
        ):
            brightness_percent = ceiling_fan_data.light_brightness
            self._attr_brightness = int((brightness_percent / 100) * 255)
        else:
            self._attr_brightness = None

        # deal with color temperature (1-100 -> 2700K-6500K)
        if (
            hasattr(ceiling_fan_data, "light_color_temp")
            and ceiling_fan_data.light_color_temp is not None
        ):
            color_temp_percent = ceiling_fan_data.light_color_temp
            temp_range = (
                self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin
            )
            kelvin = (
                self._attr_min_color_temp_kelvin
                + (color_temp_percent / 100) * temp_range
            )
            self._attr_color_temp_kelvin = int(kelvin)
        else:
            self._attr_color_temp_kelvin = None

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the light."""
        command_params: dict[str, Any] = {"light_switch": True}

        # deal with brightness (0-255 -> 1-100)
        if ATTR_BRIGHTNESS in kwargs:
            brightness_255 = kwargs[ATTR_BRIGHTNESS]
            brightness_percent = max(1, int((brightness_255 / 255) * 100))
            command_params["brightness"] = brightness_percent

        # deal with color temperature (2700K-6500K -> 1-100)
        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            # ensure color temperature is within supported range
            kelvin = max(
                self._attr_min_color_temp_kelvin,
                min(self._attr_max_color_temp_kelvin, kelvin),
            )
            # map kelvin value to 1-100
            temp_range = (
                self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin
            )
            color_temp_percent = (
                (kelvin - self._attr_min_color_temp_kelvin) / temp_range
            ) * 100
            command_params["colortemp"] = max(1, int(color_temp_percent))

        await self.async_send_command_and_update(ERROR_TURN_ON_FAILED, **command_params)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.async_send_command_and_update(
            ERROR_TURN_OFF_FAILED, light_switch=False
        )
