"""Data update coordinator for Dreo devices."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
import logging
from typing import Any, NoReturn

from pydreo.client import DreoClient
from pydreo.exceptions import DreoException

from homeassistant.components.climate import HVACMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util.percentage import ranged_value_to_percentage

from .const import (
    CEILING_FAN_DEVICE_TYPE,
    CIR_FAN_DEVICE_TYPE,
    DOMAIN,
    FAN_DEVICE_TYPE,
    HAC_DEVICE_TYPE,
    HEC_DEVICE_TYPE,
)

_LOGGER = logging.getLogger(__name__)

UPDATE_INTERVAL = timedelta(seconds=10)


class DreoGenericDeviceData:
    """Base data for all Dreo devices."""

    available: bool = False
    is_on: bool = False

    def __init__(self, available: bool = False, is_on: bool = False) -> None:
        """Initialize generic device data."""
        self.available = available
        self.is_on = is_on


class DreoFanDeviceData(DreoGenericDeviceData):
    """Data specific to Dreo fan devices."""

    mode: str | None = None
    oscillate: bool | None = None
    speed_percentage: int | None = None
    model_config: dict[str, Any] | None = None

    def __init__(
        self,
        available: bool = False,
        is_on: bool = False,
        mode: str | None = None,
        oscillate: bool | None = None,
        speed_percentage: int | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize fan device data."""
        super().__init__(available, is_on)
        self.mode = mode
        self.oscillate = oscillate
        self.speed_percentage = speed_percentage
        self.model_config = model_config

    @staticmethod
    def process_fan_data(
        status: dict[str, Any], model_config: dict[str, Any]
    ) -> DreoFanDeviceData:
        """Process fan device specific data."""

        fan_data = DreoFanDeviceData(
            available=status.get("connected", False),
            is_on=status.get("power_switch", False),
        )

        if (mode := status.get("mode")) is not None:
            fan_data.mode = str(mode)

        if (oscillate := status.get("oscillate")) is not None:
            fan_data.oscillate = bool(oscillate)

        if (speed := status.get("speed")) is not None:
            speed_range = model_config.get("speed_range")
            if speed_range and len(speed_range) >= 2:
                fan_data.speed_percentage = int(
                    ranged_value_to_percentage(tuple(speed_range), float(speed))
                )

        return fan_data


