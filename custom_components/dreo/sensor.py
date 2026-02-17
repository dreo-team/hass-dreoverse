"""Support for Dreo sensors (e.g., humidity)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import PERCENTAGE, Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import UNDEFINED

from . import DreoConfigEntry
from .const import DreoEntityConfigSpec, DreoFeatureSpec
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
        sensors: list[DreoHumidityGenericSensor | DreoGenericSensor] = []

        for device in config_entry.runtime_data.devices:
            device_id = device.get("deviceSn")
            if not device_id:
                continue

            top_config = device.get(DreoEntityConfigSpec.TOP_CONFIG, {})
            has_sensor_support = Platform.SENSOR in top_config.get(
                DreoEntityConfigSpec.ENTITY_SUPPORTS, []
            )

            coordinator = config_entry.runtime_data.coordinators.get(device_id)
            if not coordinator:
                _LOGGER.error("Coordinator not found for device %s", device_id)
                continue

            if not has_sensor_support:
                continue

            sensor_config = coordinator.model_config.get(
                DreoEntityConfigSpec.SENSOR_ENTITY_CONF, {}
            )
            for sensor_type, sensor_conf in sensor_config.items():
                sensors.append(
                    DreoGenericSensor(device, coordinator, sensor_type, sensor_conf)
                )

            if isinstance(coordinator.data, (DreoDehumidifierDeviceData)):
                sensors.append(DreoHumidityGenericSensor(device, coordinator))

        if sensors:
            async_add_entities(sensors)

    async_add_sensor_entities()


class DreoGenericSensor(DreoEntity, SensorEntity):
    """Generic Dreo sensor entity based on config."""

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
        sensor_type: str,
        config: dict[str, Any],
    ) -> None:
        """Initialize the config-based sensor."""
        attr_name = config.get(DreoFeatureSpec.ATTR_NAME, sensor_type)
        super().__init__(device, coordinator, "sensor", attr_name)

        device_id = device.get("deviceSn")
        directive_name = config.get(DreoFeatureSpec.DIRECTIVE_NAME, sensor_type)
        self._attr_unique_id = f"{device_id}_{directive_name}"

        self._directive_name = directive_name
        self._state_attr_name = config.get(DreoFeatureSpec.STATE_ATTR_NAME)

        icon = config.get(DreoFeatureSpec.ATTR_ICON)
        if icon:
            self._attr_icon = icon

        sensor_class = config.get(DreoFeatureSpec.SENSOR_CLASS, sensor_type)
        # Convert string to SensorDeviceClass enum if needed
        if isinstance(sensor_class, str):
            try:
                self._attr_device_class = SensorDeviceClass(sensor_class)
            except ValueError:
                self._attr_device_class = None
        else:
            self._attr_device_class = sensor_class

        # Get sensor_unit from config, default to None
        sensor_unit = config.get(DreoFeatureSpec.SENSOR_UNIT)
        if sensor_unit == "celsius":
            self._attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
        elif sensor_unit == "fahrenheit":
            self._attr_native_unit_of_measurement = UnitOfTemperature.FAHRENHEIT
        elif self._attr_device_class == SensorDeviceClass.TEMPERATURE:
            # For temperature sensors without explicit unit, use system unit
            self._attr_native_unit_of_measurement = (
                self.coordinator.hass.config.units.temperature_unit
            )
        else:
            self._attr_native_unit_of_measurement = None

        # For temperature sensors, don't set suggested_unit_of_measurement
        # to allow Home Assistant's automatic temperature conversion to work
        if self._attr_device_class == SensorDeviceClass.TEMPERATURE:
            self._attr_suggested_unit_of_measurement = None

    def get_initial_entity_options(self):
        """
        Return initial entity options.

        For temperature sensors, return None to prevent storing suggested_unit_of_measurement,
        allowing Home Assistant's automatic temperature conversion to work.
        """
        if self._attr_device_class == SensorDeviceClass.TEMPERATURE:
            return None
        return super().get_initial_entity_options()

    @callback
    def _async_read_entity_options(self) -> None:
        """
        Read entity options from entity registry.

        For temperature sensors, clear _sensor_option_unit_of_measurement to allow
        Home Assistant's automatic temperature conversion to work.
        """
        super()._async_read_entity_options()
        # For temperature sensors, clear _sensor_option_unit_of_measurement
        # to allow automatic temperature conversion
        if self._attr_device_class == SensorDeviceClass.TEMPERATURE:
            self._sensor_option_unit_of_measurement = UNDEFINED

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        data = self.coordinator.data
        if not data:
            return

        self._attr_available = data.available

        if self._state_attr_name and hasattr(data, self._state_attr_name):
            value = getattr(data, self._state_attr_name, None)
            self._attr_native_value = value if value is not None else None
        else:
            self._attr_native_value = None

        super()._handle_coordinator_update()


class DreoHumidityGenericSensor(DreoEntity, SensorEntity):
    """Live humidity sensor from device reported rh."""

    _attr_device_class = SensorDeviceClass.HUMIDITY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_native_value: float | None = None

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
        unique_id_suffix: str | None = None,
        name: str | None = None,
    ) -> None:
        """Initialize the humidity sensor."""
        super().__init__(device, coordinator, unique_id_suffix, name)
        device_id = device.get("deviceSn")
        self._attr_unique_id = f"{device_id}_{unique_id_suffix}"

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
