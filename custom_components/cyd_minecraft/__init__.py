"""Authenticated, admin-only Minecraft controls through HA's own WebSocket."""

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN
from .hub import Hub, HubError


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    websocket_api.async_register_command(hass, ws_snapshot)
    websocket_api.async_register_command(hass, ws_command)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = Hub(
        async_get_clientsession(hass), entry.data["host"], entry.data["port"],
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    return True


def get_hub(hass: HomeAssistant) -> Hub:
    hubs = hass.data.get(DOMAIN, {})
    if len(hubs) != 1:
        raise HubError("Configure the CYD Minecraft integration in Devices & Services.")
    return next(iter(hubs.values()))


@websocket_api.websocket_command({vol.Required("type"): "cyd_minecraft/snapshot"})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_snapshot(hass, connection, msg):
    try:
        connection.send_result(msg["id"], await get_hub(hass).snapshot())
    except HubError as error:
        connection.send_error(msg["id"], "cyd_unavailable", str(error))


@websocket_api.websocket_command({
    vol.Required("type"): "cyd_minecraft/command",
    vol.Required("action"): vol.In(("start", "stop", "rotate")),
    vol.Required("server_id"): str,
    vol.Optional("allow_players", default=False): bool,
})
@websocket_api.require_admin
@websocket_api.async_response
async def ws_command(hass, connection, msg):
    try:
        result = await get_hub(hass).command(msg["action"], msg["server_id"], msg["allow_players"])
        connection.send_result(msg["id"], result)
    except HubError as error:
        connection.send_error(msg["id"], "cyd_command_failed", str(error))
