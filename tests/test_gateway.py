import json
import unittest

import httpx

from gateway import Device
from web_files import WebFiles


def response(data, status=200):
    if isinstance(data, bytes):
        return httpx.Response(status, content=data)
    return httpx.Response(status, json=data)


class GatewayApi11Tests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.requests = []

        async def handler(request):
            self.requests.append((request.method, request.url.path, request.url.query))
            routes = {
                "/api/status": {
                    "device": "LilyGo T-Embed CC1101", "board_id": "t-embed",
                    "firmware": "2.0.0", "idf_version": "v5.4.1",
                    "api_version": "1.1", "uptime_ms": 10,
                    "network_mode": "sta", "network_up": True,
                    "ip": "192.168.178.35", "webfs_running": True,
                    "busy": False, "active_job_id": 0,
                },
                "/api/capabilities": {
                    "api_version": "1.1", "read_only": False,
                    "radio_read_only": True, "storage_write": True,
                    "subghz_rx": True, "subghz_tx": False,
                    "protocol_decode": False, "raw_file_capture": False,
                    "ir_rx": False, "nfc_read": False,
                    "preset": "OOK650Async", "result": "pulse_statistics_and_rssi",
                    "min_duration_ms": 100, "max_duration_ms": 60000,
                    "retained_jobs": 1,
                },
                "/api/settings": {
                    "measurement_units": "metric", "time_format": "24h",
                    "date_format": "dmy", "timezone_automatic": True,
                    "timezone_offset_minutes": 120, "writable": False,
                },
                "/api/diagnostics": {
                    "battery": {"charge_percent": 75, "health_percent": 98,
                                "charging": False, "gauge_ok": True,
                                "voltage_v": 3.9, "temperature_c": 24.5},
                    "wifi": {"connected": True, "rssi_dbm": -55, "channel": 6},
                    "memory": {"free_internal_bytes": 100000,
                               "largest_internal_block_bytes": 50000},
                    "storage": {"available": True, "total_bytes": 1000,
                                "free_bytes": 500},
                    "uptime_ms": 10, "epoch_seconds": 1,
                },
                "/api/jobs": {"jobs": [], "retained": 0},
            }
            if request.url.path == "/api/jobs/cancel":
                return response({"id": 7, "state": "cancelling"}, 202)
            if request.url.path == "/api/storage/list":
                return response({"path": "/ext", "entries": []})
            if request.url.path == "/api/storage/download":
                return response(b"file data")
            if request.url.path == "/api/storage/upload":
                return response(b"ok")
            return response(routes[request.url.path])

        self.device = Device("http://192.168.178.35", httpx.MockTransport(handler))

    async def test_api_11_models_and_job_control(self):
        self.assertEqual((await self.device.status()).api_version, "1.1")
        self.assertTrue((await self.device.capabilities()).radio_read_only)
        self.assertEqual((await self.device.settings()).timezone_offset_minutes, 120)
        self.assertEqual((await self.device.diagnostics()).wifi.rssi_dbm, -55)
        self.assertEqual((await self.device.jobs()).retained, 0)
        self.assertEqual((await self.device.cancel_job(7)).state, "cancelling")

    async def test_storage_uses_stable_rpc_routes(self):
        files = WebFiles(self.device)
        self.assertEqual((await files.list())["path"], "/ext")
        self.assertEqual(await files.download("/ext/test.txt"), b"file data")
        self.assertTrue((await files.mutate("upload", "/ext/test.txt", content=b"x"))["ok"])
        paths = [item[1] for item in self.requests]
        self.assertIn("/api/storage/list", paths)
        self.assertIn("/api/storage/download", paths)
        self.assertIn("/api/storage/upload", paths)


if __name__ == "__main__":
    unittest.main()
