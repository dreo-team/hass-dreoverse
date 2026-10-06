"""Native protocol fakes for the external RGBIC fork; no cloud or HA calls."""

import ast
import importlib.util
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

spec = importlib.util.spec_from_file_location(
    "rgbic", Path(__file__).parents[1] / "custom_components/dreo/rgbic.py"
)
rgbic = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rgbic)


def effect(name="Constant", effect_id="fixture-effect"):
    return {
        "id": effect_id,
        "name": name,
        "referencedId": "fixture-template",
        "effectType": 0,
        "layouts": [
            {"colorList": ["#FFFFFF", "#FF0000"]},
            {
                "colorList": ["#FFFFFF"] * 17,
                "wholeColorList": ["#0066FF"],
                "currentSelected": "whole",
            },
        ],
    }


class PayloadTests(unittest.TestCase):
    def test_whole_color_clone_preserves_segments_and_catalog(self):
        original = effect()
        payload = rgbic.effect_payload("fixture-serial", original, "#0000ff")[0]
        layouts = payload["subEffects"][0]["layouts"]
        self.assertEqual(layouts[0], original["layouts"][0])
        self.assertEqual(layouts[1]["colorList"], original["layouts"][1]["colorList"])
        self.assertEqual(layouts[1]["wholeColorList"], ["#0000FF"])
        self.assertEqual(original["layouts"][1]["wholeColorList"], ["#0066FF"])
        self.assertEqual(payload["id"], "fixture-effect")
        self.assertEqual(payload["devicesn"], "fixture-serial")
        self.assertNotIn("devicesn", original)

    def test_color_refuses_nonconstant_or_missing_whole_layout(self):
        with self.assertRaises(rgbic.RGBICError):
            rgbic.effect_payload("fixture", effect("Chase"), "#0000FF")
        missing = effect()
        missing["layouts"] = [{"colorList": ["#FFFFFF"]}]
        with self.assertRaises(rgbic.RGBICError):
            rgbic.effect_payload("fixture", missing, "#0000FF")

    def test_observation_uses_current_native_id_not_requested_effect(self):
        catalog = {"basicEffects": [effect(), effect("Chase", "fixture-chase")]}
        self.assertEqual(
            rgbic.observed_effect(catalog, "fixture-chase"), ("Chase", None)
        )
        self.assertEqual(rgbic.observed_effect(catalog, "unknown"), (None, None))
        self.assertEqual(
            rgbic.observed_effect(catalog, "fixture-effect"), ("Constant", 0x0066FF)
        )


class NativeTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        c = rgbic.RGBICClient(
            None, "fixture-user", "fixture-already-md5", "fixture-serial"
        )
        c.enabled = True
        return c

    async def test_model_and_reported_capability_gate(self):
        c = self.client()
        c._request = AsyncMock(
            side_effect=[
                {"region": "NA", "access_token": "fixture-token"},
                {"list": [{"sn": "fixture-serial", "model": "DR-HCF003S"}]},
            ]
        )
        self.assertFalse(await c.initialize())
        self.assertEqual(
            c._request.call_args_list[0].kwargs["body"]["password"],
            "fixture-already-md5",
        )
        self.assertEqual(c._request.await_count, 2)

    async def test_exact_model_still_needs_rgbic_reported_field(self):
        c = self.client()
        c._request = AsyncMock(
            side_effect=[
                {"region": "NA", "access_token": "fixture-token"},
                {"list": [{"sn": "fixture-serial", "model": "DR-HCF002S"}]},
            ]
        )
        c._read_raw = AsyncMock(
            return_value=({"atmon": {"state": True}}, {"basicEffects": [effect()]})
        )
        self.assertFalse(await c.initialize())

    async def test_reported_rgbic_without_constant_remains_unqualified(self):
        c = self.client()
        c.enabled = False
        c._request = AsyncMock(
            side_effect=[
                {"region": "NA", "access_token": "fixture-token"},
                {"list": [{"sn": "fixture-serial", "model": "DR-HCF002S"}]},
            ]
        )
        c._read_raw = AsyncMock(
            return_value=(
                {"atmon": {"state": True}, "rgbeffectid": {"state": "fixture-chase"}},
                {"basicEffects": [effect("Chase", "fixture-chase")]},
            )
        )
        self.assertFalse(await c.initialize())
        c._power_brightness = AsyncMock()
        with self.assertRaises(rgbic.RGBICError):
            await c.command(brightness=40)
        c._power_brightness.assert_not_awaited()

    async def test_actual_catalog_and_mobile_state_enable_model(self):
        c = self.client()
        c._request = AsyncMock(
            side_effect=[
                {"region": "NA", "access_token": "fixture-token"},
                {"list": [{"sn": "fixture-serial", "model": "DR-HCF002S"}]},
            ]
        )
        c._read_raw = AsyncMock(
            return_value=(
                {"atmon": {"state": True}, "rgbeffectid": {"state": "fixture-effect"}},
                {"basicEffects": [effect()]},
            )
        )
        self.assertTrue(await c.initialize())
        self.assertEqual(c.effects, ["Constant"])

    async def test_command_posts_catalog_identifiers_then_reads_actual(self):
        c = self.client()
        c._read_raw = AsyncMock(
            return_value=({"atmon": {"state": True}}, {"basicEffects": [effect()]})
        )
        c._power_brightness = AsyncMock()
        c._request = AsyncMock(return_value={})
        c.read = AsyncMock(
            return_value={
                "on": True,
                "brightness": 40,
                "effect": "Constant",
                "color": 255,
            }
        )
        got = await c.command(brightness=40, color="#0000FF")
        self.assertEqual(got["color"], 255)
        c._power_brightness.assert_awaited_once_with({"atmon": True, "atmbri": 40})
        call = c._request.call_args
        self.assertEqual(call.args, ("POST", "/api/device/rgb-effect/edit/batch"))
        self.assertEqual(call.kwargs["body"][0]["id"], "fixture-effect")
        c.read.assert_awaited_once()

    async def test_mismatch_never_publishes_requested_color_or_replays(self):
        c = self.client()
        c._read_raw = AsyncMock(
            return_value=({"atmon": {"state": True}}, {"basicEffects": [effect()]})
        )
        c._power_brightness = AsyncMock()
        c._request = AsyncMock(return_value={})
        c.read = AsyncMock(
            return_value={"on": True, "brightness": 2, "effect": "Chase", "color": None}
        )
        with (
            patch.object(rgbic.asyncio, "sleep", new=AsyncMock()),
            self.assertRaises(rgbic.RGBICError),
        ):
            await c.command(brightness=40, color="#0000FF")
        self.assertEqual(c._request.await_count, 1)
        self.assertEqual(c._power_brightness.await_count, 1)
        self.assertEqual(c.read.await_count, 10)

    async def test_lost_effect_response_is_not_retried_or_accepted(self):
        c = self.client()
        c._read_raw = AsyncMock(
            return_value=({"atmon": {"state": True}}, {"basicEffects": [effect()]})
        )
        c._power_brightness = AsyncMock()
        c._request = AsyncMock(side_effect=rgbic.RGBICError("fixture lost response"))
        c.read = AsyncMock()
        with self.assertRaises(rgbic.RGBICError):
            await c.command(effect="Constant")
        self.assertEqual(c._request.await_count, 1)
        c.read.assert_not_awaited()

    async def test_wake_delay_and_off_are_rgb_only(self):
        c = self.client()
        c._read_raw = AsyncMock(
            return_value=({"atmon": {"state": False}}, {"basicEffects": [effect()]})
        )
        c._power_brightness = AsyncMock()
        c._request = AsyncMock(return_value={})
        c.read = AsyncMock(
            return_value={
                "on": True,
                "brightness": 50,
                "effect": "Constant",
                "color": None,
            }
        )
        with patch.object(rgbic.asyncio, "sleep", new=AsyncMock()) as sleep:
            await c.command(brightness=50, effect="Constant")
            sleep.assert_awaited_once_with(0.6)
        c.read = AsyncMock(
            return_value={
                "on": False,
                "brightness": 50,
                "effect": "Constant",
                "color": None,
            }
        )
        await c.command(on=False)
        self.assertEqual(c._power_brightness.call_args.args, ({"atmon": False},))

    async def test_invalid_brightness_or_catalog_changes_make_zero_writes(self):
        c = self.client()
        c._power_brightness = AsyncMock()
        c._read_raw = AsyncMock(return_value=({}, {"basicEffects": []}))
        with self.assertRaises(rgbic.RGBICError):
            await c.command(brightness=101)
        with self.assertRaises(rgbic.RGBICError):
            await c.command(effect="Constant")
        c._power_brightness.assert_not_awaited()


class Response:
    status = 200

    def __init__(self, payload):
        self.payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def json(self):
        return self.payload


class Socket:
    def __init__(self, serial):
        self.serial = serial
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def send_json(self, v):
        self.sent.append(v)

    async def receive_json(self):
        return {"devicesn": self.serial, "method": "control-reply"}


class Session:
    def __init__(self):
        self.requests = []
        self.sockets = []
        self.reply = {"code": 0, "data": {"fixture": True}}

    def request(self, method, url, **kwargs):
        self.requests.append((method, url, kwargs))
        return Response(self.reply)

    def ws_connect(self, url, **kwargs):
        socket = Socket("fixture-serial")
        self.sockets.append((url, kwargs, socket))
        return socket


