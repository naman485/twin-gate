#!/usr/bin/env python3
"""Twin Gate: an agent works in a live twin of the brain; production takes only what the twin proved.

Usage:
  twingate.py propose --task "..." [--brain ./brain] [--inject-error]
  twingate.py review  <id>
  twingate.py approve <id>
  twingate.py reject  <id>
  twingate.py list

The brain is a GBrain-style folder of markdown pages under git. A proposal creates a
twin: a git branch in a worktree on this machine, and, when CREATEOS_SANDBOX_API_KEY is
set, a forked CreateOS sandbox with egress denied where the change is applied and checked.
Every action is appended to a hash-chained log. Approve merges the branch into main and
destroys the twin. Nothing reaches main any other way.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import secrets
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import checks  # noqa: E402
import sandbox_api as sbx  # noqa: E402
import gbrain_bridge as gb  # noqa: E402

BRAIN = Path(os.environ.get("TWIN_BRAIN", HERE / "brain")).resolve()
STATE = Path(os.environ.get("TWIN_STATE", HERE / "state")).resolve()
OLLAMA = os.environ.get("OLLAMA_URL", "http://localhost:11434").rstrip("/")
MODEL = os.environ.get("TWIN_MODEL", "qwen2.5:7b")
AGENT = os.environ.get("TWIN_AGENT", "auto")  # auto | ollama | rules


# ---------- helpers ----------

def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git(*args, cwd=None, check=True):
    r = subprocess.run(["git", *args], cwd=str(cwd or BRAIN), capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def ensure_brain():
    BRAIN.mkdir(parents=True, exist_ok=True)
    if not (BRAIN / ".git").exists():
        git("init", "-q", "-b", "main")
        git("add", "-A")
        if git("status", "--porcelain").strip():
            git("-c", "user.name=twin-gate", "-c", "user.email=twin@local", "commit", "-q", "-m", "brain: initial state")
    (BRAIN / ".gitignore").write_text(".twins/\n", encoding="utf-8")
    STATE.mkdir(parents=True, exist_ok=True)


def state_path(tid):
    return STATE / f"{tid}.json"


def load(tid) -> dict:
    p = state_path(tid)
    if not p.exists():
        raise SystemExit(f"no twin {tid}")
    return json.loads(p.read_text())


def save(st: dict):
    state_path(st["id"]).write_text(json.dumps(st, indent=2))


def log(st: dict, actor: str, action: str, **detail):
    """Append-only, hash-chained. Each entry carries the hash of the previous one."""
    prev = st["log"][-1]["hash"] if st["log"] else "0" * 64
    entry = {"at": now(), "actor": actor, "action": action, "detail": detail, "prev": prev}
    entry["hash"] = hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()
    st["log"].append(entry)
    save(st)


def verify_log(st: dict) -> bool:
    prev = "0" * 64
    for e in st["log"]:
        body = {k: v for k, v in e.items() if k != "hash"}
        if body["prev"] != prev or hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest() != e["hash"]:
            return False
        prev = e["hash"]
    return True


def pages_index() -> str:
    lines = []
    for p in sorted(BRAIN.rglob("*.md")):
        if ".twins" in p.parts:
            continue
        rel = p.relative_to(BRAIN).as_posix()
        fm = checks._front(p.read_text(encoding="utf-8"))
        lines.append(f"- {rel}: {fm.get('type', '?')}, {fm.get('title', p.stem)}")
    return "\n".join(lines)


def read_page(rel: str, root: Path) -> str:
    p = (root / rel).resolve()
    return p.read_text(encoding="utf-8") if p.exists() and p.is_relative_to(root) else ""


# ---------- the agent ----------

PROMPT = """You are an agent working inside a twin of a company's brain: a folder of markdown pages.
Each page starts with front matter between --- lines: type, title, and fields.
Task: {task}

Pages in the brain:
{index}

Relevant pages:
{context}

Return ONLY a JSON object: {{"edits": [{{"path": "folder/page.md", "content": "full page text"}}], "note": "one sentence"}}.
Rules: keep front matter; a figure copied from another page must be declared in front matter as
reconcile: <field> = <page-path-without-.md>#<field>; do not add URLs; do not invent numbers."""