class DreoCirculationFanDeviceData(DreoGenericDeviceData):
    """Data specific to Dreo circulation fan devices."""

    mode: str | None = None
    speed_level: int | None = None
    speed_percentage: int | None = None
    swing_direction: str | None = None
    rgb_state: bool | None = None
    rgb_mode: str | None = None
    rgb_color: int | None = None
    rgb_brightness: int | None = None
    rgb_speed: int | None = None
    model_config: dict[str, Any] | None = None

    def __init__(
        self,
        available: bool = False,
        is_on: bool = False,
        mode: str | None = None,
        speed_level: int | None = None,
        speed_percentage: int | None = None,
        swing_direction: str | None = None,
        rgb_state: bool | None = None,
        rgb_mode: str | None = None,
        rgb_color: int | None = None,
        rgb_brightness: int | None = None,
        rgb_speed: int | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize circulation fan device data."""
        super().__init__(available, is_on)
        self.mode = mode
        self.speed_level = speed_level
        self.speed_percentage = speed_percentage
        self.swing_direction = swing_direction
        self.rgb_state = rgb_state
        self.rgb_mode = rgb_mode
        self.rgb_color = rgb_color
        self.rgb_brightness = rgb_brightness
        self.rgb_speed = rgb_speed
        self.model_config = model_config

    @staticmethod
    def process_circulation_fan_data(
        status: dict[str, Any], model_config: dict[str, Any]
    ) -> DreoCirculationFanDeviceData:
        """Process circulation fan device specific data."""

        fan_data = DreoCirculationFanDeviceData(
            available=status.get("connected", False),
            is_on=status.get("power_switch", False),
            model_config=model_config,
        )

        if (mode := status.get("mode")) is not None:
            fan_data.mode = str(mode)

        if (speed := status.get("speed")) is not None:
            fan_data.speed_level = int(speed)
            speed_range = model_config.get("speed_range")
            if speed_range and len(speed_range) >= 2:
                fan_data.speed_percentage = int(
                    ranged_value_to_percentage(tuple(speed_range), float(speed))
                )

        if (osc_mode := status.get("oscmode")) is not None:
            direction_modes = model_config.get("selectOptions")

            if direction_modes and osc_mode in direction_modes:
                fan_data.swing_direction = osc_mode
            else:
                fan_data.swing_direction = "fixed"

        if (rgb_switch := status.get("ambient_switch")) is not None:
            fan_data.rgb_state = bool(rgb_switch)

        if (rgb_mode := status.get("atmmode")) is not None:
            fan_data.rgb_mode = str(rgb_mode)

        if (rgb_color := status.get("atmcolor")) is not None:
            fan_data.rgb_color = int(rgb_color)

        if (rgb_brightness := status.get("atmbri")) is not None:
            fan_data.rgb_brightness = int(rgb_brightness)

        if (rgb_speed := status.get("atmspeed")) is not None:
            fan_data.rgb_speed = int(rgb_speed)

        return fan_data


class DreoHacDeviceData(DreoGenericDeviceData):
    """Data specific to Dreo HAC (Air Conditioner) devices."""

    mode: str | None = None
    hvac_mode: str | None = None
    speed_level: int | None = None
    speed_percentage: int | None = None
    current_temperature: float | None = None
    target_temperature: float | None = None
    target_humidity: float | None = None
    model_config: dict[str, Any] | None = None

    def __init__(
        self,
        available: bool = False,
        is_on: bool = False,
        mode: str | None = None,
        hvac_mode: str | None = None,
        speed_level: int | None = None,
        speed_percentage: int | None = None,
        target_temperature: float | None = None,
        target_humidity: float | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize HAC device data."""
        super().__init__(available, is_on)
        self.mode = mode
        self.hvac_mode = hvac_mode
        self.speed_level = speed_level
        self.speed_percentage = speed_percentage
        self.target_temperature = target_temperature
        self.target_humidity = target_humidity
        self.model_config = model_config

    @staticmethod
    def process_hac_data(
        status: dict[str, Any], model_config: dict[str, Any]
    ) -> DreoHacDeviceData:
        """Process HAC device specific data."""

        hac_data = DreoHacDeviceData(
            available=status.get("connected", False),
            is_on=status.get("power_switch", False),
            model_config=model_config,
        )

        if (hvac_mode := status.get("hvacmode")) is not None:
            hac_data.hvac_mode = str(hvac_mode)

        if (mode := status.get("mode")) is not None:
            hac_data.mode = str(mode)
            if mode in ["sleep", "eco"]:
                hac_data.hvac_mode = HVACMode.COOL

        if (speed := status.get("speed")) is not None:
            hac_data.speed_level = int(speed)
            speed_range = model_config.get("speed_range")
            if speed_range and len(speed_range) >= 2:
                hac_data.speed_percentage = int(
                    ranged_value_to_percentage(tuple(speed_range), float(speed))
                )

        if (temp := status.get("temperature")) is not None:
            hac_data.target_temperature = float(temp)

        if (humidity := status.get("humidity")) is not None:
            hac_data.target_humidity = float(humidity)

        return hac_data


class DreoHecDeviceData(DreoGenericDeviceData):
    """Data specific to Dreo HEC (Hybrid Evaporative Cooler) devices."""

    mode: str | None = None
    speed_level: int | None = None
    speed_percentage: int | None = None
    oscillate: bool | None = None
    target_humidity: float | None = None
    current_humidity: float | None = None
    model_config: dict[str, Any] | None = None

    def __init__(
        self,
        available: bool = False,
        is_on: bool = False,
        mode: str | None = None,
        speed_level: int | None = None,
        speed_percentage: int | None = None,
        oscillate: bool | None = None,
        target_humidity: float | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize HEC device data."""
        super().__init__(available, is_on)
        self.mode = mode
        self.speed_level = speed_level
        self.speed_percentage = speed_percentage
        self.oscillate = oscillate
        self.target_humidity = target_humidity
        self.model_config = model_config

    @staticmethod
    def process_hec_data(
        status: dict[str, Any], model_config: dict[str, Any]
    ) -> DreoHecDeviceData:
        """Process HEC device specific data."""

        hec_data = DreoHecDeviceData(
            available=status.get("connected", False),
            is_on=status.get("power_switch", False),
            model_config=model_config,
        )

        if (mode := status.get("mode")) is not None:
            hec_data.mode = str(mode)

        if (speed := status.get("speed")) is not None:
            hec_data.speed_level = int(speed)
            speed_range = model_config.get("speed_range")
            if speed_range and len(speed_range) >= 2:
                hec_data.speed_percentage = int(
                    ranged_value_to_percentage(tuple(speed_range), float(speed))
                )

        if (oscillate := status.get("oscillate")) is not None:
            hec_data.oscillate = bool(oscillate)

        if (humidity := status.get("humidity")) is not None:
            hec_data.target_humidity = float(humidity)

        return hec_data


class DreoCeilingFanDeviceData(DreoGenericDeviceData):
    """Data specific to Dreo Ceiling Fan devices."""

    mode: str | None = None
    speed_level: int | None = None
    speed_percentage: int | None = None
    light_switch: bool | None = None
    light_brightness: int | None = None
    light_color_temp: int | None = None
    model_config: dict[str, Any] | None = None

    def __init__(
        self,
        available: bool = False,
        is_on: bool = False,
        mode: str | None = None,
        speed_level: int | None = None,
        speed_percentage: int | None = None,
        light_switch: bool | None = None,
        light_brightness: int | None = None,
        light_color_temp: int | None = None,
        model_config: dict[str, Any] | None = None,
    ) -> None:
        """Initialize ceiling fan device data."""
        super().__init__(available, is_on)
        self.mode = mode
        self.speed_level = speed_level
        self.speed_percentage = speed_percentage
        self.light_switch = light_switch
        self.light_brightness = light_brightness
        self.light_color_temp = light_color_temp
        self.model_config = model_config

    @staticmethod
    def process_ceiling_fan_data(
        status: dict[str, Any], model_config: dict[str, Any]
    ) -> DreoCeilingFanDeviceData:
        """Process ceiling fan device specific data."""

        ceiling_fan_data = DreoCeilingFanDeviceData(
            available=status.get("connected", False),
            is_on=status.get("power_switch", False),
            model_config=model_config,
        )

        if (mode := status.get("mode")) is not None:
            ceiling_fan_data.mode = str(mode)

        if (speed := status.get("speed")) is not None:
            ceiling_fan_data.speed_level = int(speed)
            speed_range = model_config.get("speed_range")
            if speed_range and len(speed_range) >= 2:
                ceiling_fan_data.speed_percentage = int(
                    ranged_value_to_percentage(tuple(speed_range), float(speed))
                )

        if (light_switch := status.get("light_switch")) is not None:
            ceiling_fan_data.light_switch = bool(light_switch)

        if (brightness := status.get("brightness")) is not None:
            ceiling_fan_data.light_brightness = int(brightness)

        if (color_temp := status.get("colortemp")) is not None:
            ceiling_fan_data.light_color_temp = int(color_temp)

        return ceiling_fan_data


DreoDeviceData = (
    DreoFanDeviceData
    | DreoCirculationFanDeviceData
    | DreoHacDeviceData
    | DreoHecDeviceData
    | DreoCeilingFanDeviceData
)


class DreoDataUpdateCoordinator(DataUpdateCoordinator[DreoDeviceData | None]):
    """Class to manage fetching Dreo data."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DreoClient,
        device_id: str,
        device_type: str,
        model_config: dict[str, Any],
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.device_id = device_id
        self.device_type = device_type
        self.model_config = model_config
        self.data_processor: (
            Callable[[dict[str, Any], dict[str, Any]], DreoDeviceData] | None
        )

        if self.device_type == FAN_DEVICE_TYPE:
            self.data_processor = DreoFanDeviceData.process_fan_data
        elif self.device_type == CIR_FAN_DEVICE_TYPE:
            self.data_processor = (
                DreoCirculationFanDeviceData.process_circulation_fan_data
            )
        elif self.device_type == CEILING_FAN_DEVICE_TYPE:
            self.data_processor = DreoCeilingFanDeviceData.process_ceiling_fan_data
        elif self.device_type == HAC_DEVICE_TYPE:
            self.data_processor = DreoHacDeviceData.process_hac_data
        elif self.device_type == HEC_DEVICE_TYPE:
            self.data_processor = DreoHecDeviceData.process_hec_data
        else:
            _LOGGER.warning(
                "Unsupported device type: %s for model: %s - data will not be processed",
                self.device_type,
                self.device_id,
            )
            self.data_processor = None

    async def _async_update_data(self) -> DreoDeviceData | None:
        """Get device status from Dreo API and process it."""

        def _raise_no_status() -> NoReturn:
            """Raise UpdateFailed for no status available."""
            raise UpdateFailed(
                f"No status available for device {self.device_id} with type {self.device_type}"
            )

        def _raise_no_processor() -> NoReturn:
            """Raise UpdateFailed for no data processor available."""
            raise UpdateFailed(
                f"No data processor available for device {self.device_id} with type {self.device_type}"
            )

        try:
            status = await self.hass.async_add_executor_job(
                self.client.get_status, self.device_id
            )

            if status is None:
                _raise_no_status()

            if self.data_processor is None:
                _raise_no_processor()

            return self.data_processor(status, self.model_config)
        except DreoException as error:
            raise UpdateFailed(f"Error communicating with Dreo API: {error}") from error
        except Exception as error:
            raise UpdateFailed(f"Unexpected error: {error}") from error
