# RPC Gateway for Momentum T-Embed CC1101 RPC

Docker gateway for the
[`momentum-t-embed-cc1101-rpc`](https://github.com/crimson1968/momentum-t-embed-cc1101-rpc)
firmware running on a LilyGO T-Embed CC1101 Plus.

The gateway exposes the firmware RPC API through MCP and includes a small web
interface. It can reach the device through its Wi-Fi Web Filesystem API and can
optionally map the USB serial device for screen and button control.

## Features

- Streamable HTTP MCP transport on port `8000`
- Browser-based status and control interface
- Firmware status, capabilities and diagnostics
- Receive-only Sub-GHz job support
- SD-card file access through the firmware RPC endpoints
- Optional USB screen and button remote control
- Docker hardening: read-only filesystem, dropped capabilities and process limit
- LAN-only Traefik example with TLS and an IP allowlist
- No OpenAI API key required

Radio control remains receive-only. The gateway does not add RF transmission or
an arbitrary-command interface.

## Quick start

The device must run the matching patched firmware. For Wi-Fi functions, connect
the T-Embed to the LAN and start **Web Filesystem** on the device.

1. Copy this repository to the Docker host.
2. Adjust the device URL, USB path and LAN address in `compose.yaml` if needed.
3. Start it with Docker Compose:

   ```text
   docker compose up -d --build
   ```

4. Open `http://<NAS-IP>:8787/`.

The included defaults match the original installation:

- Device URL: `http://192.168.178.35`
- USB mapping: `/dev/serial/by-id/usb-Flipper_Devices_Inc._Warp_FZESP32-if01`
- Container USB path: `/dev/tembed`
- Serial device group: `20`

Set `NAS_LAN_IP` in the stack environment before applying `compose.yaml`.

## Traefik and AdGuard

Use `compose.traefik-lan.yaml` for the existing LAN-only HTTPS deployment. It
publishes `tembed-gateway.myhomelabs.work` through the external `proxy` network,
uses the `cloudflare` certificate resolver, and allows only
`192.168.178.0/24`.

Create an AdGuard DNS rewrite for the hostname pointing to the Traefik host.
See [HTTPS.md](HTTPS.md) and [USB-SETUP.md](USB-SETUP.md) for the full setup.

## Main files

- `gateway.py` — MCP server and firmware API client
- `web_ui.py` / `web.html` — local web interface
- `usb_remote.py` — optional USB remote support
- `web_files.py` — WebFS file operations
- `Dockerfile` — container image
- `compose.yaml` — direct LAN port deployment
- `compose.traefik-lan.yaml` — LAN-only HTTPS deployment

## Security model

The intended deployment is a trusted private LAN. The Traefik example restricts
requests to the configured LAN subnet. There is no application login. Do not
publish this service directly to the internet.

