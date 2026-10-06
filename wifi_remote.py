"""Wi-Fi RPC transport: the same Flipper GUI RPC that usb_remote.py speaks, but
carried over the firmware's WebSocket endpoint (ws://<device>:80/rpc?token=...)
instead of USB serial. Gives screen streaming and button control over Wi-Fi, so
no USB cable is required.

Mirrors UsbRemote's interface (connect / snapshot / key / close) and reuses its
protobuf framing helpers. Stdlib only -- a small masked-frame WebSocket client,
no extra dependency. Receive-only radio and the no-arbitrary-RPC stance are
unchanged; this only moves the existing GUI RPC onto Wi-Fi.
"""
import atexit
import base64
import os
import socket
import struct
import threading
import time
from urllib.parse import urlsplit

from mcp.server.fastmcp.exceptions import ToolError

# Reuse the exact wire framing the USB transport uses.
from usb_remote import varint, number, blob, read_varint, fields


def _resolve_endpoint():
    """Host/port/token for the Wi-Fi Remote endpoint, from the environment.

    TEMBED_REMOTE_URL (ws://host[:port]) wins; otherwise the host is taken from
    TEMBED_URL (the WebFS origin) on port 80. The token comes from
    TEMBED_REMOTE_TOKEN."""
    token = os.environ.get("TEMBED_REMOTE_TOKEN", "").strip()
    url = os.environ.get("TEMBED_REMOTE_URL", "").strip()
    if not url:
        url = os.environ.get("TEMBED_URL", "").strip()
    host, port = "", 80
    if url:
        parts = urlsplit(url if "://" in url else "http://" + url)
        host = parts.hostname or ""
        port = parts.port or 80
    return host, port, token


