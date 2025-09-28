"""Support for Dreo number entities (RGB humidity thresholds)."""

from __future__ import annotations

import contextlib
import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DreoConfigEntry
from .const import DreoDirective, DreoEntityConfigSpec, DreoErrorCode, DreoFeatureSpec
from .coordinator import DreoDataUpdateCoordinator, DreoHumidifierDeviceData
from .entity import DreoEntity
from .status_dependency import DreotStatusDependency

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Dreo number entities from a config entry."""

    @callback
    def async_add_number_entities() -> None:
        numbers: list[DreoRgbThresholdLow | DreoRgbThresholdHigh | DreoSlideNumber] = []

        for device in config_entry.runtime_data.devices:
            device_id = device.get("deviceSn")
            if not device_id:
                continue

            top_config = device.get(DreoEntityConfigSpec.TOP_CONFIG, {})
            has_number_support = Platform.NUMBER in top_config.get(
                DreoEntityConfigSpec.ENTITY_SUPPORTS, []
            )

            if not has_number_support:
                continue

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for device %s", device_id)
                continue

            threshold_config = coordinator.model_config.get(
                DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
            ).get(DreoFeatureSpec.AMBIENT_THRESHOLD, [])

            # Add generic slide components
            number_config = coordinator.model_config.get(
                DreoEntityConfigSpec.NUMBER_ENTITY_CONF, {}
            )
            slide_config = number_config.get(DreoFeatureSpec.SLIDE_COMPONENT)
            if slide_config:
                numbers.append(DreoSlideNumber(device, coordinator))
            elif threshold_config:
                numbers.append(DreoRgbThresholdLow(device, coordinator))
                numbers.append(DreoRgbThresholdHigh(device, coordinator))

        if numbers:
            async_add_entities(numbers)

    async_add_number_entities()


class DreoSlideNumber(DreoEntity, NumberEntity):
    """Generic Dreo slide number entity."""

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the slide number entity."""
        number_config = coordinator.model_config.get(
            DreoEntityConfigSpec.NUMBER_ENTITY_CONF, {}
        )
        slide_component = number_config.get(DreoFeatureSpec.SLIDE_COMPONENT, {})

        attr_name = slide_component.get(DreoFeatureSpec.ATTR_NAME, "Slider")
        super().__init__(device, coordinator, "number", attr_name)

        device_id = device.get("deviceSn")
        directive_name = slide_component.get(DreoFeatureSpec.DIRECTIVE_NAME, "slider")
        self._attr_unique_id = f"{device_id}_{attr_name}"

        self._attr_mode = NumberMode.SLIDER
        self._directive_name = directive_name
        self._state_attr_name = slide_component.get(DreoFeatureSpec.STATE_ATTR_NAME)
        self._status_dependency = DreotStatusDependency(
            slide_component.get(DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, [])
        )

        icon = slide_component.get(DreoFeatureSpec.ATTR_ICON)
        if icon:
            self._attr_icon = icon

        threshold_range = slide_component.get(DreoFeatureSpec.THRESHOLD_RANGE, [0, 100])
        if isinstance(threshold_range, (list, tuple)) and len(threshold_range) >= 2:
            self._attr_native_min_value = float(threshold_range[0])
            self._attr_native_max_value = float(threshold_range[1])
        else:
            self._attr_native_min_value = 0.0
            self._attr_native_max_value = 100.0
        self._attr_native_step = 1.0

    @property
    def available(self) -> bool:
        """Entity is available only if base is available and ambient light is on."""
        if not super().available:
            return False
        return bool(
            getattr(self.coordinator.data, DreoDirective.HUMIDITY_SWITCH, False)
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        if not self.coordinator.data:
            return

        device_state_data = self.coordinator.data
        self._attr_available = device_state_data.available and self._status_dependency(
            device_state_data
        )

        if not self._state_attr_name or not hasattr(
            device_state_data, self._state_attr_name
        ):
            self._attr_native_value = None
            return

        value = getattr(device_state_data, self._state_attr_name, None)
        self._attr_native_value = float(value) if value is not None else None
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        if not self.available:
            return

        clamped_value = max(
            self._attr_native_min_value, min(self._attr_native_max_value, value)
        )

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HUMIDITY_FAILED,
            **{self._directive_name: int(clamped_value)},
        )


