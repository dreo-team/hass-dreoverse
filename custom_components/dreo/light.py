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
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)

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
    DreoCeilingFanDeviceData,
    DreoCirculationFanDeviceData,
    DreoDataUpdateCoordinator,
    DreoGenericDeviceData,
    DreoHecDeviceData,
    DreoHumidifierDeviceData,
)
from .entity import DreoEntity

_LOGGER = logging.getLogger(__name__)


def _has_rgb_features(device_data: DreoGenericDeviceData) -> bool:
    """Check if device data has RGB features."""
    return isinstance(
        device_data,
        (
            DreoCirculationFanDeviceData,
            DreoCeilingFanDeviceData,
            DreoHecDeviceData,
            DreoHumidifierDeviceData,
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Light from a config entry."""

    @callback
    def async_add_light_devices() -> None:
        """Add light devices."""
        lights: list[DreoRGBLight | DreoRegularLight] = []

        for device in config_entry.runtime_data.devices:
            device_type = device.get("deviceType")
            if device_type not in [
                DreoDeviceType.CIR_FAN,
                DreoDeviceType.CEILING_FAN,
                DreoDeviceType.RGBLIGHT_CEILING_FAN,
                DreoDeviceType.HEC,
                DreoDeviceType.HUMIDIFIER,
            ]:
                continue

            device_id = device.get("deviceSn")
            if not device_id:
                continue

            if Platform.LIGHT not in device.get(
                DreoEntityConfigSpec.TOP_CONFIG, {}
            ).get("entitySupports", []):
                _LOGGER.warning(
                    "No light entity support for model %s", device.get("model")
                )
                continue

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for light device %s", device_id)
                continue

            if device_type == DreoDeviceType.CIR_FAN:
                lights.append(DreoRGBLight(device, coordinator))
            elif device_type == DreoDeviceType.CEILING_FAN:
                lights.append(DreoRegularLight(device, coordinator))
            elif device_type == DreoDeviceType.RGBLIGHT_CEILING_FAN:
                lights.append(DreoRGBLight(device, coordinator))
                lights.append(DreoRegularLight(device, coordinator))
            elif device_type == DreoDeviceType.HEC or DreoDeviceType.HUMIDIFIER:
                lights.append(DreoRGBLight(device, coordinator))
        if lights:
            async_add_entities(lights)

    async_add_light_devices()


class DreoRGBLight(DreoEntity, LightEntity):
    """Dreo Circulation Fan RGB Light."""

    _attr_is_on = False
    _attr_brightness = None
    _attr_rgb_color = None
    _attr_effect = None
    _attr_supported_color_modes = {ColorMode.RGB}
    _attr_color_mode = ColorMode.RGB

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the Dreo circulation fan RGB light."""
        super().__init__(device, coordinator, "light", "RGB Light")

        device_id = device.get("deviceSn")
        self._attr_unique_id = f"{device_id}_rgb_light"
        self._device_type = coordinator.device_type

        rgb_light_config = coordinator.model_config.get(
            DreoEntityConfigSpec.RGBLIGHT_ENTITY_CONF, {}
        )

        self._attr_effect_list = rgb_light_config.get(DreoFeatureSpec.LIGHT_MODES)
        self._brightness_percentage = tuple(
            rgb_light_config.get(DreoFeatureSpec.BRIGHTNESS_PERCENTAGE, [1, 100])
        )
        self._rgb_brightness = tuple[Any, ...](
            rgb_light_config.get(DreoFeatureSpec.RGB_BRIGHTNESS, [])
        )

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

        # Check if device has RGB features
        has_rgb = _has_rgb_features(fan_data)
        self._attr_is_on = bool(fan_data.rgb_state) if has_rgb else False
        self._attr_effect = fan_data.rgb_mode if has_rgb else None
        self._attr_color_mode = ColorMode.RGB

        if fan_data.rgb_color is not None:
            color_int = fan_data.rgb_color
            r = (color_int >> 16) & 255
            g = (color_int >> 8) & 255
            b = color_int & 255
            self._attr_rgb_color = (r, g, b)

        if self._attr_effect != "Breath" and self._device_type != DreoDeviceType.HEC:
            async_delete_issue(
                self.hass,
                "dreo",
                f"brightness_disabled_breath_{self.entity_id}",
            )

        if fan_data.rgb_brightness is not None:
            rgb_brightness = fan_data.rgb_brightness
            max_brightness = self._rgb_brightness[1]
            brightness_percent = (rgb_brightness / max_brightness) * 100
            self._attr_brightness = int((brightness_percent / 100) * 255)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the RGB light."""
        command_params: dict[str, Any] = {DreoDirective.AMBIENT_SWITCH: True}

        if ATTR_RGB_COLOR in kwargs:
            r, g, b = kwargs[ATTR_RGB_COLOR]
            color_int = (r << 16) | (g << 8) | b
            command_params[DreoDirective.AMBIENT_RGB_COLOR] = color_int

        if ATTR_BRIGHTNESS in kwargs:
            current_rgb_mode = None
            if self.coordinator.data and _has_rgb_features(self.coordinator.data):
                current_rgb_mode = getattr(self.coordinator.data, "rgb_mode", None)

            if current_rgb_mode == "Breath" and self._device_type != DreoDeviceType.HEC:
                _LOGGER.warning(
                    "Brightness control is disabled in %s mode for %s. Use color picker to change colors",
                    current_rgb_mode,
                    self.entity_id,
                )

                async_create_issue(
                    self.hass,
                    DOMAIN,
                    f"brightness_disabled_breath_{self.entity_id}",
                    is_fixable=False,
                    is_persistent=True,
                    severity=IssueSeverity.ERROR,
                    translation_key="brightness_disabled_breath",
                    translation_placeholders={
                        "entity_name": str(self.name) if self.name else self.entity_id,
                    },
                )
            else:
                max_brightness = self._rgb_brightness[1]
                brightness_255 = kwargs[ATTR_BRIGHTNESS]
                brightness_percent = (brightness_255 / 255) * 100
                brightness_value = max(
                    1, int((brightness_percent / 100) * max_brightness)
                )
                command_params[DreoDirective.AMBIENT_RGB_BRIGHTNESS] = brightness_value

        if ATTR_EFFECT in kwargs:
            effect = kwargs[ATTR_EFFECT]
            if self._attr_effect_list and effect in self._attr_effect_list:
                command_params[DreoDirective.AMBIENT_RGB_MODE] = effect
                if (
                    effect in ["Breath", "Circle"]
                    and self.coordinator.data
                    and _has_rgb_features(self.coordinator.data)
                    and getattr(self.coordinator.data, "rgb_speed", None) is not None
                ):
                    current_speed = getattr(self.coordinator.data, "rgb_speed", None)
                    command_params[DreoDirective.AMBIENT_RGB_SPEED] = current_speed

        await self.async_send_command_and_update(
            DreoErrorCode.TURN_ON_FAILED, **command_params
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the RGB light."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_OFF_FAILED, ambient_switch=False
        )

    @property
    def supported_features(self) -> LightEntityFeature:
        """Return the supported features based on current mode."""
        return LightEntityFeature.TRANSITION | LightEntityFeature.EFFECT

    @property
    def brightness(self) -> int | None:
        """Return the brightness of this light between 0..255."""
        current_rgb_mode = None
        if self.coordinator.data and _has_rgb_features(self.coordinator.data):
            current_rgb_mode = getattr(self.coordinator.data, "rgb_mode", None)

        if current_rgb_mode == "Breath" and self._device_type != DreoDeviceType.HEC:
            return None

        return self._attr_brightness

    async def async_set_rgb_color_direct(self, red: int, green: int, blue: int) -> None:
        """Set RGB color directly via service call."""
        if not (0 <= red <= 255 and 0 <= green <= 255 and 0 <= blue <= 255):
            _LOGGER.error(
                "RGB values must be between 0-255. Got: R=%d, G=%d, B=%d",
                red,
                green,
                blue,
            )
            return

        color_int = (red << 16) | (green << 8) | blue
        command_params: dict[str, Any] = {DreoDirective.AMBIENT_RGB_COLOR: color_int}

        await self.async_send_command_and_update(
            DreoErrorCode.TURN_ON_FAILED, **command_params
        )

    async def async_set_light_speed(self, speed: int) -> None:
        """Set the light animation speed (for Circle and Breath modes)."""
        rgb_mode = None
        if self.coordinator.data and _has_rgb_features(self.coordinator.data):
            rgb_mode = getattr(self.coordinator.data, "rgb_mode", None)

        if rgb_mode and rgb_mode in ["Circle", "Breath"]:
            command_params: dict[str, Any] = {DreoDirective.AMBIENT_RGB_SPEED: speed}
            await self.async_send_command_and_update(
                DreoErrorCode.TURN_ON_FAILED, **command_params
            )
        else:
            _LOGGER.warning(
                "Light speed can only be set in Circle or Breath mode. Current mode: %s",
                getattr(self.coordinator.data, "rgb_mode", "Unknown"),
            )


class DreoRegularLight(DreoEntity, LightEntity):
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

        light_config = coordinator.model_config.get(
            DreoEntityConfigSpec.LIGHT_ENTITY_CONF, {}
        )
        brightness_percentage = light_config.get(
            DreoFeatureSpec.BRIGHTNESS_PERCENTAGE, [1, 100]
        )
        color_temp_range = light_config.get(
            DreoFeatureSpec.COLOR_TEMPERATURE_RANGE, [1, 100]
        )

        self._brightness_percentage = tuple(brightness_percentage)
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

        if not self.coordinator.data:
            _LOGGER.warning(
                "Expected DreoCeilingFanDeviceData, got %s", type(self.coordinator.data)
            )
            return

        ceiling_fan_data = self.coordinator.data
        self._attr_available = ceiling_fan_data.available

        if (
            hasattr(ceiling_fan_data, DreoDirective.LIGHT_SWITCH)
            and ceiling_fan_data.light_switch is not None
        ):
            self._attr_is_on = ceiling_fan_data.light_switch
        else:
            self._attr_is_on = False

        if (
            hasattr(ceiling_fan_data, DreoDirective.LIGHT_BRIGHTNESS)
            and ceiling_fan_data.brightness is not None
        ):
            brightness_percent = ceiling_fan_data.brightness
            self._attr_brightness = int((brightness_percent / 100) * 255)
        else:
            self._attr_brightness = None

        if (
            hasattr(ceiling_fan_data, DreoDirective.LIGHT_COLOR_TEMP)
            and ceiling_fan_data.colortemp is not None
        ):
            color_temp_percent = ceiling_fan_data.colortemp
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
        command_params: dict[str, Any] = {DreoDirective.LIGHT_SWITCH: True}

        if ATTR_BRIGHTNESS in kwargs:
            brightness_255 = kwargs[ATTR_BRIGHTNESS]
            brightness_percent = max(1, int((brightness_255 / 255) * 100))
            command_params[DreoDirective.LIGHT_BRIGHTNESS] = brightness_percent

        if ATTR_COLOR_TEMP_KELVIN in kwargs:
            kelvin = kwargs[ATTR_COLOR_TEMP_KELVIN]
            kelvin = max(
                self._attr_min_color_temp_kelvin,
                min(self._attr_max_color_temp_kelvin, kelvin),
            )
            temp_range = (
                self._attr_max_color_temp_kelvin - self._attr_min_color_temp_kelvin
            )
            color_temp_percent = (
                (kelvin - self._attr_min_color_temp_kelvin) / temp_range
            ) * 100
            command_params[DreoDirective.LIGHT_COLOR_TEMP] = max(
                1, int(color_temp_percent)
            )

        await self.async_send_command_and_update(
            DreoErrorCode.TURN_ON_FAILED, **command_params
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the light."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_OFF_FAILED, light_switch=False
        )