def ollama_edits(task: str, context: str) -> dict | None:
    import urllib.request
    body = {"model": MODEL, "stream": False, "format": "json",
            "messages": [{"role": "user", "content": PROMPT.format(task=task, index=pages_index(), context=context)}]}
    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            doc = json.loads(r.read())
        return json.loads(doc["message"]["content"])
    except Exception:
        return None


def rules_edits(task: str, inject_error: bool) -> dict:
    """Deterministic fallback for the demo: draft a chargeback dispute from the brain's pages."""
    so = checks._front(read_page("sales-orders/so-1014.md", BRAIN))
    shp = checks._front(read_page("shipping/shp-0031.md", BRAIN))
    weight = shp.get("net_kg", "0")
    if inject_error:
        weight = str(int(float(weight.replace(",", "")) * 0.9))
    page = f"""---
type: chargeback
title: CB-0003 short staple claim on INV-102
status: draft
sales_order: so-1014
shipment: shp-0031
customer: {so.get('customer', 'spinning-mill-a')}
net_kg: {weight}
reconcile: net_kg = shipping/shp-0031#net_kg
claim_cents_per_lb: 0.6
---

# CB-0003 short staple claim on INV-102

Customer [[sales-orders/so-1014]] ({so.get('customer', 'the mill')}) reports short staple length on invoice INV-102 and
deducts 0.6 cents per lb. Shipment [[shipping/shp-0031]] carried {weight} kg net.

## Draft dispute to the broker

The outbound QC test on this lot recorded staple length within contract. The retained sample
is held and can be re-tested by an independent lab at the mill's cost if the claim stands.
We do not accept the deduction on invoice INV-102 pending that test.

Owner to approve before this leaves the building.
"""
    return {"edits": [{"path": "chargebacks/cb-0003.md", "content": page}],
            "note": "Drafted CB-0003 from SO-1014 and SHP-0031" + (" (weight copied wrong on purpose)" if inject_error else "")}


RETRY = """Your previous attempt was rejected by the gate. Failed checks:
{failures}

Fix only what failed. Return the corrected JSON with the full page content."""


