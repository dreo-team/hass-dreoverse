"""Support for Dreo number entities (RGB humidity thresholds)."""

from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import DreoConfigEntry
from .const import DreoDirective, DreoEntityConfigSpec, DreoErrorCode, DreoFeatureSpec
from .coordinator import (
    DreoCirculationFanDeviceData,
    DreoDataUpdateCoordinator,
    DreoHumidifierDeviceData,
)
from .entity import DreoEntity
from .status_dependency import DreotStatusDependency

_LOGGER = logging.getLogger(__name__)
MIN_RANGE_LEN = 2
MIN_SPACING = 5
DIRECTION_COUNT = 4


async def async_setup_entry(  # noqa: PLR0915
    _hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Dreo number entities from a config entry."""

    @callback
    def async_add_number_entities() -> None:  # noqa: PLR0912
        numbers: list[
            DreoRgbThresholdLow
            | DreoRgbThresholdHigh
            | DreoSlideNumber
            | DreoFanPairFixedAngleHorizonal
            | DreoFanPairFixedAngleVertical
            | DreoFanSingleFixedAngleHorizonal
            | DreoFanSingleFixedAngleVertical
            | DreoFanOscRangeUp
            | DreoFanOscRangeRight
            | DreoFanOscRangeDown
            | DreoFanOscRangeLeft
            | DreoFanOscRangeBothHorizontalLeft
            | DreoFanOscRangeBothHorizontalRight
            | DreoFanOscRangeBothVerticalUp
            | DreoFanOscRangeBothVerticalDown
        ] = []

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

            fan_config = coordinator.model_config.get(
                DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
            )

            fan_fixed_angle_config = fan_config.get(DreoFeatureSpec.FIXED_ANGLE, {})

            fan_oscrange = fan_config.get(DreoFeatureSpec.OSCRANGE, {})

            # Add generic slide components
            number_config = coordinator.model_config.get(
                DreoEntityConfigSpec.NUMBER_ENTITY_CONF, {}
            )
            slide_config = number_config.get(DreoFeatureSpec.SLIDE_COMPONENT)
            if slide_config:
                # Support both single slide component and array of slide components
                if isinstance(slide_config, list):
                    numbers.extend(
                        DreoSlideNumber(device, coordinator, slide_component)
                        for slide_component in slide_config
                        if isinstance(slide_component, dict)
                    )
                elif isinstance(slide_config, dict):
                    numbers.append(DreoSlideNumber(device, coordinator, slide_config))
            if threshold_config:
                numbers.append(DreoRgbThresholdLow(device, coordinator))
                numbers.append(DreoRgbThresholdHigh(device, coordinator))

            if fan_fixed_angle_config:
                if fan_fixed_angle_config.get("mode") == "pair":
                    numbers.append(DreoFanPairFixedAngleHorizonal(device, coordinator))
                    numbers.append(DreoFanPairFixedAngleVertical(device, coordinator))
                elif fan_fixed_angle_config.get("mode") == "single":
                    if fan_fixed_angle_config.get("horizontal"):
                        numbers.append(
                            DreoFanSingleFixedAngleHorizonal(device, coordinator)
                        )
                    if fan_fixed_angle_config.get("vertical"):
                        numbers.append(
                            DreoFanSingleFixedAngleVertical(device, coordinator)
                        )

            if fan_oscrange:
                if fan_oscrange.get("mode") == "all":
                    numbers.append(DreoFanOscRangeUp(device, coordinator))
                    numbers.append(DreoFanOscRangeDown(device, coordinator))
                    numbers.append(DreoFanOscRangeLeft(device, coordinator))
                    numbers.append(DreoFanOscRangeRight(device, coordinator))
                elif fan_oscrange.get("mode") == "both":
                    if fan_oscrange.get("horizontal"):
                        numbers.append(
                            DreoFanOscRangeBothHorizontalLeft(device, coordinator)
                        )
                        numbers.append(
                            DreoFanOscRangeBothHorizontalRight(device, coordinator)
                        )
                    if fan_oscrange.get("vertical"):
                        numbers.append(
                            DreoFanOscRangeBothVerticalUp(device, coordinator)
                        )
                        numbers.append(
                            DreoFanOscRangeBothVerticalDown(device, coordinator)
                        )

        if numbers:
            async_add_entities(numbers)

    async_add_number_entities()


class DreoSlideNumber(DreoEntity, NumberEntity):
    """Generic Dreo slide number entity."""

    _data_range: tuple[float, float] | None = None

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
        slide_component: dict[str, Any] | None = None,
    ) -> None:
        """Initialize the slide number entity."""
        if slide_component is None:
            number_config = coordinator.model_config.get(
                DreoEntityConfigSpec.NUMBER_ENTITY_CONF, {}
            )
            slide_component = number_config.get(DreoFeatureSpec.SLIDE_COMPONENT, {})

        # Ensure slide_component is a dict
        if not isinstance(slide_component, dict):
            slide_component = {}

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
        if (
            isinstance(threshold_range, list | tuple)
            and len(threshold_range) >= MIN_RANGE_LEN
        ):
            self._attr_native_min_value = float(threshold_range[0])
            self._attr_native_max_value = float(threshold_range[1])
            self._threshold_range = (
                float(threshold_range[0]),
                float(threshold_range[1]),
            )
        else:
            self._attr_native_min_value = 0.0
            self._attr_native_max_value = 100.0
            self._threshold_range = (0.0, 100.0)

        # Get data_range for value mapping
        data_range = slide_component.get(DreoFeatureSpec.DATA_RANGE)
        if isinstance(data_range, list | tuple) and len(data_range) >= MIN_RANGE_LEN:
            self._data_range = (float(data_range[0]), float(data_range[1]))
        else:
            # If no data_range, use threshold_range as data_range (no mapping)
            self._data_range = None

        self._attr_native_step = 1.0

    def _map_threshold_to_data(self, threshold_value: float) -> float:
        """Map threshold_range value to data_range value."""
        if self._data_range is None:
            return threshold_value

        threshold_min, threshold_max = self._threshold_range
        data_min, data_max = self._data_range

        # Handle division by zero
        if threshold_max == threshold_min:
            return data_min

        # Calculate the ratio in threshold_range
        ratio = (threshold_value - threshold_min) / (threshold_max - threshold_min)

        # Map to data_range (supports both ascending and descending)
        if data_min < data_max:
            # Ascending: data_min -> data_max
            return data_min + ratio * (data_max - data_min)
        # Descending: data_min -> data_max (data_min > data_max)
        return data_min - ratio * (data_min - data_max)

    def _map_data_to_threshold(self, data_value: float) -> float:
        """Map data_range value to threshold_range value."""
        if self._data_range is None:
            return data_value

        threshold_min, threshold_max = self._threshold_range
        data_min, data_max = self._data_range

        # Handle division by zero
        if data_min == data_max:
            return threshold_min

        # Calculate the ratio in data_range
        if data_min < data_max:
            # Ascending: data_min -> data_max
            ratio = (data_value - data_min) / (data_max - data_min)
        else:
            # Descending: data_min -> data_max (data_min > data_max)
            ratio = (data_min - data_value) / (data_min - data_max)

        # Map to threshold_range
        return threshold_min + ratio * (threshold_max - threshold_min)

    @property
    def available(self) -> bool:
        """Entity is available based on status dependency configuration."""
        if not super().available:
            return False
        data = self.coordinator.data
        if not data:
            return False
        return self._status_dependency(data)

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
        if value is not None:
            data_value = float(value)
            # Map from data_range to threshold_range for UI display
            threshold_value = self._map_data_to_threshold(data_value)
            self._attr_native_value = threshold_value
        else:
            self._attr_native_value = None
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Set new value."""
        if not self.available:
            return

        clamped_value = max(
            self._attr_native_min_value, min(self._attr_native_max_value, value)
        )

        # Map from threshold_range to data_range for device command
        data_value = self._map_threshold_to_data(clamped_value)

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HUMIDITY_FAILED,
            **{self._directive_name: int(data_value)},
        )


