"""Support for Dreo humidifier entities."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, ClassVar

from homeassistant.components.humidifier import (
    HumidifierEntity,
    HumidifierEntityFeature,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError

if TYPE_CHECKING:
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
    DreoDehumidifierDeviceData,
    DreoHecDeviceData,
    DreoHumidifierDeviceData,
)
from .entity import DreoEntity

_LOGGER = logging.getLogger(__name__)
MIN_RANGE_LEN = 2
DEFAULT_FOG_LEVEL_RANGE = (1, 6)


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: DreoConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Dreo humidifier entities from a config entry."""

    @callback
    def async_add_humidifier_entities() -> None:
        """Add humidifier entities."""
        humidifiers: list[DreoHumidifier | DreoDehumidifier | DreoHecHumidifier] = []

        for device in config_entry.runtime_data.devices:
            device_type = device.get("deviceType")
            if device_type not in [
                DreoDeviceType.HEC,
                DreoDeviceType.HUMIDIFIER,
                DreoDeviceType.DEHUMIDIFIER,
            ]:
                continue

            device_id = device.get("deviceSn")
            if not device_id:
                continue

            device_config = device.get(DreoEntityConfigSpec.TOP_CONFIG, {})
            entity_supports = device_config.get("entitySupports", [])
            device_model = device.get("model")

            _LOGGER.debug(
                "Device %s config %s Platform.HUMIDIFIER value: %s",
                device_model,
                device_config,
                Platform.HUMIDIFIER,
            )

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

            if device_type == DreoDeviceType.HUMIDIFIER:
                humidifier_entity = DreoHumidifier(device, coordinator)
                humidifiers.append(humidifier_entity)
            elif device_type == DreoDeviceType.DEHUMIDIFIER:
                dehumidifier_entity = DreoDehumidifier(device, coordinator)
                humidifiers.append(dehumidifier_entity)
            elif device_type == DreoDeviceType.HEC:
                hec_humidifier_entity = DreoHecHumidifier(device, coordinator)
                humidifiers.append(hec_humidifier_entity)

        if humidifiers:
            async_add_entities(humidifiers)

    async_add_humidifier_entities()


