"""Receive-only T-Embed MCP bridge. stdio or local-network Streamable HTTP."""
from __future__ import annotations

import argparse
import asyncio
import base64
import ipaddress
import json
import os
from typing import Annotated, Literal
from urllib.parse import urlsplit

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import BaseModel, ConfigDict, Field, ValidationError

UInt = Annotated[int, Field(strict=True, ge=0, le=4294967295)]
JobId = Annotated[int, Field(strict=True, ge=1, le=4294967295)]
Duration = Annotated[int, Field(strict=True, ge=100, le=60000)]
Frequency = Annotated[int, Field(strict=True, ge=281000000, le=962000000)]
ShortText = Annotated[str, Field(max_length=128)]
Base64File = Annotated[str, Field(max_length=2796204)]


class DeviceModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="ignore", allow_inf_nan=False)


class Status(DeviceModel):
    device: ShortText
    board_id: Literal["t-embed"]
    firmware: ShortText
    idf_version: ShortText
    api_version: Literal["1.1"]
    uptime_ms: Annotated[int, Field(ge=0)]
    network_mode: Literal["ap", "sta"]
    network_up: bool
    ip: Annotated[str, Field(max_length=45)]
    webfs_running: bool
    busy: bool
    active_job_id: UInt


class Capabilities(DeviceModel):
    api_version: Literal["1.1"]
    read_only: bool
    radio_read_only: Literal[True]
    storage_write: bool
    subghz_rx: bool
    subghz_tx: Literal[False]
    protocol_decode: Literal[False]
    raw_file_capture: Literal[False]
    ir_rx: Literal[False]
    nfc_read: Literal[False]
    preset: Literal["OOK650Async"]
    result: Literal["pulse_statistics_and_rssi"]
    min_duration_ms: int
    max_duration_ms: int
    retained_jobs: int


class Accepted(DeviceModel):
    id: JobId


class Job(DeviceModel):
    id: JobId
    state: Literal["running", "done", "cancelled"]
    frequency_hz: UInt
    actual_frequency_hz: UInt
    duration_ms: UInt
    elapsed_ms: UInt
    pulses: UInt
    high_pulses: UInt
    rssi_samples: UInt
    peak_rssi_dbm: float | None


class JobList(DeviceModel):
    jobs: list[Job]
    retained: Annotated[int, Field(ge=0)]


class CancelAccepted(DeviceModel):
    id: JobId
    state: Literal["cancelling"]


class Settings(DeviceModel):
    measurement_units: Literal["metric", "imperial"]
    time_format: Literal["12h", "24h"]
    date_format: Literal["dmy", "mdy", "ymd"]
    timezone_automatic: bool
    timezone_offset_minutes: Annotated[int, Field(ge=-1440, le=1440)]
    writable: Literal[False]


class BatteryDiagnostics(DeviceModel):
    charge_percent: Annotated[float, Field(ge=0, le=100)]
    health_percent: Annotated[float, Field(ge=0, le=100)]
    charging: bool
    gauge_ok: bool
    voltage_v: float
    temperature_c: float


class WifiDiagnostics(DeviceModel):
    connected: bool
    rssi_dbm: int | None = None
    channel: int | None = None


class MemoryDiagnostics(DeviceModel):
    free_internal_bytes: Annotated[int, Field(ge=0)]
    largest_internal_block_bytes: Annotated[int, Field(ge=0)]


class StorageDiagnostics(DeviceModel):
    available: bool
    total_bytes: Annotated[int, Field(ge=0)] | None = None
    free_bytes: Annotated[int, Field(ge=0)] | None = None


class Diagnostics(DeviceModel):
    battery: BatteryDiagnostics
    wifi: WifiDiagnostics
    memory: MemoryDiagnostics
    storage: StorageDiagnostics
    uptime_ms: Annotated[int, Field(ge=0)]
    epoch_seconds: Annotated[int, Field(ge=0)]


