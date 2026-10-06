# Agent Handoff

## Repository and Git State

- Repository: `crimson1968/RPC-Gateway_for_momentum-t-embed-cc1101-rpc`
- Branch: `main`. Use `git log -1 --oneline` for the current HEAD.
- Local commit pending for the work below; not yet pushed (awaiting user authorization).

## Current Objective

Add a **Wi-Fi Remote** transport to the gateway: the same Flipper GUI RPC that
`usb_remote.py` speaks, carried over the firmware's WebSocket endpoint
(`ws://<device>:80/rpc?token=...`) instead of USB. Gives screen streaming and
button control over Wi-Fi with no USB cable. Pairs with the firmware's new
"Wi-Fi Remote" feature (merged in the firmware repo, PR #5 / commit on `main`).

## Completed Work

- `wifi_remote.py` (new): `WifiRemote` class mirroring `UsbRemote`'s interface
  (`connect` / `snapshot` / `key` / `close`). Stdlib-only masked-frame WebSocket
  client; reuses `usb_remote.py`'s protobuf framing helpers. No new dependency.
  Config from `TEMBED_REMOTE_TOKEN` (+ `TEMBED_URL` or `TEMBED_REMOTE_URL`).
- `gateway.py`: three MCP tools `tembed_wifi_connect` / `tembed_wifi_screen` /
  `tembed_wifi_button`, added in `make_server` (local import of `WifiRemote`).
- `Dockerfile`: `wifi_remote.py` added to the COPY list (required for the image).
- `compose.yaml`, `compose.traefik-lan.yaml`: optional `TEMBED_REMOTE_TOKEN`
  env (empty = Wi-Fi tools disabled).
- `README.md`: Features, MCP tools, Wi-Fi Remote configuration, Main files.
- Browser UI (`web_ui.py` / `web.html`): `/ui/api/wifi` GET+POST routes and a
  "Connect Wi-Fi" button in the remote-control card. USB and Wi-Fi share the same
  screen canvas and keys via a `remoteTransport` variable.
- Browser UI redesigned into four tabs (`web.html` only, no JS/route changes):
  **Remote control** (USB/Wi-Fi shared screen + keys), **Reception** (start RX +
  result), **Device** (Wi-Fi/WebFS status, settings, diagnostics, capabilities),
  **SD card**. All element IDs and the existing script are unchanged; a small
  `showTab()` toggles `.tab-panel` visibility. Polling runs regardless of the
  active tab. The Wi-Fi Remote feature was already fully present (screen stream +
  all buttons); it was just buried in the old single-column layout.

## Tests and Verification

- `pytest tests/test_gateway.py` → 2 passed (run in a `python:3.11-slim`
  container on the NAS host with `requirements-docker-lock.txt` + pytest; the PC
  has no local Python and the NAS host lacks `ensurepip`).
- Tab redesign verified visually in the browser pane (tabs switch; each panel
  shows its own cards; no console/layout breakage).
- Live end-to-end: ran `wifi_remote.py` against the device (192.168.178.35, token
  on the Wi-Fi Remote screen) from the NAS host; WebSocket handshake + token auth
  succeeded and a 1024-byte screen frame streamed back. The firmware bridge itself
  was separately validated (stable screen stream).
- `git diff` reviewed: only the files listed above changed; no secrets committed
  (token is an env reference, never a literal).

## Known Issues / Notes

- Requires the device's "Wi-Fi Remote" feature to be running to serve; the token
  must match. The gateway container cannot start without the mapped USB device
  (`/dev/ttyACM0`); run the gateway where the device is attached, or adjust the
  compose `devices:` mapping if running Wi-Fi-only.
- Firmware context: this port's desktop suspends Wi-Fi when any app launches, so
  remote control works on the desktop/menus; driving a running app needs the
  firmware "stage 2b" work (out of scope here).

## Recommended Next Action

1. Rebuild/redeploy the gateway image (Dockhand) so `wifi_remote.py` is included
   and the new UI/tools ship. Set `TEMBED_REMOTE_TOKEN` in the stack env.
2. On the device, start "Wi-Fi Remote"; then test the browser "Connect Wi-Fi"
   button and the `tembed_wifi_*` MCP tools end to end.
