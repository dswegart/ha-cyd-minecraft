import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.exceptions import Unauthorized
from custom_components.cyd_minecraft import async_setup, ws_command, ws_snapshot
from custom_components.cyd_minecraft.hub import Hub, HubError, origin


def server(identifier, state="stopped", players=0):
    return {"id": identifier, "name": identifier, "state": state, "online_players": players}


class OriginTest(unittest.TestCase):
    def test_private_ip_only(self):
        self.assertEqual(origin("192.168.1.2", 8098), "http://192.168.1.2:8098")
        for host in ("127.0.0.1", "169.254.169.254", "8.8.8.8", "localhost", "https://example.com", "::1"):
            with self.subTest(host=host), self.assertRaises(ValueError):
                origin(host, 8098)

    def test_port_bounds(self):
        for port in (0, 65536, True):
            with self.assertRaises(ValueError):
                origin("192.168.1.2", port)


class AuthorizationTest(unittest.IsolatedAsyncioTestCase):
    async def test_non_admin_cannot_read_or_control(self):
        for command in (ws_snapshot, ws_command):
            for user in (None, SimpleNamespace(is_admin=False)):
                with self.subTest(command=command, user=user), self.assertRaises(Unauthorized):
                    command(SimpleNamespace(data={}), SimpleNamespace(user=user), {"id": 1})

    async def test_admin_snapshot_and_error(self):
        tasks = []
        hass = SimpleNamespace(data={"cyd_minecraft": {"entry": SimpleNamespace(snapshot=AsyncMock(return_value={"servers": []}))}}, async_create_background_task=lambda task, *a, **kw: tasks.append(asyncio.create_task(task)))
        connection = SimpleNamespace(user=SimpleNamespace(is_admin=True), send_result=Mock(), send_error=Mock())
        ws_snapshot(hass, connection, {"id": 1})
        await tasks.pop()
        connection.send_result.assert_called_once_with(1, {"servers": []})
        hass.data.clear()
        ws_snapshot(hass, connection, {"id": 2})
        await tasks.pop()
        self.assertEqual(connection.send_error.call_args.args[:2], (2, "cyd_unavailable"))

    async def test_command_schema_is_closed(self):
        schema = ws_command._ws_schema
        for action in ("shell", "restart", "delete"):
            with self.assertRaises(Exception):
                schema({"id": 1, "type": "cyd_minecraft/command", "action": action, "server_id": "abc"})
        with self.assertRaises(Exception):
            schema({"id": 1, "type": "cyd_minecraft/command", "action": "start", "server_id": "abc", "url": "http://example.com"})


class HubTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.hub = Hub(Mock(), "192.168.1.2", 8098)
        self.hub.write_server = AsyncMock()
        self.hub.wait_state = AsyncMock()
        self.hub.snapshot = AsyncMock(return_value={"servers": []})

    async def test_start_guard(self):
        self.hub.servers = AsyncMock(return_value=[server("old", "running"), server("new")])
        with self.assertRaises(HubError):
            await self.hub.command("start", "new")
        self.hub.write_server.assert_not_called()

    async def test_unknown_state_fails_closed(self):
        self.hub.servers = AsyncMock(return_value=[server("old", "unknown"), server("new")])
        with self.assertRaises(HubError):
            await self.hub.command("rotate", "new")
        self.hub.write_server.assert_not_called()

    async def test_players_require_confirmation(self):
        for players in (2, None):
            self.hub.servers = AsyncMock(return_value=[server("old", "running", players), server("new")])
            with self.assertRaises(HubError):
                await self.hub.command("rotate", "new")
        self.hub.write_server.assert_not_called()

    async def test_rotation_order_and_confirmed_stop(self):
        self.hub.servers = AsyncMock(side_effect=[[server("old", "running", 2), server("new")], [server("old"), server("new")]])
        events = []
        self.hub.write_server.side_effect = lambda identifier, action, allow_players=False: events.append((identifier, action))
        self.hub.wait_state.side_effect = lambda identifier, state: events.append((identifier, state))
        await self.hub.command("rotate", "new", allow_players=True)
        self.assertEqual(events, [("old", "stop"), ("old", "stopped"), ("new", "start"), ("new", "running")])
        self.assertEqual(self.hub.write_server.await_args_list[0].args, ("old", "stop", True))

    async def test_failed_stop_never_starts_new_world(self):
        self.hub.servers = AsyncMock(return_value=[server("old", "running"), server("new")])
        self.hub.wait_state.side_effect = HubError("timeout")
        with self.assertRaises(HubError):
            await self.hub.command("rotate", "new")
        self.hub.write_server.assert_awaited_once_with("old", "stop", False)

    async def test_port_recheck_before_start(self):
        self.hub.servers = AsyncMock(side_effect=[[server("old"), server("new")], [server("old", "running"), server("new")]])
        with self.assertRaises(HubError):
            await self.hub.command("start", "new")
        self.hub.write_server.assert_not_called()

    async def test_stop_idempotent(self):
        self.hub.servers = AsyncMock(return_value=[server("new")])
        await self.hub.command("stop", "new")
        self.hub.write_server.assert_not_called()

    async def test_arbitrary_request_is_rejected(self):
        with self.assertRaises(HubError):
            await self.hub.request("/api/secrets")

    async def test_control_uses_exact_identifier_without_picker(self):
        hub = Hub(Mock(), "192.168.1.2", 8098)
        hub.request = AsyncMock(return_value={})
        identifier = "11111111-2222-3333-4444-555555555555"
        await hub.write_server(identifier, "stop", True)
        hub.request.assert_awaited_once_with(f"/api/crafty/servers/{identifier}/stop", "POST", data={"allow_players": True})

    async def test_control_rejects_path_injection(self):
        hub = Hub(Mock(), "192.168.1.2", 8098)
        hub.request = AsyncMock()
        for identifier in ("../selected", "abc", "11111111-2222-3333-4444-555555555555/start"):
            with self.assertRaises(HubError):
                await hub.write_server(identifier, "start")
        hub.request.assert_not_called()

    async def test_request_allowlist_and_body_are_closed(self):
        path = "/api/crafty/servers/11111111-2222-3333-4444-555555555555/stop"
        for request_path, method, data in ((path, "GET", None), (path, "POST", None),
                (path, "POST", {"allow_players": "yes"}), (path, "POST", {"allow_players": True, "url": "x"}),
                ("/api/crafty/selected/stop", "POST", None), ("/api/crafty/servers", "GET", {})):
            with self.assertRaises(HubError):
                await self.hub.request(request_path, method, data=data)
        self.hub.session.request.assert_not_called()

    async def test_wait_checks_fresh_state_without_retrying_write(self):
        hub = Hub(Mock(), "192.168.1.2", 8098)
        hub.servers = AsyncMock(side_effect=[[server("new")], [server("new", "running")]])
        with patch("custom_components.cyd_minecraft.hub.asyncio.sleep", new_callable=AsyncMock) as sleep:
            await hub.wait_state("new", "running")
        sleep.assert_awaited_once_with(5)

    async def test_payload_strips_unrelated_values_and_unknown_flags(self):
        hub = Hub(Mock(), "192.168.1.2", 8098)
        hub.request = AsyncMock(return_value={"servers": [{**server("a", "unknown"), "token": "never-forward", "can_start": True}]})
        values = await hub.servers()
        self.assertNotIn("token", values[0])
        self.assertFalse(values[0]["can_start"])


if __name__ == "__main__":
    unittest.main()
