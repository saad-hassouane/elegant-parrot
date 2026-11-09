"""Localhost HTTP sidecar so any language can use the gate.

    python -m pii_gate.server --port 8765
    POST /protect  {"text": "..."}                  -> {"session": id, "safe_text": "..."}
    POST /restore  {"session": id, "text": "..."}   -> {"ok": bool, "text": "...", "problems": []}
                   (restore closes the session; unrestored sessions expire after --ttl s)
Binds 127.0.0.1 only."""
from __future__ import annotations

import argparse
import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .gate import Gate, Session


def make_server(gate: Gate, port: int = 8765, ttl: float = 300.0) -> ThreadingHTTPServer:
    sessions: dict[str, tuple[Session, float]] = {}
    lock = threading.Lock()

    def sweep() -> None:
        now = time.time()
        for sid in [k for k, (_, t) in sessions.items() if now - t > ttl]:
            sessions.pop(sid)[0].close()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:  # never log payloads
            pass

        def _reply(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:  # noqa: N802
            try:
                req = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
                with lock:
                    sweep()
                    if self.path == "/protect":
                        s = gate.session()
                        sid = secrets.token_urlsafe(16)
                        safe = s.protect(req["text"])
                        sessions[sid] = (s, time.time())
                        return self._reply(200, {"session": sid, "safe_text": safe})
                    if self.path == "/restore":
                        entry = sessions.pop(req["session"], None)
                        if not entry:
                            return self._reply(404, {"error": "unknown or expired session"})
                        r = entry[0].restore(req["text"])
                        entry[0].close()
                        return self._reply(200, {"ok": r.ok, "text": r.text, "problems": r.problems})
                self._reply(404, {"error": "not found"})
            except (KeyError, ValueError):
                self._reply(400, {"error": "bad request"})

    return ThreadingHTTPServer(("127.0.0.1", port), H)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--ttl", type=float, default=300)
    ap.add_argument("--no-ner", action="store_true")
    a = ap.parse_args()
    make_server(Gate(ner=not a.no_ner), a.port, a.ttl).serve_forever()


if __name__ == "__main__":
    main()