class DreoHecHumidifier(DreoEntity, HumidifierEntity):
    """Dreo HEC (Hybrid Evaporative Cooler) humidifier entity."""

    _attr_supported_features: ClassVar[HumidifierEntityFeature] = (
        HumidifierEntityFeature.MODES
    )
    _attr_is_on: ClassVar[bool] = False
    _attr_mode: str | None = None
    _attr_current_humidity: int | None = None
    _attr_target_humidity: int | None = None
    _attr_available_modes: ClassVar[list[str]] = []

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the Dreo HEC humidifier."""
        super().__init__(device, coordinator, "humidifier", "Humidifier")

        model_config = coordinator.model_config
        humidifier_config = model_config.get(
            DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
        )

        humidity_range = humidifier_config.get(DreoFeatureSpec.HUMIDITY_RANGE)
        if humidity_range and len(humidity_range) >= MIN_RANGE_LEN:
            self._attr_min_humidity = int(humidity_range[0])
            self._attr_max_humidity = int(humidity_range[1])

        self._attr_available_modes = (
            humidifier_config.get(DreoFeatureSpec.PRESET_MODES) or []
        )

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
        self._attr_is_on = (
            hec_data.humidity_switch if hec_data.humidity_switch is not None else False
        )

        if hec_data.humidity_mode is not None:
            self._attr_mode = hec_data.humidity_mode

        if hec_data.target_humidity is not None:
            self._attr_target_humidity = int(hec_data.target_humidity)

    @property
    def is_on(self) -> bool:
        """Return True if the humidifier is on."""
        if self._attr_is_on is None:
            return False
        return self._attr_is_on

    @property
    def mode(self) -> str | None:
        """Return the current mode."""
        return self._attr_mode

    @property
    def target_humidity(self) -> int | None:
        """Return the target humidity."""
        return self._attr_target_humidity

    async def async_turn_on(self, **_: Any) -> None:
        """Turn the humidifier on."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_ON_FAILED, humidity_switch=True
        )

    async def async_turn_off(self, **_: Any) -> None:
        """Turn the humidifier off."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_OFF_FAILED, humidity_switch=False
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
            command_params[DreoDirective.HUMIDITY_SWITCH] = True

        command_params[DreoDirective.HUMIDITY] = int(humidity)

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HEC_HUMIDITY_FAILED, **command_params
        )

    async def async_set_mode(self, mode: str) -> None:
        """Set the mode of the humidifier."""
        if not self._attr_available_modes or mode not in self._attr_available_modes:
            _LOGGER.error("Mode %s is not available", mode)
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params[DreoDirective.HUMIDITY_SWITCH] = True

        command_params[DreoDirective.HUMIDITY_MODE] = mode.capitalize()

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HUMIDIFIER_MODE_FAILED, **command_params
        )


class DreoHumidifier(DreoEntity, HumidifierEntity):
    """Dreo Humidifier entity for dedicated humidifier devices like HHM001S."""

    _attr_supported_features: ClassVar[HumidifierEntityFeature] = (
        HumidifierEntityFeature.MODES
    )
    _attr_is_on: ClassVar[bool] = False
    _attr_mode: str | None = None
    _attr_current_humidity: int | None = None
    _attr_target_humidity: int | None = None
    _attr_available_modes: ClassVar[list[str]] = []
    _attr_directive_graph: ClassVar[dict[str, Any]] = {}
    _attr_description_limits: ClassVar[dict[str, Any]] = {}
    _attr_fog_level_range: ClassVar[list[int]] = list(DEFAULT_FOG_LEVEL_RANGE)
    _attr_rgb_humidity_threshold: str | None = None

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the Dreo humidifier."""
        super().__init__(device, coordinator, "humidifier", "Humidifier")

        model_config = coordinator.model_config
        humidifier_config = model_config.get(
            DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
        )

        # Set humidity range
        humidity_range = humidifier_config.get(DreoFeatureSpec.HUMIDITY_RANGE)
        if humidity_range and len(humidity_range) >= MIN_RANGE_LEN:
            self._attr_min_humidity = int(humidity_range[0])
            self._attr_max_humidity = int(humidity_range[1])
        else:
            self._attr_min_humidity = 30
            self._attr_max_humidity = 90

        humidity_mode_config = humidifier_config.get(
            DreoFeatureSpec.HUMIDIFIER_MODE_CONFIG, {}
        )

        self._attr_description_limits = humidifier_config.get(
            DreoFeatureSpec.DESCRIPTION_LIMITS, {}
        )
        self._attr_available_modes = humidity_mode_config.get(
            DreoFeatureSpec.PRESET_MODES, []
        )
        self._attr_directive_graph = humidity_mode_config.get(
            DreoFeatureSpec.DIRECTIVE_GRAPH, {}
        )

        # Set fog_level range from config
        fog_level_range = humidifier_config.get(
            "fog_level_range", DEFAULT_FOG_LEVEL_RANGE
        )
        if len(fog_level_range) >= MIN_RANGE_LEN:
            self._attr_fog_level_range = [
                int(fog_level_range[0]),
                int(fog_level_range[1]),
            ]
        else:
            self._attr_fog_level_range = list(DEFAULT_FOG_LEVEL_RANGE)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._update_attributes()
        super()._handle_coordinator_update()

    def _update_attributes(self) -> None:
        """Update attributes from coordinator data."""
        if not self.coordinator.data:
            return

        if not isinstance(self.coordinator.data, DreoHumidifierDeviceData):
            return

        humidifier_data = self.coordinator.data
        self._attr_available = humidifier_data.available
        self._attr_is_on = humidifier_data.is_on

        self._set_attrs_if(
            condition=not self._attr_is_on or not self._attr_available,
            target=self.coordinator.data,
            attrs={
                "current_humidity": None,
                "target_humidity": None,
                "mode": None,
            },
        )

        if humidifier_data.target_humidity is not None:
            self._attr_target_humidity = int(humidifier_data.target_humidity)

        if humidifier_data.current_humidity is not None:
            try:
                self._attr_current_humidity = int(humidifier_data.current_humidity)
            except (TypeError, ValueError):
                self._attr_current_humidity = None

        if (
            humidifier_data.mode
            and self._attr_available_modes
            and humidifier_data.mode in self._attr_available_modes
        ):
            self._attr_mode = humidifier_data.mode

        if self._attr_mode == "Manual":
            min_fog, max_fog = self._attr_fog_level_range
            self._attr_min_humidity = min_fog
            self._attr_max_humidity = 100

            if (
                hasattr(humidifier_data, "fog_level")
                and humidifier_data.fog_level is not None
            ):
                fog_level = int(humidifier_data.fog_level)
                percentage = int(
                    min_fog
                    + (fog_level - min_fog) / (max_fog - min_fog) * (100 - min_fog)
                )
                self._attr_target_humidity = percentage
        else:
            model_config = self.coordinator.model_config
            humidifier_config = model_config.get(
                DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
            )
            humidity_range = humidifier_config.get(DreoFeatureSpec.HUMIDITY_RANGE)
            if humidity_range and len(humidity_range) >= MIN_RANGE_LEN:
                self._attr_min_humidity = int(humidity_range[0])
                self._attr_max_humidity = int(humidity_range[1])

    async def async_turn_on(self, **_: Any) -> None:
        """Turn the humidifier on."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_ON_FAILED, power_switch=True
        )

    async def async_turn_off(self, **_: Any) -> None:
        """Turn the humidifier off."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_OFF_FAILED, power_switch=False
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
            command_params[DreoDirective.POWER_SWITCH] = True

        current_mode = self.mode

        mode_graph = self._attr_directive_graph.get(current_mode or "", {})
        directive_name = mode_graph.get("name")
        if not directive_name:
            _LOGGER.error("Directive name not found for mode %s", current_mode)
            return

        if directive_name:
            if current_mode == "Manual":
                min_fog, max_fog = self._attr_fog_level_range
                fog_level = max(
                    min_fog,
                    min(
                        max_fog,
                        round(
                            (humidity - min_fog) / (100 - min_fog) * (max_fog - min_fog)
                            + min_fog
                        ),
                    ),
                )
                command_params[directive_name] = fog_level
            else:
                command_params[directive_name] = int(humidity)

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HEC_HUMIDITY_FAILED, **command_params
        )

    async def async_set_mode(self, mode: str) -> None:
        """Set the mode of the humidifier."""
        if not self._attr_available_modes or mode not in self._attr_available_modes:
            _LOGGER.error("Mode %s is not available", mode)
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params[DreoDirective.POWER_SWITCH] = True

        command_params[DreoDirective.MODE] = mode

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HUMIDIFIER_MODE_FAILED, **command_params
        )


