# T-Embed RPC Gateway User Guide

This guide explains how to operate the Docker gateway with the RPC-enabled
Momentum firmware on a LilyGO T-Embed CC1101 Plus. Firmware operation is also
documented in the
[firmware user guide](https://github.com/crimson1968/momentum-t-embed-cc1101-rpc/blob/webfs-rpc/docs/USER_GUIDE.md).

## System overview

```text
Browser or MCP client
        |
        v
Docker gateway -- USB serial --> T-Embed screen and buttons
        |
        +-- LAN HTTP -----------> T-Embed WebFS RPC
```

- **USB** carries screen frames and button presses.
- **Wi-Fi WebFS RPC** carries status, diagnostics, storage, and receive-only
  Sub-GHz jobs.
- **Traefik** provides LAN-only HTTPS at
  `https://tembed-gateway.myhomelabs.work/`.
- **AdGuard Home** resolves that name to the Traefik host on the LAN.

No OpenAI API key is required. The current deployment has no application login
and must remain restricted to the trusted LAN.

## Before opening the gateway

On the T-Embed:

1. Connect Wi-Fi.
2. Start **Web Filesystem** and leave it open.
3. Enable **qFlipper**.
4. Connect USB to the NAS.

On the NAS, qFlipper should create:

```text
/dev/ttyACM0
/dev/serial/by-id/usb-Flipper_Devices_Inc._Warp_FZESP32-if01
```

Verify it with:

```sh
ls -l /dev/ttyACM* /dev/serial/by-id/ 2>&1
```

The deployed stack maps `/dev/ttyACM0` to `/dev/tembed` in the container. Turn
on qFlipper before applying or recreating the stack; Docker cannot start a
container with a device path that does not currently exist.

## Open and check the web interface

Open:

```text
https://tembed-gateway.myhomelabs.work/
```

The page should show the device as reachable and USB as connected. The verified
combination is firmware `2.3.14`, RPC API `1.1`, `network_up: true`,
`webfs_running: true`, and an active USB screen frame.

The direct LAN alternative, when enabled in `compose.yaml`, is:

```text
http://192.168.178.81:8787/
```

## Web interface features

### Status and diagnostics

Use the status area to check firmware version, API version, Wi-Fi, uptime,
WebFS state, and whether a receive job is active. Diagnostics adds link and
memory information. Settings is read-only and reports locale, time format,
date format, and timezone state.

### USB remote control

The USB panel displays the device's logical 128 x 64 monochrome screen. Use the
direction buttons, OK, and Back to operate the current device menu. Short and
long presses are supported.

Button effects depend on the application currently open on the device. The
gateway does not replay a button automatically after a timeout or disconnect.

### Receive-only Sub-GHz jobs

Enter a frequency and duration, then start a receive job. The result contains
pulse counts, elapsed time, and peak RSSI. Only one receive job may run at a
time. Check the jobs/status panel before retrying a request that returned an
uncertain timeout or busy response.

The gateway exposes reception only. Sub-GHz transmit is disabled.

### SD-card files

The Files area operates inside `/ext`. It can list folders, download and upload
files, rename entries, create folders, and delete entries. Browser confirmations
are shown before overwrite and deletion. The current file-size limit is 2 MiB.

## MCP endpoint and tools

The external MCP endpoint is:

```text
https://tembed-gateway.myhomelabs.work/mcp
```

Docker services on the same network can use:

```text
http://tembed-gateway:8000/mcp
```

Available tools:

- `tembed_status`, `tembed_capabilities`, `tembed_settings`
- `tembed_diagnostics`
- `tembed_start_rx`, `tembed_job`, `tembed_jobs`, `tembed_cancel_job`
- `tembed_files_list`, `tembed_file_download`, `tembed_file_upload`
- `tembed_usb_connect`, `tembed_usb_screen`, `tembed_usb_button`

## Dockhand operation

The gateway is part of the `mcp-server` stack. When changing its configuration:

1. Confirm qFlipper is enabled and `/dev/ttyACM0` exists.
2. Open the `mcp-server` stack in Dockhand.
3. Validate the compose file.
4. Use **Save & redeploy** to recreate the container.
5. Wait for all stack containers to report running.
6. Reload the gateway page and verify both device and USB status.

A restart is insufficient after changing the image or device mapping; use a
rebuild/redeploy.

## Recommended Docker device mapping

Use long syntax. It avoids ambiguity when a `by-id` name contains colons:

```yaml
environment:
  TEMBED_URL: http://192.168.178.35
  TEMBED_SERIAL: /dev/tembed
devices:
  - source: /dev/ttyACM0
    target: /dev/tembed
    permissions: rw
group_add:
  - '20'
```

`/dev/ttyACM0` is reliable for this NAS while the T-Embed is its only ACM
device. If other ACM devices are added, use the current qFlipper `by-id` path in
long syntax and recreate the container whenever USB re-enumerates.

## Troubleshooting

### Bad Gateway

Check that `tembed-gateway` is running. A common cause is applying the stack
while `/dev/ttyACM0` does not exist. Enable qFlipper, verify the device path,
then redeploy.

### USB is not configured

Set `TEMBED_SERIAL=/dev/tembed` and map the host serial device to
`/dev/tembed`. Keep group `20` in `group_add`; the verified host device is owned
by `root:dialout` with mode `660`.

### USB is configured but not connected

Leave qFlipper enabled for several seconds. Confirm the device node still
exists. Recreate the container after unplugging the cable or changing USB mode.
Do not use qFlipper or the serial port from another application at the same
time.

### Device unreachable or timeout

This refers to Wi-Fi/WebFS, not USB. Confirm the T-Embed is connected to Wi-Fi,
start Web Filesystem, and test:

```powershell
Invoke-RestMethod 'http://192.168.178.35/api/status'
```

USB screen control may continue while WebFS is unavailable.

### Host or Origin not allowed

Include the public hostname in `MCP_ALLOWED_HOSTS`, including `:443` when used,
then recreate the gateway container.

### The hostname does not resolve or TLS is missing

AdGuard must rewrite `tembed-gateway.myhomelabs.work` to the Traefik LAN host.
Traefik must use the `websecure` entrypoint and the existing `cloudflare`
certificate resolver. See [HTTPS.md](HTTPS.md).

## Security and operational limits

- Keep the service LAN-only; do not add public port forwarding.
- There is no arbitrary-command endpoint.
- Radio RPC is receive-only; Sub-GHz transmit remains disabled.
- USB control operates the visible device UI and therefore can invoke whatever
  the user selects on the device. Review the screen before pressing controls.
- Wi-Fi, USB, and installed hardware still determine which firmware apps work.

## Related documentation

- [Gateway README](README.md)
- [USB setup](USB-SETUP.md)
- [LAN HTTPS setup](HTTPS.md)
- [Firmware repository](https://github.com/crimson1968/momentum-t-embed-cc1101-rpc)
- [Firmware WebFS RPC API](https://github.com/crimson1968/momentum-t-embed-cc1101-rpc/blob/webfs-rpc/docs/webfs-rpc.md)
