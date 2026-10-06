# Agent Handoff

## Repository and Git State

- Repository: `crimson1968/RPC-Gateway_for_momentum-t-embed-cc1101-rpc`
- Branch: `main`. Use `git log -1 --oneline` for the current HEAD.
- HEAD `e1d13e3` ("Organize gateway browser UI into tabs") is pushed to
  `origin/main`. The Wi-Fi Remote transport and the tab redesign are both live.

## Current Objective

Add a **Wi-Fi Remote** transport to the gateway: the same Flipper GUI RPC that
`usb_remote.py` speaks, carried over the firmware's WebSocket endpoint
(`ws://<device>:80/rpc?token=...`) instead of USB. Gives screen streaming and
button control over Wi-Fi with no USB cable. Pairs with the firmware's
"Wi-Fi Remote" feature, now fully on `crimson1968/momentum-t-embed-cc1101-rpc`
`main`: stage 1 (WebSocket-to-RPC bridge, PR #5) and stage 2 (auto-recovery /
"Return Home" dead-man's switch, PR #4, merge commit `d134d42`). The merged
feature branches (`feature/wifi-remote`, `wifi-remote-stage1`) and the
`feature/low-battery-shutdown` branch have been deleted; that repo's local and
remote state is just `main`.

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
- Live end-to-end (transport, from inside the deployed `tembed-gateway`
  container): `WifiRemote.connect()` resolved `ws://192.168.178.35:80/rpc` with
  token `VN0SD3IF`, returned `connected: True`, and `snapshot()` delivered a
  1368-byte screen frame. `key("down")` and `key("up")` each returned `{ok: True}`
  and the frame hash changed in response, confirming the input path. Clean
  `close()`.
- Live end-to-end (browser UI, at `tembed-gateway.myhomelabs.work`, Remote
  control tab): "Connect Wi-Fi" → badge "Wi-Fi: Connected", the device Browser
  menu mirrored in the canvas; pressing ↑ moved the on-screen selection
  (version.txt → README.md); "Disconnect" returned to "Wi-Fi: Not connected".
- `git diff` reviewed before commit: only `web.html` + `HANDOFF.md` changed in the
  tab commit; no secrets committed (token is an env reference, never a literal).

## Known Issues / Notes

- Requires the device's "Wi-Fi Remote" feature to be running to serve; the token
  must match. The gateway container cannot start without the mapped USB device
  (`/dev/ttyACM0`); run the gateway where the device is attached, or adjust the
  compose `devices:` mapping if running Wi-Fi-only.
- Firmware context: this port's desktop suspends Wi-Fi when any app launches, so
  remote control works on the desktop/menus. Stage 2 adds an auto-recovery
  dead-man's switch (recovery timer + "Return Home") for when a launched app
  seizes the radio and the link drops. The app-exit half works; the "Return
  Home" auto-reconnect is unreliable (`wlan_hal` resume) and currently recovers
  only via a reboot — tracked as firmware issue
  `crimson1968/momentum-t-embed-cc1101-rpc#6`.

## Deployment (done)

- Stack: `mcp-server`, service `tembed-gateway`, on the NAS at
  `/volume2/docker/dockhand/stacks/Ugreen-NAS/mcp-server/`.
- `compose.yaml` build context pinned to
  `...RPC-Gateway...git#e1d13e334c6294fc3a351e8fe5a727719b6bf483` (a timestamped
  `compose.yaml.bak-*` backup sits beside it). `.env` holds
  `TEMBED_REMOTE_TOKEN=VN0SD3IF`; container env also has
  `TEMBED_URL=http://192.168.178.35`.
- Redeployed via `docker compose -p mcp-server build tembed-gateway` then
  `up -d tembed-gateway`. Live tab UI + Wi-Fi Remote verified (see above).

## Recommended Next Action

- Nothing outstanding for this task. For future gateway changes, redeploy by
  bumping the pinned SHA in the `mcp-server` compose, then
  `docker compose -p mcp-server build tembed-gateway && ... up -d tembed-gateway`
  (or Dockhand "Save & redeploy").
- Operational prerequisite for Wi-Fi Remote at runtime: the device must be
  running its "Wi-Fi Remote" feature and the token must match `TEMBED_REMOTE_TOKEN`.
