"""Import real setup/coordinator modules with only external HA/SDK boundary fakes."""

import importlib.util
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).parents[1] / "custom_components/dreo"


class CoordinatorBoundary:
    @classmethod
    def __class_getitem__(cls, item):
        return cls

    def __init__(self, hass, *args, **kwargs):
        self.hass, self.data = hass, None

    async def async_refresh(self):
        self.data = await self._async_update_data()

    def async_update_listeners(self):
        pass


class SetupTests(unittest.IsolatedAsyncioTestCase):
    def load(self):
        modules = {}

        def module(name, **attrs):
            obj = ModuleType(name)
            obj.__dict__.update(attrs)
            modules[name] = obj

        for name in (
            "homeassistant",
            "homeassistant.helpers",
            "homeassistant.components",
            "homeassistant.util",
            "pydreo",
        ):
            module(name)
        module("homeassistant.config_entries", ConfigEntry=CoordinatorBoundary)
        module(
            "homeassistant.const",
            CONF_PASSWORD="password",
            CONF_USERNAME="username",
            Platform=SimpleNamespace(
                **{
                    key: key
                    for key in (
                        "CLIMATE",
                        "FAN",
                        "HUMIDIFIER",
                        "LIGHT",
                        "NUMBER",
                        "SELECT",
                        "SENSOR",
                        "SWITCH",
                    )
                }
            ),
        )
        module(
            "homeassistant.exceptions",
            ConfigEntryAuthFailed=RuntimeError,
            ConfigEntryNotReady=RuntimeError,
        )
        module(
            "homeassistant.helpers.aiohttp_client",
            async_get_clientsession=lambda hass: None,
        )
        module(
            "homeassistant.helpers.update_coordinator",
            DataUpdateCoordinator=CoordinatorBoundary,
            UpdateFailed=RuntimeError,
        )
        module(
            "homeassistant.components.climate", HVACMode=SimpleNamespace(COOL="cool")
        )
        module(
            "homeassistant.util.percentage", ranged_value_to_percentage=lambda *args: 0
        )
        module("pydreo.client", DreoClient=object)
        module(
            "pydreo.exceptions",
            DreoBusinessException=RuntimeError,
            DreoException=RuntimeError,
        )
        self.boundaries = patch.dict(sys.modules, modules)
        self.boundaries.start()
        self.addCleanup(self.boundaries.stop)
        for name in list(sys.modules):
            if name.startswith("fixture_dreo"):
                del sys.modules[name]
        spec = importlib.util.spec_from_file_location(
            "fixture_dreo", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)]
        )
        integration = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = integration
        spec.loader.exec_module(integration)
        return (
            integration,
            sys.modules["fixture_dreo.coordinator"],
            sys.modules["fixture_dreo.rgbic"],
        )

    async def check_startup(self, failed):
        integration, coordinator_module, rgbic_module = self.load()
        hass = SimpleNamespace(
            config_entries=SimpleNamespace(async_forward_entry_setups=AsyncMock()),
            async_add_executor_job=AsyncMock(return_value={"fixture": "state"}),
        )
        client = SimpleNamespace(get_status=lambda serial: {})
        entry = SimpleNamespace(
            data={"username": "fixture-user", "password": "fixture-md5"}
        )
        device = {"deviceSn": "fixture-serial", "model": "DR-HCF002S"}
        coordinator = coordinator_module.DreoDataUpdateCoordinator(
            hass, client, "fixture-serial", "fixture", {}
        )

        def process(*args):
            data = coordinator_module.DreoCeilingFanDeviceData()
            data.available = True
            data.is_on = True
            data.light_state = True
            data.rgb_state = True
            data.rgb_brightness = 2
            return data

        coordinator.data_processor = process

        async def setup(hass, client, device, coordinators):
            coordinators[device["deviceSn"]] = coordinator

        integration.async_login = AsyncMock(return_value=(client, [device]))
        integration.async_setup_device_coordinator = setup
        initialization = (
            AsyncMock(side_effect=rgbic_module.RGBICError("fixture unavailable"))
            if failed
            else AsyncMock(return_value=False)
        )
        with patch.object(rgbic_module.RGBICClient, "initialize", new=initialization):
            self.assertTrue(await integration.async_setup_entry(hass, entry))
        self.assertIsNotNone(
            coordinator.rgbic_client, "exact model must never fall back to legacy RGB"
        )
        self.assertTrue(coordinator.data.available)
        self.assertTrue(coordinator.data.is_on)
        self.assertTrue(coordinator.data.light_state)
        self.assertIsNone(coordinator.data.rgb_state)
        hass.config_entries.async_forward_entry_setups.assert_awaited_once()
        # Unqualified adapter refuses writes before any transport/legacy SDK call.
        with self.assertRaises(rgbic_module.RGBICError):
            await coordinator.rgbic_client.command(brightness=40)

    async def test_optional_mobile_login_failure_preserves_fan_main(self):
        await self.check_startup(True)

    async def test_incomplete_capability_cannot_fall_back_to_legacy_rgb(self):
        await self.check_startup(False)