class WifiRemote:
    def __init__(self):
        self.host, self.port, self.token = _resolve_endpoint()
        self.sock = None
        self.thread = None
        self.stop = threading.Event()
        self.control = threading.RLock()
        self.lock = threading.Lock()
        self.pending = {}
        self.counter = 0
        self.frame = None
        self.error = ""
        self.connected = False
        atexit.register(self.close)

    def snapshot(self):
        with self.lock:
            return {
                "configured": bool(self.host and self.token),
                "connected": self.connected,
                "endpoint": f"ws://{self.host}:{self.port}/rpc" if self.host else "",
                "error": self.error,
                "frame": self.frame,
            }

    # ---- WebSocket transport (stdlib, client-masked) ----
    def _ws_handshake(self, sock):
        key = base64.b64encode(os.urandom(16)).decode()
        path = f"/rpc?token={self.token}"
        req = (
            f"GET {path} HTTP/1.1\r\nHost: {self.host}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\n"
            f"Sec-WebSocket-Version: 13\r\n\r\n"
        )
        sock.sendall(req.encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            chunk = sock.recv(1)
            if not chunk:
                raise ValueError("no handshake response")
            resp += chunk
            if len(resp) > 4096:
                raise ValueError("oversized handshake response")
        if b" 101 " not in resp.split(b"\r\n", 1)[0] + b" ":
            raise ValueError("handshake rejected (check token)")

    def _ws_send(self, payload, opcode=0x2):
        mask = os.urandom(4)
        n = len(payload)
        header = bytearray([0x80 | opcode])
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def _ws_recv_frame(self):
        def rd(count):
            buf = b""
            while len(buf) < count:
                chunk = self.sock.recv(count - len(buf))
                if not chunk:
                    raise EOFError("socket closed")
                buf += chunk
            return buf

        b0, b1 = rd(2)
        opcode = b0 & 0x0F
        masked = b1 & 0x80
        length = b1 & 0x7F
        if length == 126:
            length = struct.unpack(">H", rd(2))[0]
        elif length == 127:
            length = struct.unpack(">Q", rd(8))[0]
        key = rd(4) if masked else b""  # server frames are unmasked in practice
        data = rd(length) if length else b""
        if masked and key:
            data = bytes(b ^ key[i % 4] for i, b in enumerate(data))
        return opcode, data

    def connect(self):
        with self.control:
            if self.connected:
                return self.snapshot()
            self.close()
            if not self.host or not self.token:
                raise ToolError(
                    "Wi-Fi Remote not configured: set TEMBED_URL (or TEMBED_REMOTE_URL) "
                    "and TEMBED_REMOTE_TOKEN"
                )
            try:
                sock = socket.create_connection((self.host, self.port), timeout=6)
                sock.settimeout(6)
                self._ws_handshake(sock)
                self.sock = sock
                self.stop.clear()
                with self.lock:
                    self.error = ""
                    self.frame = None
                    self.connected = True
                self.thread = threading.Thread(target=self._read, daemon=True)
                self.thread.start()
                # Start the GUI screen stream (RPC field 20, empty submessage).
                self._command(20, b"")
                return self.snapshot()
            except Exception as exc:
                self.close()
                with self.lock:
                    self.error = str(exc)
                raise ToolError("Wi-Fi Remote connection failed: " + str(exc)) from exc

    def _read(self):
        buffer = bytearray()
        try:
            while not self.stop.is_set():
                try:
                    opcode, payload = self._ws_recv_frame()
                except socket.timeout:
                    continue
                if opcode == 0x8:  # CLOSE
                    raise EOFError("server closed the session")
                if opcode not in (0x2, 0x0):  # only binary/continuation carry RPC
                    continue
                buffer.extend(payload)
                if len(buffer) > 131072:
                    raise ValueError("RPC buffer limit")
                while buffer:
                    try:
                        size, start = read_varint(buffer)
                    except (EOFError, IndexError):
                        break
                    if size > 65536:
                        raise ValueError("RPC message too large")
                    if len(buffer) < start + size:
                        break
                    msg = fields(bytes(buffer[start : start + size]))
                    del buffer[: start + size]
                    if 22 in msg:  # gui_screen_frame
                        frame = fields(msg[22])
                        raw = frame.get(1, b"")
                        orientation = frame.get(2, 0)
                        if len(raw) == 1024 and orientation in (0, 1, 2, 3):
                            with self.lock:
                                self.frame = {
                                    "data": base64.b64encode(raw).decode(),
                                    "orientation": orientation,
                                    "width": 128,
                                    "height": 64,
                                    "received_at": time.time(),
                                }
                    cid = msg.get(1, 0)
                    with self.lock:
                        pending = self.pending.get(cid)
                        if pending:
                            pending["status"] = msg.get(2, 0)
                            pending["event"].set()
        except Exception as exc:
            if not self.stop.is_set():
                with self.lock:
                    self.error = str(exc)
        finally:
            with self.lock:
                self.connected = False
                for p in self.pending.values():
                    p["event"].set()

    def _command(self, tag, payload):
        if not self.connected:
            raise ToolError("Wi-Fi Remote disconnected; reconnect explicitly")
        self.counter = (self.counter % 0xFFFFFFFE) + 1
        cid = self.counter
        pending = {"event": threading.Event(), "status": None}
        with self.lock:
            self.pending[cid] = pending
        try:
            message = number(1, cid) + blob(tag, payload)
            self._ws_send(varint(len(message)) + message)
            if not pending["event"].wait(3):
                raise ToolError("Wi-Fi Remote RPC timeout; command is not retried")
            if pending["status"] not in (0, None):
                raise ToolError("Wi-Fi Remote RPC failed: " + str(pending["status"]))
        finally:
            with self.lock:
                self.pending.pop(cid, None)

    def key(self, key, long=False):
        keys = {"up": 0, "down": 1, "right": 2, "left": 3, "ok": 4, "back": 5}
        if key not in keys or type(long) is not bool:
            raise ToolError("Invalid button")
        with self.control:
            try:
                self._command(23, number(1, keys[key]) + number(2, 0))  # PRESS
                try:
                    self._command(23, number(1, keys[key]) + number(2, 3 if long else 2))
                finally:
                    self._command(23, number(1, keys[key]) + number(2, 1))  # RELEASE
                return {"ok": True}
            except Exception as exc:
                self.close()
                raise ToolError(
                    "Button sequence interrupted; check device before repeating: " + str(exc)
                ) from exc

    def close(self):
        with self.control:
            self.stop.set()
            if self.thread and self.thread is not threading.current_thread():
                self.thread.join(timeout=1)
            if self.sock:
                try:
                    self.sock.close()
                except Exception:
                    pass
            self.sock = None
            self.thread = None
            with self.lock:
                self.connected = False
                self.frame = None
            return {"connected": False}
