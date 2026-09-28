#!/usr/bin/env python3
"""Destroy stray Twin Gate base sandboxes on this account.

A base is a paused sandbox named twin-gate-base-* holding a copy of the brain. Each server keeps one and
destroys it on approve, reset and shutdown, but a container that is killed without SIGTERM, or a second
container started for the same deployment, leaves its base behind. This sweeps everything named
twin-gate-base-* that is paused or running, except the ids you pass and the one in ./state.

  python3 sweep_bases.py                 # dry run: list what would go
  python3 sweep_bases.py --yes [id ...]  # destroy, keeping the listed ids and the local marker
  python3 sweep_bases.py --yes --keep-url https://production-twin-gate.tyzo.nodeops.app
                                         # also keep the base a hosted copy reports at /api/base
"""
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sandbox_api as sbx  # noqa: E402

args = sys.argv[1:]
do = "--yes" in args
keep = {a for a in args if a.startswith("sb-")}
for i, a in enumerate(args):
    if a == "--keep-url" and i + 1 < len(args):
        try:
            with urllib.request.urlopen(args[i + 1].rstrip("/") + "/api/base", timeout=15) as r:
                cur = json.loads(r.read()).get("current")
                if cur:
                    keep.add(cur)
        except Exception as e:  # noqa: BLE001
            print(f"could not read {args[i + 1]}: {e}")
marker = Path(__file__).resolve().parent / "state" / "base-sandbox.json"
if marker.exists():
    keep.add(json.loads(marker.read_text()).get("id"))

items = sbx._req("GET", "/v1/sandboxes").get("data", [])
alive = [s for s in items if str(s.get("name", "")).startswith("twin-gate") and s.get("status") in ("paused", "running", "pausing")]
for s in alive:
    tag = "keep" if s["id"] in keep else ("destroy" if do else "would destroy")
    print(f"{tag:14} {s['id']}  {s['name']}  {s['status']}  {s.get('created_at', '')[11:19]}")
    if tag == "destroy":
        try:
            sbx.destroy(s["id"])
        except sbx.SandboxError as e:
            print(f"  failed: {e}")
if not do:
    print("dry run; add --yes to destroy")
