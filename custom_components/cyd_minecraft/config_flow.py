"""UI setup: LAN connection only, with no API token or YAML changes."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DEFAULT_PORT, DOMAIN
from .hub import Hub, HubError


class CydMinecraftConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        errors = {}
        if user_input is not None:
            try:
                hub = Hub(async_get_clientsession(self.hass), user_input["host"], user_input["port"])
                await hub.snapshot()
            except ValueError:
                errors["base"] = "invalid_host"
            except HubError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_create_entry(title="CYD Minecraft", data=user_input)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("host"): str, vol.Required("port", default=DEFAULT_PORT): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535))}),
            errors=errors,
        )
