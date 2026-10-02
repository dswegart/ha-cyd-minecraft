# CYD Minecraft bridge

This is a generic Home Assistant integration, not the private CYD application or
home-platform control plane. Never add household addresses, credentials, family
details, runtime configuration, or private project files to this repository.

Preserve backend `require_admin` on both WebSocket commands, the closed operation
allowlist, private-IP validation, redirect rejection, unknown-state denial,
player confirmation and stop-before-start sequencing. Do not add browser-to-LAN
fetches, public CYD routes, secret-handling logic, or general-purpose HTTP/shell APIs.

Run Python tests against the target HA version and Node card tests before publication.
Rebuild the checked-in self-contained card with `npm run build`; retain dependency
licenses. Live activation is a separate HA/HACS transaction with its own preflight,
explicit restart impact, saved dashboard/resource rollback, and post-state evidence.
