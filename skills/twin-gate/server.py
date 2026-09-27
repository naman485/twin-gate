#!/usr/bin/env python3
"""Twin Gate review page. Standard library only.

  python3 server.py            then open http://localhost:8790
  PORT=8790 TWIN_BRAIN=./brain

Endpoints: GET /api/twins, GET /api/twin/<id>, POST /api/propose {task, inject_error},
POST /api/approve/<id>, POST /api/reject/<id>, POST /api/reset (restore the sample brain).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import twingate as tg  # noqa: E402

PORT = int(os.environ.get("PORT", "8790"))
PAGE = (HERE / "index.html").read_text(encoding="utf-8")


def reset_brain():
    seed = HERE / "brain-seed"
    if not seed.exists():
        return {"ok": False, "error": "no brain-seed folder"}
    if tg.BRAIN.exists():
        shutil.rmtree(tg.BRAIN)
    shutil.copytree(seed, tg.BRAIN)
    for p in tg.STATE.glob("tg-*.json"):
        st = json.loads(p.read_text())
        sb = st.get("sandbox") or {}
        if sb.get("id") and st.get("status") not in ("approved", "rejected"):
            try:
                tg.sbx.destroy(sb["id"])
            except tg.sbx.SandboxError:
                pass
        p.unlink()
    tg.ensure_brain()
    gb = tg.gb.reset(tg.BRAIN) if tg.gb.available() else {"ok": False, "reason": "gbrain not installed"}
    return {"ok": True, "gbrain": gb.get("ok", False)}


class H(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.command, self.path))

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            return self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        if self.path == "/api/twins":
            return self._send(200, {"twins": tg.list_twins(), "sandbox": tg.sbx.available(), "gbrain": tg.gb.available(),
                                    "brain": str(tg.BRAIN), "head": tg.git("log", "--oneline", "-5", check=False)})
        if self.path.startswith("/api/twin/"):
            try:
                return self._send(200, tg.review(self.path.rsplit("/", 1)[1]))
            except SystemExit as e:
                return self._send(404, {"error": str(e)})
        if self.path.startswith("/api/gbrain/search"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            return self._send(200, tg.gb.search(qs.get("q", ["CB-0003"])[0]) | {"available": tg.gb.available()})
        if self.path.startswith("/api/page/"):
            rel = self.path[len("/api/page/"):]
            return self._send(200, {"path": rel, "text": tg.read_page(rel, tg.BRAIN)})
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}") if n else {}
        try:
            if self.path == "/api/propose":
                tid = tg.propose(body.get("task", "").strip() or "Draft the dispute for the short staple chargeback on INV-102",
                                 bool(body.get("inject_error")))
                return self._send(200, tg.review(tid))
            if self.path.startswith("/api/approve/"):
                tid = self.path.rsplit("/", 1)[1]
                tg.approve(tid, body.get("who", "owner"))
                return self._send(200, tg.review(tid))
            if self.path.startswith("/api/reject/"):
                tid = self.path.rsplit("/", 1)[1]
                tg.reject(tid, body.get("who", "owner"))
                return self._send(200, tg.review(tid))
            if self.path == "/api/reset":
                return self._send(200, reset_brain())
            if self.path == "/api/gbrain/init":
                return self._send(200, tg.gb.init(tg.BRAIN))
        except (SystemExit, RuntimeError, tg.sbx.SandboxError) as e:
            return self._send(400, {"error": str(e)})
        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    tg.ensure_brain()
    print(f"Twin Gate on http://localhost:{PORT}  brain={tg.BRAIN}  sandbox={'on' if tg.sbx.available() else 'off (set CREATEOS_SANDBOX_API_KEY)'}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
