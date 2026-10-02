"""Closed, credential-free client for the LAN CYD Minecraft API."""

from __future__ import annotations

import asyncio
import ipaddress
from typing import Any

import aiohttp


class HubError(Exception):
    """A safe, user-facing control error (never raw network or secret data)."""


def origin(host: str, port: int) -> str:
    """Accept only an RFC1918 IP literal; never an arbitrary URL or hostname."""
    address = ipaddress.ip_address(host)
    networks = ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
    if not any(address in ipaddress.ip_network(network) for network in networks):
        raise ValueError("Use a private LAN IPv4 address")
    if isinstance(port, bool) or not 1 <= port <= 65535:
        raise ValueError("Invalid port")
    return f"http://{address}:{port}"


class Hub:
    """All actions run server-side; no credentials reach the frontend."""

    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self.session = session
        self.base_url = origin(host, port)
        self.lock = asyncio.Lock()

    async def request(self, path: str, method: str = "GET") -> dict[str, Any]:
        allowed = {
            ("GET", "/api/crafty/servers"),
            ("GET", "/api/crafty/selected"),
            ("POST", "/api/crafty/select/next"),
            ("POST", "/api/crafty/selected/start"),
            ("POST", "/api/crafty/selected/stop"),
        }
        if (method, path) not in allowed:
            raise HubError("Unsupported CYD operation")
        try:
            async with self.session.request(
                method, self.base_url + path,
                timeout=aiohttp.ClientTimeout(total=10),
                allow_redirects=False,
                headers={"Accept": "application/json"},
            ) as response:
                if response.status >= 300:
                    raise HubError(f"CYD rejected the request (HTTP {response.status})")
                payload = await response.json()
                if not isinstance(payload, dict):
                    raise HubError("CYD returned invalid server data")
                return payload
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as error:
            raise HubError("Cannot reach CYD. Check the hub and its credential adapter.") from error

    async def servers(self) -> list[dict[str, Any]]:
        payload = await self.request("/api/crafty/servers")
        items = payload.get("servers")
        if not isinstance(items, list):
            raise HubError("CYD returned invalid server data")
        result = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                raise HubError("CYD returned invalid server data")
            state = item.get("state", "unknown")
            if state not in ("running", "stopped", "unknown"):
                state = "unknown"
            count = item.get("online_players")
            result.append({
                "id": item["id"], "name": str(item.get("name", "Minecraft")),
                "state": state,
                "online_players": count if isinstance(count, int) and not isinstance(count, bool) and count >= 0 else None,
                "can_start": state == "stopped", "can_stop": state == "running",
            })
        return result

    async def snapshot(self) -> dict[str, Any]:
        servers = await self.servers()
        selected = (await self.request("/api/crafty/selected")).get("server")
        selected_id = selected.get("id") if isinstance(selected, dict) else None
        return {"servers": servers, "selected_id": selected_id, "connected": True}

    @staticmethod
    def target(servers: list[dict[str, Any]], server_id: str) -> dict[str, Any]:
        target = next((item for item in servers if item["id"] == server_id), None)
        if target is None:
            raise HubError("That server is no longer available. Refresh the list.")
        if target["state"] == "unknown":
            raise HubError("Server state is unknown; refusing to change it.")
        return target

    async def select(self, server_id: str, count: int) -> None:
        """Use the legacy CYD picker, bounded by the known server count."""
        for _ in range(count + 1):
            selected = (await self.request("/api/crafty/selected")).get("server")
            if isinstance(selected, dict) and selected.get("id") == server_id:
                return
            await self.request("/api/crafty/select/next", "POST")
        raise HubError("CYD selection changed. Refresh and try again.")

    async def write_selected(self, server_id: str, action: str, count: int) -> None:
        await self.select(server_id, count)
        selected = (await self.request("/api/crafty/selected")).get("server")
        if not isinstance(selected, dict) or selected.get("id") != server_id:
            raise HubError("CYD selection changed; no command was sent.")
        await self.request(f"/api/crafty/selected/{action}", "POST")

    async def wait_state(self, server_id: str, state: str) -> None:
        for _ in range(25):
            if self.target(await self.servers(), server_id)["state"] == state:
                return
            await asyncio.sleep(1)
        raise HubError("Server transition not confirmed yet. Refresh before retrying.")

    @staticmethod
    def check_players(server: dict[str, Any], allow_players: bool) -> None:
        if not allow_players and server["online_players"] != 0:
            raise HubError("Players may be connected. Confirm before stopping this world.")

    async def command(self, action: str, server_id: str, allow_players: bool = False) -> dict[str, Any]:
        if action not in ("start", "stop", "rotate"):
            raise HubError("Unsupported Minecraft action")
        async with self.lock:
            servers = await self.servers()
            target = self.target(servers, server_id)
            if action != "stop" and any(item["state"] == "unknown" for item in servers):
                raise HubError("A server has unknown state; shared-port safety cannot be verified.")
            running = [item for item in servers if item["state"] == "running" and item["id"] != server_id]
            if action == "start" and running:
                raise HubError("Another world is live. Use Switch to this world instead.")
            if action == "rotate":
                # Check every occupant before stopping any, so this cannot partially
                # interrupt players and then discover another unconfirmed server.
                for item in running:
                    self.check_players(item, allow_players)
                for item in running:
                    await self.write_selected(item["id"], "stop", len(servers))
                    await self.wait_state(item["id"], "stopped")
            if action == "stop" and target["state"] == "running":
                self.check_players(target, allow_players)
                await self.write_selected(server_id, "stop", len(servers))
                await self.wait_state(server_id, "stopped")
            elif action in ("start", "rotate") and target["state"] != "running":
                # Re-check port occupants after stop confirmations; never start on
                # a stale snapshot or automatically retry a timed-out write.
                fresh = await self.servers()
                if any(item["id"] != server_id and item["state"] != "stopped" for item in fresh):
                    raise HubError("Shared port is not clear; the selected world was not started.")
                await self.write_selected(server_id, "start", len(fresh))
                await self.wait_state(server_id, "running")
            result = await self.snapshot()
            result["message"] = "World stopped" if action == "stop" else "Selected world is live"
            return result