def ollama_retry(task: str, context: str, failures: str, previous: dict) -> dict | None:
    import urllib.request
    msgs = [{"role": "user", "content": PROMPT.format(task=task, index=pages_index(), context=context)},
            {"role": "assistant", "content": json.dumps(previous)},
            {"role": "user", "content": RETRY.format(failures=failures)}]
    body = {"model": MODEL, "stream": False, "format": "json", "messages": msgs}
    req = urllib.request.Request(OLLAMA + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            return json.loads(json.loads(r.read())["message"]["content"])
    except Exception:
        return None


def run_agent(task: str, inject_error: bool) -> tuple[dict, str]:
    mode = AGENT
    if mode in ("auto", "ollama") and not inject_error:
        ctx = "\n\n".join(read_page(rel, BRAIN) for rel in ("sales-orders/so-1014.md", "shipping/shp-0031.md", "customers/spinning-mill-a.md"))
        out = ollama_edits(task, ctx)
        if out and isinstance(out.get("edits"), list) and out["edits"]:
            return out, f"ollama:{MODEL}"
        if mode == "ollama":
            raise SystemExit("ollama unavailable and TWIN_AGENT=ollama")
    return rules_edits(task, inject_error), "rules"


# ---------- the twin ----------

def brain_tar() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for p in sorted(BRAIN.rglob("*")):
            if p.is_file() and ".git" not in p.parts and ".twins" not in p.parts:
                t.add(p, arcname=p.relative_to(BRAIN).as_posix())
        t.add(HERE / "checks.py", arcname="checks.py")
        t.add(HERE / "checks_runner.py", arcname="checks_runner.py")
    return buf.getvalue()


def base_sandbox(st: dict) -> str | None:
    """A paused sandbox holding the brain at its known state. Forked per proposal."""
    marker = STATE / "base-sandbox.json"
    if marker.exists():
        info = json.loads(marker.read_text())
        try:
            v = sbx.get(info["id"])
            if v.get("status") in ("paused", "pausing", "running"):
                if v.get("status") == "running":
                    sbx.pause(info["id"])
                    sbx.wait(info["id"], want=("paused",), timeout=90)
                return info["id"]
        except sbx.SandboxError:
            pass
    sid = sbx.create("twin-gate-base-" + secrets.token_hex(2))
    sbx.wait(sid)
    sbx.sh(sid, "mkdir -p /twin && rm -rf /twin/*")
    sbx.upload(sid, "/twin/brain.tgz", brain_tar())
    sbx.sh(sid, "cd /twin && tar xzf brain.tgz && rm brain.tgz && ls")
    sbx.pause(sid)
    sbx.wait(sid, want=("paused",), timeout=90)
    marker.write_text(json.dumps({"id": sid, "at": now()}))
    log(st, "twin-gate", "base sandbox ready", sandbox=sid, note="brain uploaded at its known state, paused")
    return sid


def twin_in_sandbox(st: dict, edits: list[dict], changed: list[str]) -> dict | None:
    if not sbx.available():
        return None
    base = base_sandbox(st)
    child = sbx.fork(base)
    sbx.wait(child)
    eg = sbx.egress(child)
    log(st, "twin-gate", "forked twin sandbox", sandbox=child, forked_from=base, egress=eg.get("egress"))
    for e in edits:
        sbx.upload(child, f"/twin/{e['path']}", e["content"])
        log(st, "agent", "wrote file in twin", sandbox=child, path=e["path"])
    net = sbx.sh(child, "python3 -c \"import urllib.request;urllib.request.urlopen('https://example.com',timeout=5)\" 2>&1 | tail -1 || true", 20000)
    res = sbx.sh(child, f"cd /twin && python3 checks_runner.py {' '.join(changed)}", 60000)
    out = (res.get("stdout") or "").strip()
    try:
        remote = json.loads(out.splitlines()[-1]) if out else None
    except Exception:
        remote = None
    log(st, "twin-gate", "checks ran inside twin sandbox", sandbox=child,
        egress_probe=(net.get("stdout") or net.get("stderr") or "").strip()[-120:], exit_code=res.get("exit_code"))
    return {"id": child, "base": base, "egress": eg.get("egress"), "checks": remote,
            "egress_probe": (net.get("stdout") or net.get("stderr") or "").strip()[-160:]}


def propose(task: str, inject_error: bool) -> str:
    ensure_brain()
    tid = "tg-" + secrets.token_hex(2)
    st = {"id": tid, "task": task, "created": now(), "status": "proposed", "log": [], "sandbox": None}
    save(st)
    log(st, "member", "proposed", task=task)
    wt = BRAIN / ".twins" / tid
    git("worktree", "add", "-q", "-b", f"twin/{tid}", str(wt), "main")
    log(st, "twin-gate", "created twin", branch=f"twin/{tid}", worktree=str(wt))

    edits, agent = run_agent(task, inject_error)
    changed = [e["path"] for e in edits["edits"]]
    base_text = {rel: read_page(rel, BRAIN) for rel in changed}
    for e in edits["edits"]:
        p = wt / e["path"]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(e["content"], encoding="utf-8")
        log(st, "agent", "edited page in twin", path=e["path"], agent=agent, bytes=len(e["content"]))
    git("add", "-A", cwd=wt)
    git("-c", "user.name=twin-agent", "-c", "user.email=agent@twin", "commit", "-q", "-m", f"{tid}: {edits.get('note', task)}", cwd=wt)

    local_checks = checks.run_all(wt, changed, base_text)
    log(st, "twin-gate", "checks ran on twin branch", results=[(c["name"], c["ok"]) for c in local_checks])
    if agent.startswith("ollama") and not all(c["ok"] for c in local_checks) and os.environ.get("TWIN_RETRIES", "1") != "0":
        failures = "\n".join(f"- {c['name']}: {c['detail']}" for c in local_checks if not c["ok"])
        ctx = "\n\n".join(read_page(rel, BRAIN) for rel in ("sales-orders/so-1014.md", "shipping/shp-0031.md", "customers/spinning-mill-a.md"))
        fixed = ollama_retry(task, ctx, failures, edits)
        if fixed and isinstance(fixed.get("edits"), list) and fixed["edits"]:
            log(st, "agent", "read the failed checks and retried in the same twin", failed=[c["name"] for c in local_checks if not c["ok"]])
            edits = fixed
            changed = sorted(set(changed) | {e["path"] for e in edits["edits"]})
            for e in edits["edits"]:
                p = wt / e["path"]; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(e["content"], encoding="utf-8")
                log(st, "agent", "edited page in twin (retry)", path=e["path"], agent=agent, bytes=len(e["content"]))
            git("add", "-A", cwd=wt)
            git("-c", "user.name=twin-agent", "-c", "user.email=agent@twin", "commit", "-q", "-m", f"{tid}: retry after failed checks", cwd=wt)
            local_checks = checks.run_all(wt, changed, base_text)
            log(st, "twin-gate", "checks ran again on twin branch", results=[(c["name"], c["ok"]) for c in local_checks])
    try:
        sb = twin_in_sandbox(st, edits["edits"], changed)
    except sbx.SandboxError as e:
        sb = {"error": str(e)}
        log(st, "twin-gate", "sandbox unavailable", error=str(e)[:200])

    st.update({"agent": agent, "note": edits.get("note", ""), "changed": changed,
               "checks": local_checks, "sandbox": sb, "diff": git("diff", "main", f"twin/{tid}", "--stat"),
               "status": "passed" if all(c["ok"] for c in local_checks) else "failed"})
    save(st)
    log(st, "twin-gate", "gate " + st["status"])
    return tid


def review(tid: str) -> dict:
    st = load(tid)
    st["full_diff"] = git("diff", "main", f"twin/{tid}") if st["status"] not in ("approved", "rejected") else st.get("full_diff", "")
    st["log_intact"] = verify_log(st)
    return st


def approve(tid: str, who="owner"):
    st = load(tid)
    if st["status"] != "passed":
        raise SystemExit(f"{tid} is {st['status']}; only a passed twin can be approved")
    st["full_diff"] = git("diff", "main", f"twin/{tid}")
    git("merge", "-q", "--no-ff", "-m", f"approve {tid}: {st.get('note', '')}", f"twin/{tid}")
    log(st, who, "approved and merged", branch=f"twin/{tid}")
    if gb.available():
        res = gb.sync(BRAIN)
        st["gbrain"] = {"synced": res.get("ok", False), "out": (res.get("stdout") or res.get("stderr") or res.get("reason") or "")[-300:]}
        log(st, "twin-gate", "synced into GBrain" if res.get("ok") else "GBrain sync failed", detail=st["gbrain"]["out"][-160:])
    cleanup(st)
    st["status"] = "approved"
    save(st)


def reject(tid: str, who="owner"):
    st = load(tid)
    st["full_diff"] = git("diff", "main", f"twin/{tid}", check=False)
    log(st, who, "rejected", branch=f"twin/{tid}")
    cleanup(st)
    st["status"] = "rejected"
    save(st)


def cleanup(st: dict):
    wt = BRAIN / ".twins" / st["id"]
    git("worktree", "remove", "--force", str(wt), check=False)
    git("branch", "-D", f"twin/{st['id']}", check=False)
    sb = st.get("sandbox") or {}
    if sb.get("id"):
        try:
            sbx.destroy(sb["id"])
            log(st, "twin-gate", "destroyed twin sandbox", sandbox=sb["id"])
        except sbx.SandboxError as e:
            log(st, "twin-gate", "destroy failed", error=str(e)[:160])


def list_twins() -> list[dict]:
    out = []
    for p in sorted(STATE.glob("tg-*.json")):
        st = json.loads(p.read_text())
        out.append({k: st.get(k) for k in ("id", "task", "status", "created", "agent", "changed")})
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("propose"); p.add_argument("--task", required=True); p.add_argument("--inject-error", action="store_true")
    for c in ("review", "approve", "reject"):
        sub.add_parser(c).add_argument("id")
    sub.add_parser("list")
    a = ap.parse_args()
    if a.cmd == "propose":
        tid = propose(a.task, a.inject_error)
        st = load(tid)
        print(json.dumps({"id": tid, "status": st["status"], "agent": st["agent"], "changed": st["changed"],
                          "checks": st["checks"], "sandbox": st["sandbox"]}, indent=2))
    elif a.cmd == "review":
        print(json.dumps(review(a.id), indent=2))
    elif a.cmd == "approve":
        approve(a.id); print(f"{a.id} approved and merged into main")
    elif a.cmd == "reject":
        reject(a.id); print(f"{a.id} rejected")
    else:
        print(json.dumps(list_twins(), indent=2))


if __name__ == "__main__":
    main()
