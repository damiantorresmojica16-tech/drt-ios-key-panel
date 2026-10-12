"""HTTPS-reverse-proxy-ready validation API for the private key bot."""

from __future__ import annotations

import hashlib
import ipaddress
import json
import logging
import re
import sqlite3
import threading
import time
from collections import defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


LOGGER = logging.getLogger("key_api")
KEY_PATTERN = re.compile(r"^DRT-(?:WEEK|2WEEK|MONTH|XIT) [0-9A-F]{4}$")
VALIDITY_LABELS = {7: "WEEK", 15: "2 WEEKS", 30: "1 MONTH"}
RATE_LIMIT_WINDOW_SECONDS = 60
RATE_LIMIT_REQUESTS = 10
MAX_REQUEST_BYTES = 1024


class ValidationHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        database_path: Path,
        trust_proxy: bool,
    ) -> None:
        super().__init__(address, ValidationRequestHandler)
        self.database_path = database_path
        self.trust_proxy = trust_proxy
        self.request_times: dict[str, deque[float]] = defaultdict(deque)
        self.rate_limit_lock = threading.Lock()


class ValidationRequestHandler(BaseHTTPRequestHandler):
    server: ValidationHTTPServer

    def log_message(self, format: str, *args: Any) -> None:
        LOGGER.info("%s - %s", self.client_address[0], format % args)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        self.send_json(200, {})

    def do_GET(self) -> None:
        if self.path != "/healthz":
            self.send_json(404, {"error": "not_found"})
            return

        try:
            with sqlite3.connect(self.server.database_path, timeout=5) as connection:
                connection.execute("SELECT 1 FROM access_keys LIMIT 1").fetchone()
        except sqlite3.Error:
            LOGGER.exception("Database health check failed")
            self.send_json(503, {"error": "service_unavailable"})
            return
        self.send_json(200, {"ok": True})

    def do_POST(self) -> None:
        if self.path != "/api/validate":
            self.send_json(404, {"error": "not_found"})
            return

        if not self._within_rate_limit():
            self.send_json(429, {"error": "rate_limited"})
            return

        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_json(400, {"error": "invalid_request"})
            return
        if not 1 <= content_length <= MAX_REQUEST_BYTES:
            self.send_json(400, {"error": "invalid_request"})
            return

        try:
            request_data = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json(400, {"error": "invalid_request"})
            return
        if not isinstance(request_data, dict) or not isinstance(request_data.get("key"), str):
            self.send_json(400, {"error": "invalid_request"})
            return

        key = request_data["key"].strip().upper()
        if not KEY_PATTERN.fullmatch(key):
            self.send_json(401, {"error": "invalid_or_expired_key"})
            return

        digest = hashlib.sha256(key.encode("ascii")).hexdigest()
        try:
            connection = sqlite3.connect(self.server.database_path, timeout=5)
            connection.row_factory = sqlite3.Row
            try:
                row = connection.execute(
                    """
                    SELECT created_at, expires_at, revoked_at
                    FROM access_keys
                    WHERE key_hash = ?
                    """,
                    (digest,),
                ).fetchone()
            finally:
                connection.close()
        except sqlite3.Error:
            LOGGER.exception("Database error while validating a key")
            self.send_json(503, {"error": "service_unavailable"})
            return

        now = int(time.time())
        if row is None or row["revoked_at"] is not None or row["expires_at"] <= now:
            self.send_json(401, {"error": "invalid_or_expired_key"})
            return

        days = round((row["expires_at"] - row["created_at"]) / 86400)
        label = VALIDITY_LABELS.get(days)
        if label is None:
            LOGGER.error("Key row has an unsupported validity duration")
            self.send_json(503, {"error": "service_unavailable"})
            return

        self.send_json(
            200,
            {
                "valid": True,
                "duration_days": days,
                "duration_label": label,
                "expires_at": row["expires_at"],
                "server_time": now,
                "remaining_seconds": row["expires_at"] - now,
            },
        )

    def _within_rate_limit(self) -> bool:
        client_ip = self.client_address[0]
        if self.server.trust_proxy:
            forwarded_ip = self.headers.get("X-Forwarded-For", "").split(",", 1)[0].strip()
            try:
                client_ip = str(ipaddress.ip_address(forwarded_ip))
            except ValueError:
                pass
        now = time.monotonic()
        with self.server.rate_limit_lock:
            requests = self.server.request_times[client_ip]
            while requests and now - requests[0] >= RATE_LIMIT_WINDOW_SECONDS:
                requests.popleft()
            if len(requests) >= RATE_LIMIT_REQUESTS:
                return False
            requests.append(now)
            return True


def start_validation_api(
    database_path: Path, host: str, port: int, trust_proxy: bool = False
) -> ValidationHTTPServer:
    server = ValidationHTTPServer((host, port), database_path, trust_proxy)
    thread = threading.Thread(
        target=server.serve_forever,
        name="key-validation-api",
        daemon=True,
    )
    thread.start()
    return server
