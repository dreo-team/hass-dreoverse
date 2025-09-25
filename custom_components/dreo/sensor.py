"""Support for Dreo sensors (e.g., humidity)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DreoConfigEntry
from .const import DreoEntityConfigSpec
from .coordinator import DreoDataUpdateCoordinator, DreoDehumidifierDeviceData
from .entity import DreoEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up Dreo sensor entities from a config entry."""

    @callback
    def async_add_sensor_entities() -> None:
        sensors: list[DreoDehumidifierHumiditySensor] = []

        for device in config_entry.runtime_data.devices:
            device_id = device.get("deviceSn")
            if not device_id:
                continue

            top_config = device.get(DreoEntityConfigSpec.TOP_CONFIG, {})
            has_sensor_support = Platform.SENSOR in top_config.get("entitySupports", [])

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for device %s", device_id)
                continue

            if not isinstance(coordinator.data, DreoDehumidifierDeviceData):
                continue

            if not has_sensor_support:
                continue

            sensors.append(DreoDehumidifierHumiditySensor(device, coordinator))

        if sensors:
            async_add_entities(sensors)

    async_add_sensor_entities()


class DreoDehumidifierHumiditySensor(DreoEntity, SensorEntity):
    """Live humidity sensor from device reported rh."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_value: float | None = None

    def __init__(
        self, device: dict[str, Any], coordinator: DreoDataUpdateCoordinator
    ) -> None:
        """Initialize the humidity sensor."""
        super().__init__(device, coordinator, "humidity", "Humidity")
        device_id = device.get("deviceSn")
        self._attr_unique_id = f"{device_id}_humidity"

    @callback
    def _handle_coordinator_update(self) -> None:
        if not self.coordinator.data:
            return
        data = self.coordinator.data
        if not isinstance(data, DreoDehumidifierDeviceData):
            return
        self._attr_available = data.available
        self._attr_native_value = (
            float(data.current_humidity) if data.current_humidity is not None else None
        )
        super()._handle_coordinator_update()
