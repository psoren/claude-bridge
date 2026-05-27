#!/usr/bin/env python3
"""
Tiny HTTP bridge to the local `claude -p`.

Designed to run on the Mac mini, started inside a GUI Terminal session so that
the macOS login Keychain is unlocked and `claude` can read its OAuth token.
Binds to 127.0.0.1 only — reached over SSH from any Tailnet device via:

    ssh parkers-mac-mini 'curl -sS -X POST --data-binary @- http://127.0.0.1:9100/ask' <<< "your prompt"
"""

import json
import os
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT = int(os.environ.get("PORT", "9100"))
TIMEOUT_S = int(os.environ.get("CLAUDE_TIMEOUT", "300"))


class Handler(BaseHTTPRequestHandler):
    def _write(self, status: int, body: bytes, ctype: str = "text/plain; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path in ("/", "/health"):
            self._write(200, b"ok\n")
        else:
            self._write(404, b"not found\n")

    def do_POST(self) -> None:
        if self.path != "/ask":
            self._write(404, b"not found\n")
            return
        length = int(self.headers.get("Content-Length", 0) or 0)
        if length <= 0:
            self._write(400, b"empty body\n")
            return
        prompt = self.rfile.read(length).decode("utf-8", errors="replace")

        try:
            result = subprocess.run(
                ["claude", "-p", prompt],
                capture_output=True,
                text=True,
                timeout=TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            self._write(504, f"claude timed out after {TIMEOUT_S}s\n".encode())
            return
        except FileNotFoundError:
            self._write(500, b"`claude` binary not on PATH for the daemon\n")
            return

        out = result.stdout
        if result.returncode != 0:
            out += f"\n--- stderr (rc={result.returncode}) ---\n{result.stderr}"
        self._write(200, out.encode("utf-8"))

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write(f"{self.address_string()} {fmt % args}\n")


def main() -> None:
    print(f"claude-bridge listening on 127.0.0.1:{PORT} (timeout={TIMEOUT_S}s)", flush=True)
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
