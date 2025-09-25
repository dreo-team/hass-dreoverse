"""Support for Dreo number entities (RGB humidity thresholds)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DreoConfigEntry
from .const import DreoDirective, DreoEntityConfigSpec, DreoErrorCode
from .coordinator import DreoDataUpdateCoordinator, DreoHumidifierDeviceData
from .entity import DreoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Dreo number entities from a config entry."""

    @callback
    def async_add_number_entities() -> None:
        numbers: list[DreoRgbThresholdLow | DreoRgbThresholdHigh] = []

        for device in config_entry.runtime_data.devices:
            device_id = device.get("deviceSn")
            if not device_id:
                continue

            top_config = device.get(DreoEntityConfigSpec.TOP_CONFIG, {})
            has_number_support = Platform.NUMBER in top_config.get("entitySupports", [])

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for device %s", device_id)
                continue

            if not isinstance(coordinator.data, DreoHumidifierDeviceData):
                continue

            # Create even if platform not advertised, when threshold capability/config exists
            rng = coordinator.model_config.get(
                DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
            ).get("ambient_threshold", [])
            has_conf = isinstance(rng, (list, tuple)) and len(rng) >= 2

            has_cap = False
            for cap in device.get("capabilities", []) or []:
                if (
                    isinstance(cap, dict)
                    and cap.get("interface") == "ThresholdController"
                    and cap.get("instance") == "rgbThreshold"
                ):
                    has_cap = True
                    break

            if not (has_number_support or has_conf or has_cap):
                continue

            numbers.append(DreoRgbThresholdLow(device, coordinator))
            numbers.append(DreoRgbThresholdHigh(device, coordinator))

        if numbers:
            async_add_entities(numbers)

    async_add_number_entities()


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

        # Determine min/max/step
        rng = coordinator.model_config.get(
            DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
        ).get("ambient_threshold", [])
        if isinstance(rng, (list, tuple)) and len(rng) >= 2:
            try:
                self._min_value = int(rng[0])
                self._max_value = int(rng[1])
            except (TypeError, ValueError):
                pass

        step = None
        if step is None:
            step = 1
        self._step_value = max(1, step)

    @property
    def native_min_value(self) -> float:
        return float(self._min_value)

    @property
    def native_max_value(self) -> float:
        return float(self._max_value)

    @property
    def native_step(self) -> float:
        return float(self._step_value)

    @callback
    def _handle_coordinator_update(self) -> None:
        data = self.coordinator.data
        if not isinstance(data, DreoHumidifierDeviceData):
            return
        self._attr_available = data.available and bool(
            getattr(data, "ambient_Light_switch", False)
        )

        rgb = getattr(data, "rgb_threshold", None)
        low: int | None = None
        high: int | None = None
        if isinstance(rgb, (list, tuple)) and len(rgb) >= 2:
            try:
                low = int(rgb[0])
                high = int(rgb[1])
            except (TypeError, ValueError):
                low = None
                high = None
        elif isinstance(rgb, str) and "," in rgb:
            parts = rgb.split(",")
            if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                low = int(parts[0])
                high = int(parts[1])

        # Cache last known pair for local clamping
        self._pair_low = low
        self._pair_high = high
        self._sync_from_pair(low, high)
        super()._handle_coordinator_update()

    def _sync_from_pair(self, low: int | None, high: int | None) -> None:
        # Implemented in subclasses
        raise NotImplementedError

    async def _write_pair(self, low: int, high: int) -> None:
        # Update cache immediately
        self._pair_low = int(low)
        self._pair_high = int(high)
        value = f"{self._pair_low},{self._pair_high}"
        await self.async_send_command_and_update(
            DreoErrorCode.SET_RGB_THRESHOLD_FAILED,
            **{DreoDirective.RGB_HUMIDITY_THRESHOLD.value: value},
        )


