# RPC Gateway for Momentum T-Embed CC1101 RPC

Docker gateway for the
[`momentum-t-embed-cc1101-rpc`](https://github.com/crimson1968/momentum-t-embed-cc1101-rpc)
firmware running on a LilyGO T-Embed CC1101 Plus.

The gateway exposes the firmware RPC API through MCP and includes a small web
interface. It can reach the device through its Wi-Fi Web Filesystem API and can
optionally map the USB serial device for screen and button control.

## How the two repositories fit together

This repository is the **host-side companion** to
[`momentum-t-embed-cc1101-rpc`](https://github.com/crimson1968/momentum-t-embed-cc1101-rpc),
which contains the ESP32 firmware and implements the Web Filesystem RPC API.
Install that firmware on the T-Embed first; this gateway runs separately on a
NAS, home server, or other Docker host.

```text
MCP client / browser
        |
        v
this Docker gateway  -- USB serial -->  T-Embed screen and buttons
        |
        +-- private-LAN HTTP ------->  firmware Web Filesystem RPC
```

The connection methods complement each other:

- **Wi-Fi RPC** provides status, capabilities, diagnostics, receive-only
  Sub-GHz jobs, and SD-card operations. The device must be connected to Wi-Fi
  with **Web Filesystem** running.
- **USB serial** provides the live device screen and button control and remains
  useful when the Web Filesystem service is stopped.
- **MCP and the web UI** present those device functions to clients; they do not
  emulate the firmware or replace the applications installed on the T-Embed.

The shared intent is controlled remote access to the user's own device on a
trusted private LAN. The radio RPC stays receive-only, and neither repository
adds an arbitrary-command endpoint.

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

