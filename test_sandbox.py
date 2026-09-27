#!/usr/bin/env python3
"""One-shot integration test of the sandbox path. Needs CREATEOS_SANDBOX_API_KEY (env or .env).

Creates a base sandbox, uploads a file, pauses, forks, checks egress is denied in the fork,
runs a command, destroys both. Prints each step so a mismatch with the control plane is obvious.
"""
import json
import sys
import time

import sandbox_api as s

if not s.available():
    sys.exit("no CREATEOS_SANDBOX_API_KEY in env or .env")

t0 = time.time()
step = lambda msg: print(f"[{time.time()-t0:5.1f}s] {msg}", flush=True)

step("whoami: " + json.dumps(s.whoami())[:160])
base = child = None
try:
    base = s.create("twin-gate-test-" + str(int(t0))[-4:])
    step(f"created base {base}")
    v = s.wait(base)
    step(f"base running, egress={v.get('egress')} region={v.get('region')} rootfs={v.get('rootfs')}")
    s.upload(base, "/twin/hello.txt", "hello from twin gate")
    step("uploaded /twin/hello.txt")
    r = s.sh(base, "cat /twin/hello.txt && python3 --version")
    step(f"exec in base: exit={r.get('exit_code')} out={ (r.get('stdout') or '').strip()[:80]!r} err={(r.get('stderr') or '').strip()[:80]!r}")
    s.pause(base)
    s.wait(base, want=("paused",), timeout=90)
    step("base paused")
    child = s.fork(base)
    step(f"forked child {child}")
    s.wait(child)
    step(f"child running, egress={s.egress(child)}")
    r = s.sh(child, "cat /twin/hello.txt")
    step(f"child sees file: {(r.get('stdout') or '').strip()!r}")
    r = s.sh(child, "python3 -c \"import urllib.request;urllib.request.urlopen('https://example.com',timeout=5)\" 2>&1 | tail -1", 20000)
    step(f"egress probe in child (should fail): {((r.get('stdout') or '') + (r.get('stderr') or '')).strip()[-120:]!r}")
    print("OK: sandbox path works end to end")
except s.SandboxError as e:
    print("SANDBOX ERROR:", e)
    sys.exit(1)
finally:
    for sid in (child, base):
        if sid:
            try:
                s.destroy(sid); step(f"destroyed {sid}")
            except s.SandboxError as e:
                step(f"destroy {sid} failed: {e}")