class DreoRgbThresholdLow(_DreoRgbThresholdBase):
    """Number entity for the low RGB humidity threshold."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the low threshold slider."""
        super().__init__(device, coordinator, "rgb_threshold_low", "Ambient Light Low")

    def _sync_from_pair(self, low: int | None, high: int | None) -> None:
        """Sync entity value from pair received in coordinator state."""
        if low is None:
            self._attr_native_value = None
            return
        self._attr_native_value = float(low)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for low threshold and write pair back."""
        # Block when ambient light is off
        data = self.coordinator.data
        if not isinstance(data, DreoHumidifierDeviceData) or not bool(
            getattr(data, "ambient_Light_switch", False)
        ):
            return
        req_low = int(max(self._min_value, min(self._max_value, int(value))))
        high_current: int | None = self._pair_high
        if high_current is None and isinstance(data, DreoHumidifierDeviceData):
            rgb = getattr(data, "rgb_threshold", None)
            if (
                isinstance(rgb, (list, tuple))
                and len(rgb) >= 2
                and str(rgb[1]).isdigit()
            ):
                high_current = int(rgb[1])
            elif isinstance(rgb, str) and "," in rgb:
                parts = rgb.split(",")
                if len(parts) >= 2 and parts[1].isdigit():
                    high_current = int(parts[1])

        clamped_low = req_low
        if high_current is not None:
            max_allowed_low = max(
                self._min_value, min(self._max_value, high_current - 5)
            )
            clamped_low = min(req_low, max_allowed_low)

        if clamped_low != req_low:
            self._attr_native_value = float(clamped_low)
            self.async_write_ha_state()
        else:
            self._attr_native_value = float(clamped_low)

        target_high = (
            high_current
            if high_current is not None
            else max(self._min_value, min(self._max_value, clamped_low + 5))
        )
        # Schedule write to avoid blocking immediate UI update
        self.hass.async_create_task(self._write_pair(clamped_low, target_high))


class DreoRgbThresholdHigh(_DreoRgbThresholdBase):
    """Number entity for the high RGB humidity threshold."""

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the high threshold slider."""
        super().__init__(
            device, coordinator, "rgb_threshold_high", "Ambient Light High"
        )

    def _sync_from_pair(self, low: int | None, high: int | None) -> None:
        """Sync entity value from pair received in coordinator state."""
        if high is None:
            self._attr_native_value = None
            return
        self._attr_native_value = float(high)

    async def async_set_native_value(self, value: float) -> None:
        """Handle slider change for high threshold and write pair back."""
        # Block when ambient light is off
        data = self.coordinator.data
        if not isinstance(data, DreoHumidifierDeviceData) or not bool(
            getattr(data, "ambient_Light_switch", False)
        ):
            return
        req_high = int(min(self._max_value, max(self._min_value, int(value))))

        # 2) Read current low
        low_current: int | None = self._pair_low
        if low_current is None and isinstance(data, DreoHumidifierDeviceData):
            rgb = getattr(data, "rgb_threshold", None)
            if (
                isinstance(rgb, (list, tuple))
                and len(rgb) >= 2
                and str(rgb[0]).isdigit()
            ):
                low_current = int(rgb[0])
            elif isinstance(rgb, str) and "," in rgb:
                parts = rgb.split(",")
                if len(parts) >= 2 and parts[0].isdigit():
                    low_current = int(parts[0])

        # 3) Enforce only current slider: high >= low + 5 (if low known)
        clamped_high = req_high
        if low_current is not None:
            min_allowed_high = min(
                self._max_value, max(self._min_value, low_current + 5)
            )
            clamped_high = max(req_high, min_allowed_high)

        # 4) Immediately reflect in UI if changed
        if clamped_high != req_high:
            self._attr_native_value = float(clamped_high)
            self.async_write_ha_state()
        else:
            self._attr_native_value = float(clamped_high)

        # 5) Keep low unchanged; if unknown, use minimal valid guess
        target_low = (
            low_current
            if low_current is not None
            else max(self._min_value, min(self._max_value, clamped_high - 5))
        )
        # Schedule write to avoid blocking immediate UI update
        self.hass.async_create_task(self._write_pair(target_low, clamped_high))