class _DreoRgbThresholdBase(DreoEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_value: float | None = None
    _min_value: int = 0
    _max_value: int = 100
    _step_value: int = 1
    _pair_low: int | None = None
    _pair_high: int | None = None

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
        unique_suffix: str,
        name: str,
    ) -> None:
        super().__init__(device, coordinator, "number", name)
        device_id = device.get("deviceSn")
        self._attr_unique_id = f"{device_id}_{unique_suffix}"

        rng = coordinator.model_config.get(
            DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
        ).get(DreoFeatureSpec.AMBIENT_THRESHOLD, [])

        if isinstance(rng, (list, tuple)) and len(rng) >= 2:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(rng[0]), int(rng[1])

    @property
    def native_min_value(self) -> float:
        return float(self._min_value)

    @property
    def native_max_value(self) -> float:
        return float(self._max_value)

    @property
    def native_step(self) -> float:
        return 1.0

    def _parse_rgb_threshold(self, rgb: Any) -> tuple[int | None, int | None]:
        """Parse RGB threshold from device data."""
        with contextlib.suppress(TypeError, ValueError):
            if isinstance(rgb, (list, tuple)) and len(rgb) >= 2:
                return int(rgb[0]), int(rgb[1])
            if isinstance(rgb, str) and "," in rgb:
                parts = rgb.split(",")
                if len(parts) >= 2:
                    return int(parts[0]), int(parts[1])
        return None, None

    def _get_current_threshold(
        self, data: DreoHumidifierDeviceData, index: int
    ) -> int | None:
        """Get current threshold value from data."""
        low, high = self._parse_rgb_threshold(
            getattr(data, DreoDirective.RGB_HUMIDITY_THRESHOLD, None)
        )
        return low if index == 0 else high

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not isinstance(data, DreoHumidifierDeviceData):
            return
        self._attr_available = data.available and bool(
            getattr(data, DreoDirective.AMBIENT_LIGHT_SWITCH, False)
        )
        if self._attr_available:
            low, high = self._parse_rgb_threshold(
                getattr(data, DreoDirective.RGB_HUMIDITY_THRESHOLD, None)
            )
            self._pair_low = low
            self._pair_high = high
            self._sync_from_pair(low, high)
        super()._handle_coordinator_update()

    def _sync_from_pair(self, low: int | None, high: int | None) -> None:
        raise NotImplementedError

    async def _write_pair(self, low: int, high: int) -> None:
        self._pair_low = int(low)
        self._pair_high = int(high)
        value = f"{self._pair_low},{self._pair_high}"
        await self.async_send_command_and_update(
            DreoErrorCode.SET_RGB_THRESHOLD_FAILED,
            **{DreoDirective.RGB_HUMIDITY_THRESHOLD.value: value},
        )

    @property
    def available(self) -> bool:
        """Entity is available only if base is available and ambient light is on."""
        if not super().available:
            return False
        data = self.coordinator.data
        if isinstance(data, DreoHumidifierDeviceData):
            return bool(getattr(data, DreoDirective.AMBIENT_LIGHT_SWITCH, False))
        return True


class DreoRgbThresholdLow(_DreoRgbThresholdBase):
    """Number entity for the low RGB humidity threshold."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the low threshold slider."""
        super().__init__(device, coordinator, "rgb_threshold_low", "HumLight Low")

    def _sync_from_pair(self, low: int | None, high: int | None) -> None:
        """Sync entity value from pair received in coordinator state."""
        if low is None:
            self._attr_native_value = None
            return

        constrained_low = (
            max(self._min_value, high - 5) if high and high - low < 5 else low
        )
        self._attr_native_value = float(constrained_low)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for low threshold and write pair back."""
        if not self._attr_available:
            return

        req_low = max(self._min_value, min(self._max_value, int(value)))
        high_current = self._pair_high
        if high_current is None and isinstance(
            self.coordinator.data, DreoHumidifierDeviceData
        ):
            high_current = self._get_current_threshold(self.coordinator.data, 1)

        clamped_low = min(req_low, high_current - 5) if high_current else req_low
        clamped_low = max(self._min_value, clamped_low)

        self._attr_native_value = float(clamped_low)
        super()._handle_coordinator_update()
        if high_current is not None:
            self.hass.async_create_task(self._write_pair(clamped_low, high_current))


class DreoRgbThresholdHigh(_DreoRgbThresholdBase):
    """Number entity for the high RGB humidity threshold."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the high threshold slider."""
        super().__init__(device, coordinator, "rgb_threshold_high", "HumLight High")

    def _sync_from_pair(self, low: int | None, high: int | None) -> None:
        """Sync entity value from pair received in coordinator state."""
        if high is None:
            self._attr_native_value = None
            return

        constrained_high = (
            min(self._max_value, low + 5) if low and high - low < 5 else high
        )
        self._attr_native_value = float(constrained_high)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for high threshold and write pair back."""
        if not self._attr_available:
            return

        req_high = max(self._min_value, min(self._max_value, int(value)))
        low_current = self._pair_low
        if low_current is None and isinstance(
            self.coordinator.data, DreoHumidifierDeviceData
        ):
            low_current = self._get_current_threshold(self.coordinator.data, 0)

        clamped_high = min(
            self._max_value, max(req_high, low_current + 5) if low_current else req_high
        )

        self._attr_native_value = float(clamped_high)
        super()._handle_coordinator_update()
        if low_current is not None:
            self.hass.async_create_task(self._write_pair(low_current, clamped_high))
