"""Minimal CreateOS Sandbox control-plane client. Standard library only.

Env:
  CREATEOS_SANDBOX_API_KEY   required for the real twin
  CREATEOS_SANDBOX_BASE_URL  default https://api.sb.createos.sh
  CREATEOS_SANDBOX_SHAPE     default s-1vcpu-1gb (see GET /v1/shapes)

The client is deliberately small: create, get, wait, exec, upload, download,
pause, fork, resume, destroy, egress. Every call raises SandboxError with the
status and body on failure so the caller can show the real reason on the page.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

def _load_env():
    """Read KEY=value lines from .env next to this file into os.environ (existing vars win)."""
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()
BASE = os.environ.get("CREATEOS_SANDBOX_BASE_URL", "https://api.sb.createos.sh").rstrip("/")
KEY = os.environ.get("CREATEOS_SANDBOX_API_KEY", "")
SHAPE = os.environ.get("CREATEOS_SANDBOX_SHAPE", "s-1vcpu-1gb")
ROOTFS = os.environ.get("CREATEOS_SANDBOX_ROOTFS", "devbox:1")
# Deny-by-default egress: once any rule is set, everything else is dropped in-kernel.
# A loopback entry gives the twin a rule and no route out.
NO_EGRESS = ["127.0.0.1"]


class SandboxError(RuntimeError):
    def __init__(self, status, body, path):
        super().__init__(f"{status} on {path}: {body[:300]}")
        self.status, self.body, self.path = status, body, path


def available() -> bool:
    return bool(KEY)


def _req(method, path, body=None, raw=None, query=None, content_type="application/json", timeout=60):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    data = None
    headers = {"X-Api-Key": KEY, "Accept": "application/json"}
    if raw is not None:
        data = raw if isinstance(raw, bytes) else raw.encode("utf-8")
        headers["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            ctype = r.headers.get("Content-Type", "")
            if "json" in ctype:
                doc = json.loads(payload.decode("utf-8") or "{}")
                return doc.get("data", doc) if isinstance(doc, dict) else doc
            return payload
    except urllib.error.HTTPError as e:
        raise SandboxError(e.code, e.read().decode("utf-8", "ignore"), path) from None


def whoami():
    return _req("GET", "/v1/whoami")


def shapes():
    return _req("GET", "/v1/shapes")


def create(name: str, egress=None, envs=None, shape=None, auto_pause=3600):
    body = {"shape": shape or SHAPE, "rootfs": ROOTFS, "name": name, "egress": NO_EGRESS if egress is None else egress,
            "auto_pause_after_seconds": auto_pause}
    if envs:
        body["envs"] = envs
    created = _req("POST", "/v1/sandboxes", body=body)
    return created["id"] if isinstance(created, dict) else created


def get(sid: str):
    return _req("GET", f"/v1/sandboxes/{sid}")


def wait(sid: str, want=("running",), timeout=120):
    t0 = time.time()
    last = None
    while time.time() - t0 < timeout:
        v = get(sid)
        last = v.get("status")
        if last in want:
            return v
        if last in ("failed", "destroyed"):
            raise SandboxError(409, f"sandbox {sid} is {last}", f"/v1/sandboxes/{sid}")
        time.sleep(1.5)
    raise SandboxError(504, f"sandbox {sid} still {last} after {timeout}s", f"/v1/sandboxes/{sid}")


def exec(sid: str, cmd: str, args=None, timeout_ms=60000):
    body = {"cmd": cmd, "args": args or [], "timeout_ms": timeout_ms}
    out = _req("POST", f"/v1/sandboxes/{sid}/exec", body=body, timeout=timeout_ms / 1000 + 15)
    if isinstance(out, dict) and isinstance(out.get("result"), dict):
        res = dict(out["result"]); res["exec_ms"] = out.get("exec_ms"); return res
    return out


def sh(sid: str, script: str, timeout_ms=60000):
    return exec(sid, "/bin/sh", ["-lc", script], timeout_ms)


def upload(sid: str, path: str, data: bytes | str):
    return _req("PUT", f"/v1/sandboxes/{sid}/files", raw=data, query={"path": path},
                content_type="application/octet-stream")


def download(sid: str, path: str) -> bytes:
    out = _req("GET", f"/v1/sandboxes/{sid}/files", query={"path": path})
    return out if isinstance(out, bytes) else json.dumps(out).encode()


def pause(sid: str):
    return _req("POST", f"/v1/sandboxes/{sid}/pause", body={})


def resume(sid: str):
    return _req("POST", f"/v1/sandboxes/{sid}/resume", body={})


def fork(sid: str, egress=None, start_paused=False):
    body = {"start_paused": start_paused, "egress": NO_EGRESS if egress is None else egress}
    child = _req("POST", f"/v1/sandboxes/{sid}/fork", body=body)
    return child["id"] if isinstance(child, dict) else child


def destroy(sid: str):
    try:
        return _req("DELETE", f"/v1/sandboxes/{sid}")
    except SandboxError as e:
        if e.status in (404, 409):
            return None
        raise


def egress(sid: str):
    return _req("GET", f"/v1/sandboxes/{sid}/egress")
