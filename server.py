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
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import twingate as tg  # noqa: E402
import plant  # noqa: E402

PORT = int(os.environ.get("PORT", "8790"))
PAGE = (HERE / "index.html").read_text(encoding="utf-8")
PLANT_PAGE = (HERE / "plant.html").read_text(encoding="utf-8")
STATIC = {".svg": "image/svg+xml", ".mp3": "audio/mpeg", ".txt": "text/plain; charset=utf-8"}


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
    sys.stderr.write(f"reset: {tg.invalidate_base()}\n")
    plant.reset()
    gb = tg.gb.reset(tg.BRAIN) if tg.gb.available() else {"ok": False, "reason": "gbrain not installed"}
    background(tg.warm_base)
    return {"ok": True, "gbrain": gb.get("ok", False)}


def background(fn, *args):
    threading.Thread(target=fn, args=args, daemon=True).start()


def shutdown(signum, frame):
    """The platform stops this container on every redeploy. Take our sandboxes with us: the base, and the
    twins still open. A new container builds its own base at boot; nothing here is needed again."""
    sys.stderr.write("shutdown: destroying this container's sandboxes\n")
    for st_path in tg.STATE.glob("tg-*.json"):
        try:
            st = json.loads(st_path.read_text())
            sb = st.get("sandbox") or {}
            if sb.get("id") and st.get("status") not in ("approved", "rejected"):
                tg.sbx.destroy(sb["id"])
        except Exception:  # noqa: BLE001  best effort on the way out
            pass
    tg.invalidate_base()
    raise SystemExit(0)


def janitor():
    """Sweep stray base sandboxes at boot and every ten minutes. See twingate.sweep_bases."""
    import time
    while True:
        try:
            res = tg.sweep_bases()
            if res.get("swept"):
                sys.stderr.write(f"janitor: swept {res['swept']}\n")
        except Exception as e:  # noqa: BLE001  the janitor must never take the server down
            sys.stderr.write(f"janitor: {type(e).__name__}: {e}\n")
        time.sleep(600)


def warm_gbrain():
    """A fresh container has no GBrain index yet; build it from the brain so recall and approve-sync work at once."""
    if tg.gb.available() and not Path(tg.gb.HOME).exists():
        tg.gb.init(tg.BRAIN)


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
        if self.path in ("/plant", "/plant/", "/plant.html"):
            return self._send(200, PLANT_PAGE.encode(), "text/html; charset=utf-8")
        if self.path.startswith("/plant/logos/") or self.path.startswith("/plant/audio/"):
            f = HERE / "plant" / self.path.split("/")[2] / Path(self.path).name
            if f.exists() and f.suffix in STATIC:
                return self._send(200, f.read_bytes(), STATIC[f.suffix])
            return self._send(404, {"error": "not found"})
        if self.path == "/api/base":
            return self._send(200, {"current": (json.loads(tg._base_marker().read_text()).get("id") if tg._base_marker().exists() else None),
                                    "history": tg.base_history()[-40:]})
        if self.path == "/api/plant/brain":
            return self._send(200, plant.graph())
        if self.path == "/api/plant/config":
            return self._send(200, plant.config())
        if self.path == "/api/twins":
            return self._send(200, {"twins": tg.list_twins(), "sandbox": tg.sbx.available(), "gbrain": tg.gb.available(),
                                    "base_ready": tg._base_marker().exists(),
                                    "base": (json.loads(tg._base_marker().read_text()).get("id") if tg._base_marker().exists() else None),
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
                # {"async": true}: answer at once with the twin id, work in the background, the page polls
                # /api/twin/<id>. A proposal takes 15 to 40 s, longer than a hosting edge keeps a request open.
                # Without it the call blocks until the gate has decided, which scripts and Factory Brain's proxy expect.
                tid = tg.propose_start(body.get("task", "").strip() or "Draft the dispute for the short staple chargeback on INV-102",
                                       bool(body.get("inject_error")))
                if body.get("async"):
                    background(tg.propose_run, tid)
                    return self._send(202, {"id": tid, "status": "working"})
                tg.propose_run(tid)
                return self._send(200, tg.review(tid))
            if self.path.startswith("/api/approve/"):
                tid = self.path.rsplit("/", 1)[1]
                tg.approve(tid, body.get("who", "owner"))
                background(tg.warm_base)
                return self._send(200, tg.review(tid))
            if self.path.startswith("/api/reject/"):
                tid = self.path.rsplit("/", 1)[1]
                tg.reject(tid, body.get("who", "owner"))
                return self._send(200, tg.review(tid))
            if self.path == "/api/reset":
                return self._send(200, reset_brain())
            if self.path == "/api/plant/sms":
                return self._send(200, plant.on_sms(body.get("body") or body.get("text") or ""))
            if self.path == "/api/plant/voice":
                if not body.get("transcript"):
                    return self._send(400, {"error": "need transcript"})
                res = plant.on_voice(body["transcript"])
                return self._send(400 if "error" in res else 200, res)
            if self.path == "/api/plant/claim":
                if not body.get("text"):
                    return self._send(400, {"error": "need text"})
                return self._send(200, plant.on_claim(body["text"], bool(body.get("inject_error"))))
            if self.path == "/api/gbrain/init":
                return self._send(200, tg.gb.init(tg.BRAIN))
        except (SystemExit, RuntimeError, tg.sbx.SandboxError) as e:
            return self._send(400, {"error": str(e)})
        return self._send(404, {"error": "not found"})


if __name__ == "__main__":
    tg.ensure_brain()
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)
    background(tg.warm_base)
    background(warm_gbrain)
    background(janitor)
    print(f"Twin Gate on http://localhost:{PORT}  brain={tg.BRAIN}  sandbox={'on' if tg.sbx.available() else 'off (set CREATEOS_SANDBOX_API_KEY)'}")
    ThreadingHTTPServer(("0.0.0.0", PORT), H).serve_forever()
