# USB device remote + LAN HTTPS

## Install on your NAS

1. Copy all package files (including .dockerignore) into
   /volume2/docker/tembed-gateway/, replacing the old versions.
2. In the mcp-stack replace only tembed-gateway using compose.traefik-lan.yaml.
   Keep the existing other services and proxy network. This variant removes the
   direct port 8787 and uses Traefik HTTPS instead.
3. Keep qFlipper enabled on the device. The current deployment uses
   /dev/ttyACM0. qFlipper also exposes the verified stable name
   /dev/serial/by-id/usb-Flipper_Devices_Inc._Warp_FZESP32-if01.
   Device permissions: group 20, mode 660. Compose maps the ACM device to /dev/tembed
   and adds group 20 to the non-root container. No privileged mode needed.
4. Rebuild and redeploy the gateway in Dockhand. Restart alone does not rebuild.
   Dockhand build context /build/tembed-gateway must remain mounted.
5. Add AdGuard DNS rewrite for tembed-gateway.myhomelabs.work to your Traefik LAN
   IP. The existing Dockhand hostname resolved to 192.168.178.224; confirm this
   is the Traefik address. It is not necessarily the NAS address .81.
6. Open https://tembed-gateway.myhomelabs.work/ and press USB verbinden.

If retaining port 8787 initially, use compose.yaml instead (NAS_LAN_IP=.81 in
full address form 192.168.178.81). It includes the same USB mapping but no Traefik.

## Available controls

- USB screen (128x64 logical monochrome display) and up/down/left/right/OK/back,
  short or long press. Use the actual device menu to reach installed applications.
- MCP: tembed_usb_connect, tembed_usb_screen and tembed_usb_button.
  Button effects depend on the active application; no automatic retries.
- Existing Wi-Fi RX status/statistics tools remain unchanged.
- WebFS files: list, upload/download (2 MiB limit), rename, create folder and
  recursive delete. The browser asks before overwrite/delete. No file execution.
- MCP SD directory listing: tembed_files_list.

USB control does not require WebFS, but RX statistics and SD file operations in
this version still use WebFS over Wi-Fi. Leaving the WebFS app can therefore
make those panels report device errors while USB control keeps working.

## Important limits

This is remote operation of the device UI, not a reimplementation of every app
or a guarantee that every app works on this board. No new RF/NFC drivers or
unimplemented firmware capabilities have been invented. App-specific automation
beyond existing RX is not provided by dedicated APIs in this update.

USB storage, BadUSB/HID, reboot and disabling qFlipper can take over/disconnect
USB. After re-enumeration, re-enable qFlipper and recreate the gateway container
so Docker remaps the current device node. Stable by-id naming does not make
Docker device mappings automatically follow hotplug. No automatic reconnection
or button replay is attempted. Disconnecting may make firmware leave qFlipper
mode after its grace period. Do not use another serial application simultaneously.

A screen frame may be stale; USB connection state and frame timestamp are
reported. An unsupported frame size is an error rather than a guessed rendering.
All browser users share one USB session. Wi-Fi/Bluetooth functions may disconnect
WebFS. Installed hardware and firmware still determine which apps work.

## HTTPS

See HTTPS.md. LAN-only middleware permits 192.168.178.0/24, without login.
No public port forwarding is required. Existing Traefik cloudflare resolver
must be configured for DNS-01 and have its existing credentials. We did not
modify AdGuard, Traefik or deploy to your NAS from this workspace.

## Validation

Eight local tests pass: five HTTP/UI tests and three USB/path tests, including
fake serial handshake, fragmented protobuf input, screen frame and press/short/
release sequence. JavaScript syntax checked. Docker image built. The NAS
deployment, LAN HTTPS, firmware API 1.1, and real USB screen stream were verified
on 2026-10-02. No RF transmission is exposed or used by these checks.