class SessionProtocolTests(unittest.IsolatedAsyncioTestCase):
    async def test_raw_transport_exception_never_enters_traceback(self):
        session = Session()
        client = rgbic.RGBICClient(
            session, "fixture-user", "fixture-md5", "fixture-serial"
        )
        session.request = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("fixture-private-token")
        )
        try:
            await client._request("GET", "/api/device/rgb-effect/all/list")
        except rgbic.RGBICError as error:
            self.assertNotIn(
                "fixture-private-token", "".join(traceback.format_exception(error))
            )
        else:
            self.fail("expected communication failure")
        session.ws_connect = lambda *a, **kw: (_ for _ in ()).throw(
            RuntimeError("fixture-private-token")
        )
        try:
            await client._power_brightness({"atmon": True})
        except rgbic.RGBICError as error:
            self.assertNotIn(
                "fixture-private-token", "".join(traceback.format_exception(error))
            )
        else:
            self.fail("expected acknowledgement failure")

    async def test_native_http_shape_and_bounded_redirection(self):
        session = Session()
        client = rgbic.RGBICClient(
            session, "fixture-user", "fixture-md5", "fixture-serial"
        )
        client.token = "fixture-token"
        got = await client._request(
            "GET",
            "/api/device/rgb-effect/all/list",
            params={"devicesn": "fixture-serial"},
        )
        self.assertEqual(got, {"fixture": True})
        method, url, kwargs = session.requests[0]
        self.assertEqual(
            (method, url),
            ("GET", "https://app-api-us.dreo-tech.com/api/device/rgb-effect/all/list"),
        )
        self.assertEqual(kwargs["params"]["devicesn"], "fixture-serial")
        self.assertFalse(kwargs["allow_redirects"])
        self.assertEqual(kwargs["headers"]["authorization"], "Bearer fixture-token")
        self.assertIsNone(kwargs["json"])

    async def test_server_rejection_never_returns_payload_or_secret_error(self):
        session = Session()
        session.reply = {"code": 500003, "msg": "fixture-private-token"}
        client = rgbic.RGBICClient(
            session, "fixture-user", "fixture-md5", "fixture-serial"
        )
        with self.assertRaisesRegex(rgbic.RGBICError, "^RGBIC request rejected$"):
            await client._request("POST", "/api/device/rgb-effect/edit/batch", body=[])
        self.assertEqual(len(session.requests), 1)

    async def test_native_ws_shape_uses_rgb_only_and_never_effect_id_write(self):
        session = Session()
        client = rgbic.RGBICClient(
            session, "fixture-user", "fixture-md5", "fixture-serial"
        )
        client.token = "fixture-token"
        await client._power_brightness({"atmon": True, "atmbri": 40})
        url, kwargs, socket = session.sockets[0]
        self.assertEqual(url, "wss://wsb-us.dreo-tech.com/websocket")
        self.assertEqual(kwargs["params"]["accessToken"], "fixture-token")
        self.assertEqual(socket.sent[0]["devicesn"], "fixture-serial")
        self.assertEqual(socket.sent[0]["method"], "control")
        self.assertEqual(socket.sent[0]["params"], {"atmon": True, "atmbri": 40})
        with self.assertRaises(rgbic.RGBICError):
            await client._power_brightness({"poweron": True})
        with self.assertRaises(rgbic.RGBICError):
            await client._power_brightness({"rgbeffectid": "fixture"})
        self.assertEqual(len(session.sockets), 1)


class LightBoundaryTests(unittest.IsolatedAsyncioTestCase):
    def method(self, name):
        source = Path(__file__).parents[1] / "custom_components/dreo/light.py"
        tree = ast.parse(source.read_text())
        cls = next(
            n
            for n in tree.body
            if isinstance(n, ast.ClassDef) and n.name == "DreoRGBLight"
        )
        fn = next(
            n
            for n in cls.body
            if isinstance(n, ast.AsyncFunctionDef | ast.FunctionDef) and n.name == name
        )
        fn.decorator_list = []
        scope = {
            "Any": Any,
            "ATTR_BRIGHTNESS": "brightness",
            "ATTR_RGB_COLOR": "rgb_color",
            "ATTR_EFFECT": "effect",
            "RGB_MAX": 255,
            "RGBICError": rgbic.RGBICError,
            "HomeAssistantError": RuntimeError,
        }
        exec(
            compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), scope
        )
        return scope[name]

    async def test_actual_light_method_converts_40_percent_to_40_not_2(self):
        client = SimpleNamespace(command=AsyncMock())
        coordinator = SimpleNamespace(rgbic_client=client, async_refresh=AsyncMock())
        light = SimpleNamespace(coordinator=coordinator)
        await self.method("async_turn_on")(
            light, brightness=102, rgb_color=(0, 0, 255), effect="Constant"
        )
        client.command.assert_awaited_once_with(
            brightness=40, effect="Constant", color="#0000FF"
        )
        coordinator.async_refresh.assert_awaited_once()

    async def test_actual_light_off_uses_rgb_client_without_legacy_command(self):
        client = SimpleNamespace(command=AsyncMock())
        coordinator = SimpleNamespace(rgbic_client=client, async_refresh=AsyncMock())
        light = SimpleNamespace(coordinator=coordinator)
        await self.method("async_turn_off")(light)
        client.command.assert_awaited_once_with(on=False)

    async def test_actual_light_does_not_publish_after_unverified_command(self):
        client = SimpleNamespace(
            command=AsyncMock(side_effect=rgbic.RGBICError("fixture"))
        )
        coordinator = SimpleNamespace(rgbic_client=client, async_refresh=AsyncMock())
        with self.assertRaisesRegex(
            RuntimeError, "RGBIC command could not be verified"
        ):
            await self.method("async_turn_on")(
                SimpleNamespace(coordinator=coordinator), brightness=102
            )
        coordinator.async_refresh.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
