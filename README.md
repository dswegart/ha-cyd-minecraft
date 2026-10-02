# CYD Minecraft for Home Assistant

Admin-only Minecraft server controls using an existing LAN CYD Control Hub.
The dashboard talks through Home Assistant's authenticated WebSocket, so it works
wherever your normal HA access works. No public CYD endpoint, CORS bypass, proxy
credentials, or browser-to-LAN HTTP request is needed.

## Install

1. Add this repository in HACS as an **Integration**, and download it.
2. Restart Home Assistant once to discover the integration.
3. Add **CYD Minecraft** in Devices & Services. Enter your hub's private LAN IPv4
   address and port (default 8098). No token is requested or stored.
4. Register `dashboard/minecraft-cyd-card.js` as a Lovelace module, or use its
   source as an inline dashboard resource. Add `custom:minecraft-cyd-card`.

Card configuration accepts `join_host`, `join_port`, `join_name`, and
`refresh_seconds`. The join endpoint is shared by the worlds you rotate on the hub.
The QR code is generated locally, with a four-module quiet zone, and opens the
Minecraft add-server link on compatible mobile devices. It is not an Xbox
one-tap join mechanism; consoles may require their usual custom-server workaround.

## Safety and behavior

- Both read and control commands require an authenticated HA administrator at
  the backend; hiding a dashboard is not the security check.
- Only five fixed CYD operations are allowed. Clients cannot submit arbitrary
  HTTP paths, hosts, URLs, credentials, or shell commands.
- The setup accepts only RFC1918 IPv4 literals and disables HTTP redirects.
- Start refuses shared-port conflicts. Switch stops the previous world, waits
  for a confirmed stopped state, and only then starts the selected world.
- Stop/switch require confirmation when players might be present. Unknown
  server state fails closed. Writes are not automatically retried.
- Operations are serialized within this bridge. Legacy CYD uses a global
  picker; avoid simultaneous physical CYD/Crafty controls while a HA switch is
  in progress. The bridge checks the selected ID immediately before each write,
  but the old CYD protocol does not support atomic target-ID commands.
- Health means the CYD-to-Crafty read path works and reports server state/player
  counts, not a claim that a disconnected physical screen is healthy.

## Validation and rollback

Tests use the actual installed HA version, not stubbed authorization decorators:

```sh
python -m unittest discover -s tests -v
node --test tests/card.test.cjs
```

To roll back, disable the CYD Minecraft config entry and restore your saved
dashboard/resource. This stops its requests immediately without a restart or
world deletion. HACS removal is optional; code already loaded remains in memory
until a later HA restart. Keep CYD's original image and world data unchanged.