class DreoDehumidifier(DreoEntity, HumidifierEntity):
    """Expose target humidity adjustment for HDH devices in Auto/Custom."""

    _attr_supported_features: ClassVar[HumidifierEntityFeature] = (
        HumidifierEntityFeature.MODES
    )
    _attr_is_on: ClassVar[bool] = False
    _attr_mode: str | None = None
    _attr_current_humidity: int | None = None
    _attr_target_humidity: int | None = None
    _attr_available_modes: ClassVar[list[str]] = []
    _attr_directive_graph: ClassVar[dict[str, Any]] = {}
    _attr_description_limits: ClassVar[dict[str, Any]] = {}

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: DreoDataUpdateCoordinator,
    ) -> None:
        """Initialize the dehumidifier humidity interface."""
        super().__init__(device, coordinator, "humidifier", "Dehumidifier")

        model_config = coordinator.model_config
        humidifier_config = model_config.get(
            DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
        )

        # Target humidity range for HDH
        humidity_range = humidifier_config.get(DreoFeatureSpec.HUMIDITY_RANGE)
        if humidity_range and len(humidity_range) >= MIN_RANGE_LEN:
            self._attr_min_humidity = int(humidity_range[0])
            self._attr_max_humidity = int(humidity_range[1])

        humidity_mode_config = humidifier_config.get(
            DreoFeatureSpec.HUMIDIFIER_MODE_CONFIG, {}
        )
        self._attr_available_modes = humidity_mode_config.get(
            DreoFeatureSpec.PRESET_MODES, []
        )
        self._attr_directive_graph = humidity_mode_config.get(
            DreoFeatureSpec.DIRECTIVE_GRAPH, {}
        )
        self._attr_description_limits = humidifier_config.get(
            DreoFeatureSpec.DESCRIPTION_LIMITS, {}
        )

    @callback
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from coordinator."""
        self._update_attributes()
        super()._handle_coordinator_update()

    def _update_attributes(self) -> None:
        """Update internal attributes from coordinator data."""
        if not self.coordinator.data or not isinstance(
            self.coordinator.data, DreoDehumidifierDeviceData
        ):
            return

        data = self.coordinator.data
        self._attr_available = data.available
        self._attr_is_on = data.is_on
        if data.target_humidity is not None:
            self._attr_target_humidity = int(data.target_humidity)
        self._attr_mode = data.mode

        # If current mode disables humidity adjustment, freeze slider by setting
        # min == max.
        set_limits = self._attr_description_limits.get("set_humidity", {})
        disabled_modes = (
            set_limits.get("disableOnModes", []) if isinstance(set_limits, dict) else []
        )
        if self._attr_mode in disabled_modes:
            frozen_value = (
                int(self._attr_target_humidity)
                if isinstance(self._attr_target_humidity, int)
                else self._attr_min_humidity
            )
            self._attr_min_humidity = frozen_value
            self._attr_max_humidity = frozen_value

        else:
            model_config = self.coordinator.model_config
            humidifier_config = model_config.get(
                DreoEntityConfigSpec.HUMIDIFIER_ENTITY_CONF, {}
            )

            humidity_range = humidifier_config.get(DreoFeatureSpec.HUMIDITY_RANGE)
            if humidity_range and len(humidity_range) >= MIN_RANGE_LEN:
                self._attr_min_humidity = int(humidity_range[0])
                self._attr_max_humidity = int(humidity_range[1])

    async def async_turn_on(self, **_: Any) -> None:
        """Turn the humidifier on."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_ON_FAILED, power_switch=True
        )

    async def async_turn_off(self, **_: Any) -> None:
        """Turn the humidifier off."""
        await self.async_send_command_and_update(
            DreoErrorCode.TURN_OFF_FAILED, power_switch=False
        )

    async def async_set_mode(self, mode: str) -> None:
        """Set the mode of the humidifier."""
        if not self._attr_available_modes or mode not in self._attr_available_modes:
            _LOGGER.error("Mode %s is not available", mode)
            return

        command_params: dict[str, Any] = {}

        if not self.is_on:
            command_params[DreoDirective.POWER_SWITCH] = True

        command_params[DreoDirective.MODE] = mode

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HUMIDIFIER_MODE_FAILED, **command_params
        )

    async def async_set_humidity(self, humidity: int) -> None:
        """Set target humidity using directive graph like DreoHumidifier."""
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
            command_params[DreoDirective.POWER_SWITCH] = True

        # Check description limits for disabled modes
        set_limits = self._attr_description_limits.get("set_humidity", {})
        disabled_modes = (
            set_limits.get("disableOnModes", []) if isinstance(set_limits, dict) else []
        )
        if self.mode in disabled_modes:
            _LOGGER.error("Target humidity not supported in mode %s", self.mode)
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key=DreoErrorCode.HUMIDITY_NOT_SUPPORTED_IN_MODE,
            )

        mode_graph = self._attr_directive_graph.get(self.mode or "", {})
        directive_name = (
            mode_graph.get("name") if isinstance(mode_graph, dict) else None
        )
        if not directive_name:
            _LOGGER.error("Directive name not found for mode %s", self.mode)
            return

        command_params[directive_name] = int(humidity)

        await self.async_send_command_and_update(
            DreoErrorCode.SET_HUMIDITY_FAILED, **command_params
        )
