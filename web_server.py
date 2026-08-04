#!/usr/bin/env python3
import argparse
import json
import mimetypes
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


_REPO_DIR = os.path.dirname(os.path.abspath(__file__))


class _Inputs:
    def __init__(self, backend: str):
        self._backend = backend
        self._initialized = False
        self._mode = "mock"
        self._channels = None
        self._remote_state = {
            "rho": 0.5,
            "speed": 0.2,
            "joy_x": 0.5,
            "joy_y": 0.5,
            "tap": 0.0,
        }

    def _init(self):
        if self._initialized:
            return
        self._initialized = True

        if self._backend == "mock":
            self._mode = "mock_remote"
            self._channels = None
            return

        if self._backend == "gpiozero":
            try:
                from gpiozero import MCP3008

                self._mode = "gpiozero"
                self._channels = {
                    "rho": MCP3008(channel=0),
                    "speed": MCP3008(channel=1),
                    "joy_x": MCP3008(channel=2),
                    "joy_y": MCP3008(channel=3),
                    "tap": MCP3008(channel=4),
                }
                return
            except Exception:
                self._mode = "error"
                self._channels = None
                return

        if self._backend == "adafruit-mcp3008":
            try:
                import board
                import busio
                import digitalio
                import adafruit_mcp3xxx.mcp3008 as MCP
                from adafruit_mcp3xxx.analog_in import AnalogIn

                spi = busio.SPI(board.SCK, MOSI=board.MOSI, MISO=board.MISO)
                cs = digitalio.DigitalInOut(board.CE0)
                mcp = MCP.MCP3008(spi, cs)

                self._mode = "adafruit-mcp3008"
                self._channels = {
                    "rho": AnalogIn(mcp, MCP.P0),
                    "speed": AnalogIn(mcp, MCP.P1),
                    "joy_x": AnalogIn(mcp, MCP.P2),
                    "joy_y": AnalogIn(mcp, MCP.P3),
                    "tap": AnalogIn(mcp, MCP.P4),
                }
                return
            except Exception:
                self._mode = "error"
                self._channels = None
                return

        self._mode = "error"
        self._channels = None

    def read(self):
        self._init()
        # Prefer remote state if in mock/remote mode or if no hardware
        if self._mode == "mock_remote" or not self._channels:
            return {
                "mode": self._mode,
                **self._remote_state
            }

        try:
            if self._mode == "adafruit-mcp3008":
                norm = lambda ch: float(ch.value) / 65535.0
                return {
                    "mode": self._mode,
                    "rho": norm(self._channels["rho"]),
                    "speed": norm(self._channels["speed"]),
                    "joy_x": norm(self._channels["joy_x"]),
                    "joy_y": norm(self._channels["joy_y"]),
                    "tap": norm(self._channels["tap"]),
                }

            return {
                "mode": self._mode,
                "rho": float(self._channels["rho"].value),
                "speed": float(self._channels["speed"].value),
                "joy_x": float(self._channels["joy_x"].value),
                "joy_y": float(self._channels["joy_y"].value),
                "tap": float(self._channels["tap"].value),
            }
        except Exception:
            return {
                "mode": "error",
                "rho": None,
                "speed": None,
                "joy_x": None,
                "joy_y": None,
                "tap": None,
            }

    def update(self, new_state: dict):
        self._remote_state.update(new_state)



_inputs = None


class RequestHandler(BaseHTTPRequestHandler):
    def _send_json(self, payload, status=200):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, file_path):
        try:
            with open(file_path, "rb") as f:
                body = f.read()
        except FileNotFoundError:
            self.send_error(404)
            return

        content_type, _ = mimetypes.guess_type(file_path)
        if not content_type:
            content_type = "application/octet-stream"

        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            return self._send_file(os.path.join(_REPO_DIR, "device_mockup.html"))

        if path == "/api/health":
            return self._send_json({"ok": True})

        if path == "/api/inputs":
            return self._send_json(_inputs.read())

        # Resolve to a real path BEFORE the containment check. A string prefix test
        # on an unresolved path is not a containment check: a request target with no
        # leading slash keeps its ".." segments through normpath().lstrip("/"), and
        # REPO + "/../../etc/hosts" still starts with REPO + os.sep as a string.
        safe_path = os.path.normpath(path).lstrip("/").lstrip("\\")
        real_root = os.path.realpath(_REPO_DIR)
        file_path = os.path.realpath(os.path.join(real_root, safe_path))

        if file_path != real_root and not file_path.startswith(real_root + os.sep):
            self.send_error(403)
            return

        return self._send_file(file_path)

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/inputs":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(content_length)
                data = json.loads(body)
                _inputs.update(data)
                return self._send_json({"ok": True, "state": _inputs.read()})
            except Exception as e:
                self.send_error(400, str(e))
                return
        
        self.send_error(404)

    def log_message(self, format, *args):
        return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--inputs",
        choices=["mock", "gpiozero", "adafruit-mcp3008"],
        default="mock",
    )
    args = parser.parse_args()

    global _inputs
    _inputs = _Inputs(args.inputs)

    server = ThreadingHTTPServer((args.host, args.port), RequestHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