def device_url(value: str) -> str:
    """Only operator-configured RFC1918 IPv4 endpoints; never tool-supplied URLs."""
    parsed = urlsplit(value)
    address = ipaddress.IPv4Address(parsed.hostname or "")
    private = any(address in ipaddress.ip_network(net) for net in
                  ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"))
    if (not private or parsed.scheme != "http" or parsed.username is not None or
            parsed.password is not None or parsed.path not in ("", "/") or
            parsed.query or parsed.fragment):
        raise ValueError("TEMBED_URL must be an HTTP origin with a private IPv4 address.")
    port = parsed.port or 80
    if not 1 <= port <= 65535:
        raise ValueError("Invalid device port")
    return f"http://{address}:{port}"


class Device:
    def __init__(self, base_url: str, transport=None):
        self.base_url = device_url(base_url)
        self.transport = transport
        self.start_lock = asyncio.Lock()

    async def request(self, method, path, model, payload=None, expected=200):
        try:
            # A wall-clock bound also limits a slow/trickling response.
            async with asyncio.timeout(8):
                async with httpx.AsyncClient(
                    base_url=self.base_url, timeout=5, trust_env=False,
                    follow_redirects=False, transport=self.transport,
                ) as client:
                    async with client.stream(method, path, json=payload) as response:
                        code = response.status_code
                        if code != expected:
                            messages = {
                                400: "invalid_request: firmware rejected the input",
                                404: "not_found: job expired, WebFS restarted, or RPC route missing",
                                409: ("job_not_running: the retained job cannot be cancelled"
                                      if path.startswith("/api/jobs/cancel") else
                                      "busy: another receive job is running"),
                                501: "unsupported: this firmware does not support the operation",
                            }
                            raise ToolError(messages.get(code, f"device_http_error: HTTP {code}"))
                        data = bytearray()
                        async for chunk in response.aiter_bytes():
                            data.extend(chunk)
                            if len(data) > 16384:
                                raise ToolError("invalid_response: device response exceeds 16 KiB")
                        result = json.loads(data)
                        return model.model_validate(result)
        except (httpx.RequestError, TimeoutError) as exc:
            suffix = (" The RX request may have reached the device. Check tembed_status; "
                      "do not automatically retry." if path == "/api/subghz/rx" else
                      " Check WiFi and keep Web-Filesystem open.")
            raise ToolError("device_unreachable_or_timeout." + suffix) from exc
        except (ValueError, ValidationError) as exc:
            suffix = " Check tembed_status before repeating RX." if path == "/api/subghz/rx" else ""
            raise ToolError("invalid_response: expected WebFS RPC API 1.1 JSON." + suffix) from exc

    async def status(self):
        return await self.request("GET", "/api/status", Status)

    async def capabilities(self):
        return await self.request("GET", "/api/capabilities", Capabilities)

    async def start_rx(self, frequency_hz: int, duration_ms: int):
        if type(frequency_hz) is not int or not any(low <= frequency_hz <= high for low, high in
                ((281000000, 361000000), (378000000, 481000000), (749000000, 962000000))):
            raise ToolError("invalid_frequency: frequency_hz is outside the firmware RX ranges")
        if type(duration_ms) is not int or not 100 <= duration_ms <= 60000:
            raise ToolError("invalid_duration: duration_ms must be an integer from 100 to 60000")
        async with self.start_lock:
            status = await self.status()
            if status.busy:
                raise ToolError(f"busy: receive job {status.active_job_id} is active")
            if not status.webfs_running:
                raise ToolError("Web-Filesystem must remain open")
            return await self.request("POST", "/api/subghz/rx", Accepted,
                                      {"frequency_hz": frequency_hz, "duration_ms": duration_ms}, 202)

    async def job(self, job_id: int):
        if type(job_id) is not int or not 1 <= job_id <= 4294967295:
            raise ToolError("invalid_job_id: use the positive integer returned by tembed_start_rx")
        result = await self.request("GET", f"/api/jobs?id={job_id}", Job)
        if result.id != job_id:
            raise ToolError("invalid_response: device returned a different job ID")
        return result

    async def jobs(self):
        return await self.request("GET", "/api/jobs", JobList)

    async def cancel_job(self, job_id: int):
        if type(job_id) is not int or not 1 <= job_id <= 4294967295:
            raise ToolError("invalid_job_id: use a positive retained job ID")
        result = await self.request(
            "POST", f"/api/jobs/cancel?id={job_id}", CancelAccepted, expected=202
        )
        if result.id != job_id:
            raise ToolError("invalid_response: device returned a different job ID")
        return result

    async def settings(self):
        return await self.request("GET", "/api/settings", Settings)

    async def diagnostics(self):
        return await self.request("GET", "/api/diagnostics", Diagnostics)


def make_server(device: Device, **settings) -> FastMCP:
    server = FastMCP(
        "T-Embed Receive Gateway",
        **settings,
        instructions=("Use only this configured T-Embed. Direct RX tools are receive-only. USB buttons operate the actual device menu and can cause side effects. SD-card list, download and upload tools are available. "
                      "No dedicated IR or NFC tools exist. RX returns pulse statistics and RSSI, not decoded "
                      "messages. Noise can produce pulses. Only the latest job is retained. "
                      "Poll tembed_job at most once per second. Never automatically repeat a "
                      "start request after a timeout; check tembed_status first."),
    )
    read = ToolAnnotations(readOnlyHint=True, destructiveHint=False,
                           idempotentHint=True, openWorldHint=False)

    @server.tool(annotations=read)
    async def tembed_status() -> Status:
        """Get firmware, API, network and receiver busy state from the T-Embed."""
        return await device.status()

    @server.tool(annotations=read)
    async def tembed_capabilities() -> Capabilities:
        """Read supported API 1.1 capabilities and limits. No RF action."""
        return await device.capabilities()

    @server.tool(annotations=read)
    async def tembed_settings() -> Settings:
        """Read locale, clock, date and timezone settings. Settings are not changed."""
        return await device.settings()

    @server.tool(annotations=read)
    async def tembed_diagnostics() -> Diagnostics:
        """Read battery, Wi-Fi, memory, SD-card and uptime diagnostics."""
        return await device.diagnostics()

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                           idempotentHint=False, openWorldHint=False))
    async def tembed_start_rx(frequency_hz: Frequency = 433920000,
                             duration_ms: Duration = 1000) -> Accepted:
        """Start one receive-only OOK650 job, 100–60000 ms; return its ID immediately.

        Occupies the receiver and replaces the previous retained result. No RF TX.
        Accepted bands: 281–361, 378–481, 749–962 MHz. Use Hz, not MHz, as input.
        Retrieve statistics later with tembed_job. No packet decoding or RAW files.
        """
        return await device.start_rx(frequency_hz, duration_ms)

    @server.tool(annotations=read)
    async def tembed_job(job_id: JobId) -> Job:
        """Read the latest RX job by ID. done means the timer ended, not a decoded signal.

        Old IDs expire after a newer job or a WebFS restart. IDs reset on reboot.
        """
        return await device.job(job_id)

    @server.tool(annotations=read)
    async def tembed_jobs() -> JobList:
        """List retained receive jobs. The current firmware retains at most one."""
        return await device.jobs()

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False,
                                           idempotentHint=True, openWorldHint=False))
    async def tembed_cancel_job(job_id: JobId) -> CancelAccepted:
        """Request cancellation of the active receive-only job. Does not transmit RF."""
        return await device.cancel_job(job_id)

    from usb_remote import UsbRemote
    usb = UsbRemote()
    server.tembed_usb = usb
    from web_files import WebFiles
    files = WebFiles(device)

    @server.tool(annotations=read)
    async def tembed_files_list(path: str = "/ext") -> dict:
        """List SD-card files through WebFS. Does not execute files."""
        return await files.list(path)

    @server.tool(annotations=read)
    async def tembed_file_download(path: str) -> dict:
        """Download one SD-card file, up to 2 MiB, returned as base64."""
        content = await files.download(path)
        return {
            "path": path,
            "size": len(content),
            "content_base64": base64.b64encode(content).decode("ascii"),
        }

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True,
                                           idempotentHint=True, openWorldHint=False))
    async def tembed_file_upload(path: str, content_base64: Base64File) -> dict:
        """Upload one base64-encoded SD-card file, up to 2 MiB; replaces that path."""
        try:
            content = base64.b64decode(content_base64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ToolError("invalid_base64: content_base64 is not valid base64") from exc
        return await files.mutate("upload", path, content=content)

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    async def tembed_usb_connect() -> dict:
        """Open the configured USB qFlipper session and start screen streaming. No button presses."""
        return await asyncio.to_thread(usb.connect)

    @server.tool(annotations=read)
    async def tembed_usb_screen() -> dict:
        """USB state and latest 128x64 monochrome framebuffer, base64 in vertical 8-pixel pages.
        May be stale: inspect connected and received_at. Does not open a session.
        """
        return usb.snapshot()

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    async def tembed_usb_button(key: Literal["up", "down", "left", "right", "ok", "back"], long: bool = False) -> dict:
        """Press one device GUI key. The current app determines its effect, including destructive actions.
        Inspect the screen and user's intent first. Never retry automatically. USB mode changes can disconnect.
        """
        return await asyncio.to_thread(usb.key, key, long)

    # Wi-Fi Remote: the same GUI RPC over the firmware's WebSocket endpoint, so
    # screen streaming and button control work without a USB cable. Requires the
    # device's "Wi-Fi Remote" feature running and TEMBED_REMOTE_TOKEN set.
    from wifi_remote import WifiRemote
    wifi = WifiRemote()
    server.tembed_wifi = wifi

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
    async def tembed_wifi_connect() -> dict:
        """Open the Wi-Fi Remote WebSocket session and start screen streaming. No button presses."""
        return await asyncio.to_thread(wifi.connect)

    @server.tool(annotations=read)
    async def tembed_wifi_screen() -> dict:
        """Wi-Fi Remote state and latest 128x64 monochrome framebuffer, base64 in vertical 8-pixel pages.
        May be stale: inspect connected and received_at. Does not open a session.
        """
        return wifi.snapshot()

    @server.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False, openWorldHint=False))
    async def tembed_wifi_button(key: Literal["up", "down", "left", "right", "ok", "back"], long: bool = False) -> dict:
        """Press one device GUI key over Wi-Fi. The current app determines its effect, including destructive actions.
        Inspect the screen and user's intent first. Never retry automatically.
        """
        return await asyncio.to_thread(wifi.key, key, long)

    return server


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Print device status, without starting RX")
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    args = parser.parse_args()
    device = Device(os.environ.get("TEMBED_URL", "http://192.168.178.35"))
    if args.check:
        print(asyncio.run(device.status()).model_dump_json(indent=2))
    else:
        settings = {}
        if args.transport == "streamable-http":
            hosts = [h.strip() for h in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if h.strip()]
            if not hosts or any("*" in h for h in hosts):
                parser.error("Set MCP_ALLOWED_HOSTS to exact host:port values, without wildcards")
            settings = dict(
                host="0.0.0.0", port=8000, stateless_http=True, json_response=True,
                transport_security=TransportSecuritySettings(
                    enable_dns_rebinding_protection=True,
                    allowed_hosts=hosts,
                    allowed_origins=[scheme + h for h in hosts for scheme in ("http://", "https://")],
                ),
            )
        server = make_server(device, **settings)
        if args.transport == "streamable-http":
            from web_ui import register_ui
            register_ui(server, device, hosts)
        server.run(transport=args.transport)


if __name__ == "__main__":
    main()