class _DreoRgbThresholdBase(DreoEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_value: float | None = None
    _min_value: int = 0
    _max_value: int = 100
    _step_value: int = 1
    _pair_low: int | None = None
    _pair_high: int | None = None
    _status_dependency: DreotStatusDependency

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

        humidifier_config = coordinator.model_config.get(
            DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
        )
        rng = humidifier_config.get(DreoFeatureSpec.AMBIENT_THRESHOLD, [])

        if isinstance(rng, list | tuple) and len(rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(rng[0]), int(rng[1])

        # Get status dependency from config.
        # If not configured, use default dependency to check rgb_state for
        # compatibility.
        status_dependencies = humidifier_config.get(
            DreoFeatureSpec.AMBIENT_STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

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
            if isinstance(rgb, list | tuple) and len(rgb) >= MIN_RANGE_LEN:
                return int(rgb[0]), int(rgb[1])
            if isinstance(rgb, str) and "," in rgb:
                parts = rgb.split(",")
                if len(parts) >= MIN_RANGE_LEN:
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
        available_depend = self._status_dependency(data)
        self._attr_available = data.available and available_depend
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
        """Entity is available based on status dependency configuration."""
        if not super().available:
            return False
        data = self.coordinator.data
        if not data:
            return False
        return self._status_dependency(data)


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
            max(self._min_value, high - MIN_SPACING)
            if high and high - low < MIN_SPACING
            else low
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

        clamped_low = (
            min(req_low, high_current - MIN_SPACING) if high_current else req_low
        )
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
            min(self._max_value, low + MIN_SPACING)
            if low and high - low < MIN_SPACING
            else high
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
            self._max_value,
            max(req_high, low_current + MIN_SPACING) if low_current else req_high,
        )

        self._attr_native_value = float(clamped_high)
        super()._handle_coordinator_update()
        if low_current is not None:
            self.hass.async_create_task(self._write_pair(low_current, clamped_high))


class _DreoFanPairFixedAngleBase(DreoEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_value: float | None = None
    _min_value: int = -180
    _max_value: int = 180
    _step_value: int = 1
    _pair_horizontal: int | None = None
    _pair_vertical: int | None = None
    _status_dependency: DreotStatusDependency
    _fixed_directive_name: str

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

        # Get oscangle directive name from config (common for all subclasses)
        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        fixed_angle_config = fan_entity_config.get(DreoFeatureSpec.FIXED_ANGLE, {})
        self._fixed_directive_name = fixed_angle_config.get(
            "directive_name", DreoDirective.FIXED_ANGLE.value
        )

    @property
    def native_min_value(self) -> float:
        return float(self._min_value)

    @property
    def native_max_value(self) -> float:
        return float(self._max_value)

    @property
    def native_step(self) -> float:
        return float(self._step_value)

    def _parse_fan_angle(self, angle: Any) -> tuple[int | None, int | None]:
        """Parse fan angle from device data."""
        if not isinstance(angle, dict):
            return None, None

        vertical = angle.get("V")
        horizontal = angle.get("H")
        if vertical is not None:
            vertical = int(vertical)
        if horizontal is not None:
            horizontal = int(horizontal)
        return vertical, horizontal

    def _get_current_angle(self, data: Any, index: int) -> int | None:
        """Get current angle value from data."""
        vertical, horizontal = self._parse_fan_angle(
            getattr(data, self._fixed_directive_name, None)
        )
        return horizontal if index == 0 else vertical

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not data:
            return
        available_depend = self._status_dependency(data)
        self._attr_available = data.available and available_depend
        if self._attr_available:
            vertical, horizontal = self._parse_fan_angle(
                getattr(data, self._fixed_directive_name, None)
            )
            self._pair_horizontal = horizontal
            self._pair_vertical = vertical
            self._sync_from_pair(horizontal, vertical)
        super()._handle_coordinator_update()

    def _sync_from_pair(self, horizontal: int | None, _vertical: int | None) -> None:
        raise NotImplementedError

    async def _write_pair(self, horizontal: int, vertical: int) -> None:
        self._pair_horizontal = int(horizontal)
        self._pair_vertical = int(vertical)
        value = {"V": self._pair_vertical, "H": self._pair_horizontal}
        await self.async_send_command_and_update(
            DreoErrorCode.SET_FIXED_ANGLE_FAILED,
            **{self._fixed_directive_name: value},
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


class DreoFanPairFixedAngleHorizonal(_DreoFanPairFixedAngleBase):
    """Number entity for the horizontal fan angle."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the horizontal angle slider."""
        super().__init__(
            device, coordinator, "fan_angle_horizontal", "Fan Angle Horizontal"
        )

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        fixed_angle_config = fan_entity_config.get(DreoFeatureSpec.FIXED_ANGLE, {}).get(
            "horizontal", {}
        )

        # Get status dependency from config
        status_dependencies = fixed_angle_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from config
        step_value = fixed_angle_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get horizontal angle range from config
        hor_rng = fixed_angle_config.get("range", [])

        if isinstance(hor_rng, list | tuple) and len(hor_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(hor_rng[0]), int(hor_rng[1])

    def _sync_from_pair(self, horizontal: int | None, _vertical: int | None) -> None:
        """Sync entity value from pair received in coordinator state."""
        if horizontal is None:
            self._attr_native_value = None
            return

        self._attr_native_value = float(horizontal)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for horizontal angle and write pair back."""
        if not self._attr_available:
            return

        req_horizontal = max(self._min_value, min(self._max_value, int(value)))
        vertical_current = self._pair_vertical
        if vertical_current is None and isinstance(
            self.coordinator.data, DreoCirculationFanDeviceData
        ):
            vertical_current = self._get_current_angle(self.coordinator.data, 1)

        self._attr_native_value = float(req_horizontal)
        super()._handle_coordinator_update()
        if vertical_current is not None:
            self.hass.async_create_task(
                self._write_pair(req_horizontal, vertical_current)
            )


class DreoFanPairFixedAngleVertical(_DreoFanPairFixedAngleBase):
    """Number entity for the vertical fan angle."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the vertical angle slider."""
        super().__init__(
            device, coordinator, "fan_angle_vertical", "Fan Angle Vertical"
        )

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        fixed_angle_config = fan_entity_config.get(DreoFeatureSpec.FIXED_ANGLE, {}).get(
            "vertical", {}
        )

        # Get status dependency from config
        status_dependencies = fixed_angle_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from config
        step_value = fixed_angle_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get vertical angle range from config
        ver_rng = fixed_angle_config.get("range", [])

        if isinstance(ver_rng, list | tuple) and len(ver_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(ver_rng[0]), int(ver_rng[1])

    def _sync_from_pair(self, _horizontal: int | None, vertical: int | None) -> None:
        """Sync entity value from pair received in coordinator state."""
        if vertical is None:
            self._attr_native_value = None
            return

        self._attr_native_value = float(vertical)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for vertical angle and write pair back."""
        if not self._attr_available:
            return

        req_vertical = max(self._min_value, min(self._max_value, int(value)))
        horizontal_current = self._pair_horizontal
        if horizontal_current is None and isinstance(
            self.coordinator.data, DreoCirculationFanDeviceData
        ):
            horizontal_current = self._get_current_angle(self.coordinator.data, 0)

        self._attr_native_value = float(req_vertical)
        super()._handle_coordinator_update()
        if horizontal_current is not None:
            self.hass.async_create_task(
                self._write_pair(horizontal_current, req_vertical)
            )


class _DreoFanSingleFixedAngleBase(DreoEntity, NumberEntity):
    _attr_mode = NumberMode.SLIDER
    _attr_native_value: float | None = None
    _min_value: int = -180
    _max_value: int = 180
    _step_value: int = 1
    _status_dependency: DreotStatusDependency
    _fixed_directive_name: str
    _angle_key: str  # "H" for horizontal, "V" for vertical

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

    @property
    def native_min_value(self) -> float:
        return float(self._min_value)

    @property
    def native_max_value(self) -> float:
        return float(self._max_value)

    @property
    def native_step(self) -> float:
        return float(self._step_value)

    def _get_current_angle(self, data: Any) -> int | None:
        """Get current angle value from data."""
        value = getattr(data, self._fixed_directive_name, None)
        if value is None:
            return None
        # value is a dict, extract the angle using the key (H or V)
        angle_value = value.get(self._angle_key)
        if angle_value is None:
            return None
        return int(angle_value)

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not data:
            return
        available_depend = self._status_dependency(data)
        self._attr_available = data.available and available_depend
        if self._attr_available:
            current_value = self._get_current_angle(data)
            self._sync_from_single(current_value)
        super()._handle_coordinator_update()

    def _sync_from_single(self, value: int | None) -> None:
        """Sync entity value from single value received in coordinator state."""
        raise NotImplementedError

    async def _write_single(self, value: int, key: str) -> None:
        """Write single angle value (not paired)."""
        value_dict = {key: int(value)}
        await self.async_send_command_and_update(
            DreoErrorCode.SET_FIXED_ANGLE_FAILED,
            **{self._fixed_directive_name: value_dict},
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


class DreoFanSingleFixedAngleHorizonal(_DreoFanSingleFixedAngleBase):
    """Number entity for the horizontal fan angle."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the horizontal angle slider."""
        super().__init__(
            device, coordinator, "fan_angle_horizontal", "Fan Angle Horizontal"
        )
        self._angle_key = "H"

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        fixed_angle_config = fan_entity_config.get(DreoFeatureSpec.FIXED_ANGLE, {}).get(
            "horizontal", {}
        )

        # Get oscangle directive name from horizontal config
        self._fixed_directive_name = fixed_angle_config.get(
            "directive_name", DreoDirective.FIXED_ANGLE.value
        )

        # Get status dependency from config
        status_dependencies = fixed_angle_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from config
        step_value = fixed_angle_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get horizontal angle range from config
        hor_rng = fixed_angle_config.get("range", [])

        if isinstance(hor_rng, list | tuple) and len(hor_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(hor_rng[0]), int(hor_rng[1])

    def _sync_from_single(self, value: int | None) -> None:
        """Sync entity value from single value received in coordinator state."""
        if value is None:
            self._attr_native_value = None
            return

        self._attr_native_value = float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for horizontal angle and write single value."""
        if not self._attr_available:
            return

        req_horizontal = max(self._min_value, min(self._max_value, int(value)))
        self._attr_native_value = float(req_horizontal)
        super()._handle_coordinator_update()
        await self._write_single(req_horizontal, "H")


class DreoFanSingleFixedAngleVertical(_DreoFanSingleFixedAngleBase):
    """Number entity for the vertical fan angle."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the vertical angle slider."""
        super().__init__(
            device, coordinator, "fan_angle_vertical", "Fan Angle Vertical"
        )
        self._angle_key = "V"

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        fixed_angle_config = fan_entity_config.get(DreoFeatureSpec.FIXED_ANGLE, {}).get(
            "vertical", {}
        )

        # Get oscangle directive name from vertical config
        self._fixed_directive_name = fixed_angle_config.get(
            "directive_name", DreoDirective.FIXED_ANGLE.value
        )

        # Get status dependency from config
        status_dependencies = fixed_angle_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from config
        step_value = fixed_angle_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get vertical angle range from config
        ver_rng = fixed_angle_config.get("range", [])

        if isinstance(ver_rng, list | tuple) and len(ver_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(ver_rng[0]), int(ver_rng[1])

    def _sync_from_single(self, value: int | None) -> None:
        """Sync entity value from single value received in coordinator state."""
        if value is None:
            self._attr_native_value = None
            return

        self._attr_native_value = float(value)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for vertical angle and write single value."""
        if not self._attr_available:
            return

        req_vertical = max(self._min_value, min(self._max_value, int(value)))
        self._attr_native_value = float(req_vertical)
        super()._handle_coordinator_update()
        await self._write_single(req_vertical, "V")


class _DreoFanOscRangeAllBase(DreoEntity, NumberEntity):
    """Base class for oscillation range entities in 'all' mode (U,R,D,L format)."""

    _attr_mode = NumberMode.SLIDER
    _attr_native_value: float | None = None
    _min_value: int = -180
    _max_value: int = 180
    _step_value: int = 1
    _up: int | None = None
    _right: int | None = None
    _down: int | None = None
    _left: int | None = None
    _status_dependency: DreotStatusDependency
    _oscrange_directive_name: str
    _vertical_spacing: int = 0
    _horizontal_spacing: int = 0

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

        # Get oscrange directive name from config
        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {})
        self._oscrange_directive_name = oscrange_config.get(
            "directive_name", DreoDirective.OSCRANGE.value
        )

        # Get spacing values from config
        self._vertical_spacing = int(oscrange_config.get("vertical_spacing", 0))
        self._horizontal_spacing = int(oscrange_config.get("horizontal_spacing", 0))

    @property
    def native_min_value(self) -> float:
        return float(self._min_value)

    @property
    def native_max_value(self) -> float:
        return float(self._max_value)

    @property
    def native_step(self) -> float:
        return float(self._step_value)

    def _parse_oscrange(
        self, value: Any
    ) -> tuple[int | None, int | None, int | None, int | None]:
        """Parse oscillation range from device data (U,R,D,L format)."""
        if not isinstance(value, dict):
            return None, None, None, None

        up = value.get("U")
        right = value.get("R")
        down = value.get("D")
        left = value.get("L")
        if up is not None:
            up = int(up)
        if right is not None:
            right = int(right)
        if down is not None:
            down = int(down)
        if left is not None:
            left = int(left)
        return up, right, down, left

    def _get_current_value(self, data: Any, index: int) -> int | None:
        """Get current value from data based on index (0=U, 1=R, 2=D, 3=L)."""
        up, right, down, left = self._parse_oscrange(
            getattr(data, self._oscrange_directive_name, None)
        )
        values = [up, right, down, left]
        return values[index] if 0 <= index < DIRECTION_COUNT else None

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not data:
            return
        available_depend = self._status_dependency(data)
        self._attr_available = data.available and available_depend
        if self._attr_available:
            up, right, down, left = self._parse_oscrange(
                getattr(data, self._oscrange_directive_name, None)
            )
            self._up = up
            self._right = right
            self._down = down
            self._left = left
            self._sync_from_all(up, right, down, left)
        super()._handle_coordinator_update()

    def _sync_from_all(
        self,
        up: int | None,
        _right: int | None,
        _down: int | None,
        _left: int | None,
    ) -> None:
        """Sync entity value from all values received in coordinator state."""
        raise NotImplementedError

    async def _write_all(self, up: int, right: int, down: int, left: int) -> None:
        """Write all oscillation range values (U,R,D,L format)."""
        self._up = int(up)
        self._right = int(right)
        self._down = int(down)
        self._left = int(left)
        value = {"U": self._up, "R": self._right, "D": self._down, "L": self._left}
        await self.async_send_command_and_update(
            DreoErrorCode.SET_FIXED_ANGLE_FAILED,
            **{self._oscrange_directive_name: value},
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


class DreoFanOscRangeUp(_DreoFanOscRangeAllBase):
    """Number entity for the up oscillation range."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the up range slider."""
        super().__init__(device, coordinator, "fan_oscrange_up", "Fan Osc Range Up")

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {})
        up_config = oscrange_config.get("up", {})

        # Get status dependency from up config
        status_dependencies = up_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from up config
        step_value = up_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get up range from config
        up_rng = up_config.get("range", [])
        if isinstance(up_rng, list | tuple) and len(up_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(up_rng[0]), int(up_rng[1])

    def _sync_from_all(
        self,
        up: int | None,
        _right: int | None,
        _down: int | None,
        _left: int | None,
    ) -> None:
        """Sync entity value from all values."""
        if up is None:
            self._attr_native_value = None
            return
        self._attr_native_value = float(up)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for up range and write all back."""
        if not self._attr_available:
            return

        req_up = max(self._min_value, min(self._max_value, int(value)))
        right_current = self._right
        down_current = self._down
        left_current = self._left
        if (
            right_current is None or down_current is None or left_current is None
        ) and self.coordinator.data:
            if right_current is None:
                right_current = self._get_current_value(self.coordinator.data, 1)
            if down_current is None:
                down_current = self._get_current_value(self.coordinator.data, 2)
            if left_current is None:
                left_current = self._get_current_value(self.coordinator.data, 3)

        # Limit up value to ensure vertical spacing: up - down >= vertical spacing.
        if down_current is not None:
            min_up = down_current + self._vertical_spacing
            req_up = max(req_up, min_up)

        self._attr_native_value = float(req_up)
        super()._handle_coordinator_update()
        if (
            right_current is not None
            and down_current is not None
            and left_current is not None
        ):
            self.hass.async_create_task(
                self._write_all(req_up, right_current, down_current, left_current)
            )


class DreoFanOscRangeRight(_DreoFanOscRangeAllBase):
    """Number entity for the right oscillation range."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the right range slider."""
        super().__init__(
            device, coordinator, "fan_oscrange_right", "Fan Osc Range Right"
        )

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {})
        right_config = oscrange_config.get("right", {})

        # Get status dependency from right config
        status_dependencies = right_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from right config
        step_value = right_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get right range from config
        right_rng = right_config.get("range", [])
        if isinstance(right_rng, list | tuple) and len(right_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(right_rng[0]), int(right_rng[1])

    def _sync_from_all(
        self,
        _up: int | None,
        right: int | None,
        _down: int | None,
        _left: int | None,
    ) -> None:
        """Sync entity value from all values."""
        if right is None:
            self._attr_native_value = None
            return
        self._attr_native_value = float(right)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for right range and write all back."""
        if not self._attr_available:
            return

        req_right = max(self._min_value, min(self._max_value, int(value)))
        up_current = self._up
        down_current = self._down
        left_current = self._left
        if (
            up_current is None or down_current is None or left_current is None
        ) and self.coordinator.data:
            if up_current is None:
                up_current = self._get_current_value(self.coordinator.data, 0)
            if down_current is None:
                down_current = self._get_current_value(self.coordinator.data, 2)
            if left_current is None:
                left_current = self._get_current_value(self.coordinator.data, 3)

        # Limit right value to ensure horizontal spacing: right - left >= spacing.
        if left_current is not None:
            min_right = left_current + self._horizontal_spacing
            req_right = max(req_right, min_right)

        self._attr_native_value = float(req_right)
        super()._handle_coordinator_update()
        if (
            up_current is not None
            and down_current is not None
            and left_current is not None
        ):
            self.hass.async_create_task(
                self._write_all(up_current, req_right, down_current, left_current)
            )


class DreoFanOscRangeDown(_DreoFanOscRangeAllBase):
    """Number entity for the down oscillation range."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the down range slider."""
        super().__init__(device, coordinator, "fan_oscrange_down", "Fan Osc Range Down")

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {})
        down_config = oscrange_config.get("down", {})

        # Get status dependency from down config
        status_dependencies = down_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from down config
        step_value = down_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get down range from config
        down_rng = down_config.get("range", [])
        if isinstance(down_rng, list | tuple) and len(down_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(down_rng[0]), int(down_rng[1])

    def _sync_from_all(
        self,
        _up: int | None,
        _right: int | None,
        down: int | None,
        _left: int | None,
    ) -> None:
        """Sync entity value from all values."""
        if down is None:
            self._attr_native_value = None
            return
        self._attr_native_value = float(down)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for down range and write all back."""
        if not self._attr_available:
            return

        req_down = max(self._min_value, min(self._max_value, int(value)))
        up_current = self._up
        right_current = self._right
        left_current = self._left
        if (
            up_current is None or right_current is None or left_current is None
        ) and self.coordinator.data:
            if up_current is None:
                up_current = self._get_current_value(self.coordinator.data, 0)
            if right_current is None:
                right_current = self._get_current_value(self.coordinator.data, 1)
            if left_current is None:
                left_current = self._get_current_value(self.coordinator.data, 3)

        # Limit down value to ensure vertical spacing: up - down >= spacing.
        if up_current is not None:
            max_down = up_current - self._vertical_spacing
            req_down = min(req_down, max_down)

        self._attr_native_value = float(req_down)
        super()._handle_coordinator_update()
        if (
            up_current is not None
            and right_current is not None
            and left_current is not None
        ):
            self.hass.async_create_task(
                self._write_all(up_current, right_current, req_down, left_current)
            )


class DreoFanOscRangeLeft(_DreoFanOscRangeAllBase):
    """Number entity for the left oscillation range."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the left range slider."""
        super().__init__(device, coordinator, "fan_oscrange_left", "Fan Osc Range Left")

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {})
        left_config = oscrange_config.get("left", {})

        # Get status dependency from left config
        status_dependencies = left_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from left config
        step_value = left_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get left range from config
        left_rng = left_config.get("range", [])
        if isinstance(left_rng, list | tuple) and len(left_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(left_rng[0]), int(left_rng[1])

    def _sync_from_all(
        self,
        _up: int | None,
        _right: int | None,
        _down: int | None,
        left: int | None,
    ) -> None:
        """Sync entity value from all values."""
        if left is None:
            self._attr_native_value = None
            return
        self._attr_native_value = float(left)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for left range and write all back."""
        if not self._attr_available:
            return

        req_left = max(self._min_value, min(self._max_value, int(value)))
        up_current = self._up
        right_current = self._right
        down_current = self._down
        if (
            up_current is None or right_current is None or down_current is None
        ) and self.coordinator.data:
            if up_current is None:
                up_current = self._get_current_value(self.coordinator.data, 0)
            if right_current is None:
                right_current = self._get_current_value(self.coordinator.data, 1)
            if down_current is None:
                down_current = self._get_current_value(self.coordinator.data, 2)

        # Limit left value to ensure horizontal spacing: right - left >= spacing.
        if right_current is not None:
            max_left = right_current - self._horizontal_spacing
            req_left = min(req_left, max_left)

        self._attr_native_value = float(req_left)
        super()._handle_coordinator_update()
        if (
            up_current is not None
            and right_current is not None
            and down_current is not None
        ):
            self.hass.async_create_task(
                self._write_all(up_current, right_current, down_current, req_left)
            )


class _DreoFanOscRangeBothBase(DreoEntity, NumberEntity):
    """Base class for oscillation range entities in 'both' mode."""

    _attr_mode = NumberMode.SLIDER
    _attr_native_value: float | None = None
    _min_value: int = -180
    _max_value: int = 180
    _step_value: int = 1
    _status_dependency: DreotStatusDependency
    _oscrange_directive_name: str
    _vertical_spacing: int = 0
    _horizontal_spacing: int = 0

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

        # Get oscrange directive name from config
        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {})
        # Get spacing values from config
        self._vertical_spacing = int(oscrange_config.get("vertical_spacing", 0))
        self._horizontal_spacing = int(oscrange_config.get("horizontal_spacing", 0))

    @property
    def native_min_value(self) -> float:
        return float(self._min_value)

    @property
    def native_max_value(self) -> float:
        return float(self._max_value)

    @property
    def native_step(self) -> float:
        return float(self._step_value)

    def _parse_oscrange_pair(self, value: Any) -> tuple[int | None, int | None]:
        """Parse oscillation range pair from device data."""
        if not isinstance(value, dict):
            return None, None

        # Check for horizontal format (L, R)
        if "L" in value or "R" in value:
            left = value.get("L")
            right = value.get("R")
            if left is not None:
                left = int(left)
            if right is not None:
                right = int(right)
            return left, right

        # Check for vertical format (U, D)
        if "U" in value or "D" in value:
            up = value.get("U")
            down = value.get("D")
            if up is not None:
                up = int(up)
            if down is not None:
                down = int(down)
            return up, down

        return None, None

    def _apply_horizontal_spacing(
        self, left: int | None, right: int | None
    ) -> tuple[int | None, int | None]:
        """Apply horizontal spacing constraint to left and right values."""
        if left is None or right is None:
            return left, right

        # Ensure right - left >= horizontal_spacing
        if right - left < self._horizontal_spacing:
            # Adjust to meet spacing requirement
            # Prefer adjusting the value that's being updated
            # For now, adjust left to ensure spacing
            left = right - self._horizontal_spacing

        return left, right

    def _apply_vertical_spacing(
        self, up: int | None, down: int | None
    ) -> tuple[int | None, int | None]:
        """Apply vertical spacing constraint to up and down values."""
        if up is None or down is None:
            return up, down

        # Ensure up - down >= vertical_spacing
        if up - down < self._vertical_spacing:
            # Adjust to meet spacing requirement
            # Prefer adjusting the value that's being updated
            # For now, adjust down to ensure spacing
            down = up - self._vertical_spacing

        return up, down

    @property
    def available(self) -> bool:
        """Entity is available based on status dependency configuration."""
        if not super().available:
            return False
        data = self.coordinator.data
        if not data:
            return False
        return self._status_dependency(data)


class DreoFanOscRangeBothHorizontalLeft(_DreoFanOscRangeBothBase):
    """Number entity for the left oscillation range in horizontal mode."""

    _left: int | None = None
    _right: int | None = None

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the left range slider."""
        super().__init__(
            device,
            coordinator,
            "fan_oscrange_horizontal_left",
            "Fan Osc Range Horizontal Left",
        )

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {}).get(
            "horizontal", {}
        )

        # Get oscrange directive name from horizontal config
        self._oscrange_directive_name = oscrange_config.get(
            "directive_name", DreoDirective.OSCRANGE.value
        )

        # Get left config
        left_config = oscrange_config.get("left", {})

        # Get status dependency from left config
        status_dependencies = left_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from left config
        step_value = left_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get left range from left config
        left_rng = left_config.get("range", [])
        if isinstance(left_rng, list | tuple) and len(left_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(left_rng[0]), int(left_rng[1])

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not data:
            return
        available_depend = self._status_dependency(data)
        self._attr_available = data.available and available_depend
        if self._attr_available:
            left, right = self._parse_oscrange_pair(
                getattr(data, self._oscrange_directive_name, None)
            )
            # Apply horizontal spacing constraint
            left, right = self._apply_horizontal_spacing(left, right)
            self._left = left
            self._right = right
            if left is None:
                self._attr_native_value = None
            else:
                self._attr_native_value = float(left)
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for left range and write pair back."""
        if not self._attr_available:
            return

        req_left = max(self._min_value, min(self._max_value, int(value)))
        right_current = self._right
        if right_current is None and self.coordinator.data:
            _, right_current = self._parse_oscrange_pair(
                getattr(self.coordinator.data, self._oscrange_directive_name, None)
            )

        # Limit left value to ensure horizontal spacing: right - left >= spacing.
        if right_current is not None:
            max_left = right_current - self._horizontal_spacing
            req_left = min(req_left, max_left)

        self._attr_native_value = float(req_left)
        super()._handle_coordinator_update()
        if right_current is not None:
            value_dict = {"L": req_left, "R": right_current}
            await self.async_send_command_and_update(
                DreoErrorCode.SET_FIXED_ANGLE_FAILED,
                **{self._oscrange_directive_name: value_dict},
            )


class DreoFanOscRangeBothHorizontalRight(_DreoFanOscRangeBothBase):
    """Number entity for the right oscillation range in horizontal mode."""

    _left: int | None = None
    _right: int | None = None

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the right range slider."""
        super().__init__(
            device,
            coordinator,
            "fan_oscrange_horizontal_right",
            "Fan Osc Range Horizontal Right",
        )

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {}).get(
            "horizontal", {}
        )

        # Get oscrange directive name from horizontal config
        self._oscrange_directive_name = oscrange_config.get(
            "directive_name", "oscrange"
        )

        # Get right config
        right_config = oscrange_config.get("right", {})

        # Get status dependency from right config
        status_dependencies = right_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from right config
        step_value = right_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get right range from right config
        right_rng = right_config.get("range", [])
        if isinstance(right_rng, list | tuple) and len(right_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(right_rng[0]), int(right_rng[1])

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not data:
            return
        available_depend = self._status_dependency(data)
        self._attr_available = data.available and available_depend
        if self._attr_available:
            left, right = self._parse_oscrange_pair(
                getattr(data, self._oscrange_directive_name, None)
            )
            # Apply horizontal spacing constraint
            left, right = self._apply_horizontal_spacing(left, right)
            self._left = left
            self._right = right
            if right is None:
                self._attr_native_value = None
            else:
                self._attr_native_value = float(right)
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for right range and write pair back."""
        if not self._attr_available:
            return

        req_right = max(self._min_value, min(self._max_value, int(value)))
        left_current = self._left
        if left_current is None and self.coordinator.data:
            left_current, _ = self._parse_oscrange_pair(
                getattr(self.coordinator.data, self._oscrange_directive_name, None)
            )

        # Limit right value to ensure horizontal spacing: right - left >= spacing.
        if left_current is not None:
            min_right = left_current + self._horizontal_spacing
            req_right = max(req_right, min_right)

        self._attr_native_value = float(req_right)
        super()._handle_coordinator_update()
        if left_current is not None:
            value_dict = {"L": left_current, "R": req_right}
            await self.async_send_command_and_update(
                DreoErrorCode.SET_FIXED_ANGLE_FAILED,
                **{self._oscrange_directive_name: value_dict},
            )


class DreoFanOscRangeBothVerticalUp(_DreoFanOscRangeBothBase):
    """Number entity for the up oscillation range in vertical mode."""

    _up: int | None = None
    _down: int | None = None

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the up range slider."""
        super().__init__(
            device, coordinator, "fan_oscrange_vertical_up", "Fan Osc Range Vertical Up"
        )

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {}).get(
            "vertical", {}
        )

        # Get oscrange directive name from vertical config
        self._oscrange_directive_name = oscrange_config.get(
            "directive_name", "oscrange"
        )

        # Get up config
        up_config = oscrange_config.get("up", {})

        # Get status dependency from up config
        status_dependencies = up_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from up config
        step_value = up_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get up range from up config
        up_rng = up_config.get("range", [])
        if isinstance(up_rng, list | tuple) and len(up_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(up_rng[0]), int(up_rng[1])

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not data:
            return
        available_depend = self._status_dependency(data)
        self._attr_available = data.available and available_depend
        if self._attr_available:
            up, down = self._parse_oscrange_pair(
                getattr(data, self._oscrange_directive_name, None)
            )
            # Apply vertical spacing constraint
            up, down = self._apply_vertical_spacing(up, down)
            self._up = up
            self._down = down
            if up is None:
                self._attr_native_value = None
            else:
                self._attr_native_value = float(up)
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for up range and write pair back."""
        if not self._attr_available:
            return

        req_up = max(self._min_value, min(self._max_value, int(value)))
        down_current = self._down
        if down_current is None and self.coordinator.data:
            _, down_current = self._parse_oscrange_pair(
                getattr(self.coordinator.data, self._oscrange_directive_name, None)
            )

        # Limit up value to ensure vertical spacing: up - down >= spacing.
        if down_current is not None:
            min_up = down_current + self._vertical_spacing
            req_up = max(req_up, min_up)

        self._attr_native_value = float(req_up)
        super()._handle_coordinator_update()
        if down_current is not None:
            value_dict = {"U": req_up, "D": down_current}
            await self.async_send_command_and_update(
                DreoErrorCode.SET_FIXED_ANGLE_FAILED,
                **{self._oscrange_directive_name: value_dict},
            )


class DreoFanOscRangeBothVerticalDown(_DreoFanOscRangeBothBase):
    """Number entity for the down oscillation range in vertical mode."""

    _up: int | None = None
    _down: int | None = None

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the down range slider."""
        super().__init__(
            device,
            coordinator,
            "fan_oscrange_vertical_down",
            "Fan Osc Range Vertical Down",
        )

        fan_entity_config = coordinator.model_config.get(
            DreoEntityConfigSpec.FAN_ENTITY_CONF, {}
        )
        oscrange_config = fan_entity_config.get(DreoFeatureSpec.OSCRANGE, {}).get(
            "vertical", {}
        )

        # Get oscrange directive name from vertical config
        self._oscrange_directive_name = oscrange_config.get(
            "directive_name", "oscrange"
        )

        # Get down config
        down_config = oscrange_config.get("down", {})

        # Get status dependency from down config
        status_dependencies = down_config.get(
            DreoFeatureSpec.STATUS_AVAILABLE_DEPENDENCIES, []
        )
        self._status_dependency = DreotStatusDependency(status_dependencies)

        # Get step value from down config
        step_value = down_config.get("step", 1)
        if isinstance(step_value, int | float):
            with contextlib.suppress(TypeError, ValueError):
                self._step_value = int(step_value)

        # Get down range from down config
        down_rng = down_config.get("range", [])
        if isinstance(down_rng, list | tuple) and len(down_rng) >= MIN_RANGE_LEN:
            with contextlib.suppress(TypeError, ValueError):
                self._min_value, self._max_value = int(down_rng[0]), int(down_rng[1])

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not data:
            return
        available_depend = self._status_dependency(data)
        self._attr_available = data.available and available_depend
        if self._attr_available:
            up, down = self._parse_oscrange_pair(
                getattr(data, self._oscrange_directive_name, None)
            )
            # Apply vertical spacing constraint
            up, down = self._apply_vertical_spacing(up, down)
            self._up = up
            self._down = down
            if down is None:
                self._attr_native_value = None
            else:
                self._attr_native_value = float(down)
        super()._handle_coordinator_update()

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for down range and write pair back."""
        if not self._attr_available:
            return

        req_down = max(self._min_value, min(self._max_value, int(value)))
        up_current = self._up
        if up_current is None and self.coordinator.data:
            up_current, _ = self._parse_oscrange_pair(
                getattr(self.coordinator.data, self._oscrange_directive_name, None)
            )

        # Limit down value to ensure vertical spacing: up - down >= spacing.
        if up_current is not None:
            max_down = up_current - self._vertical_spacing
            req_down = min(req_down, max_down)

        self._attr_native_value = float(req_down)
        super()._handle_coordinator_update()
        if up_current is not None:
            value_dict = {"U": up_current, "D": req_down}
            await self.async_send_command_and_update(
                DreoErrorCode.SET_FIXED_ANGLE_FAILED,
                **{self._oscrange_directive_name: value_dict},
            )
