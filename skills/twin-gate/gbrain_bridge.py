"""GBrain bridge. The brain folder is a GBrain content root; GBrain's index moves only on approve.

Uses the gbrain CLI (github.com/garrytan/gbrain). Everything is optional: if the CLI is
absent, every call returns {"ok": False, "reason": "gbrain not installed"} and Twin Gate keeps
working on the folder alone.

Env:
  GBRAIN_BIN   path to the gbrain binary (default: gbrain on PATH)
  GBRAIN_HOME  GBrain home for an isolated local brain (default ~/twin-gate/.gbrain)
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
BIN = os.environ.get("GBRAIN_BIN") or shutil.which("gbrain") or os.path.expanduser("~/.bun/bin/gbrain")
HOME = os.environ.get("GBRAIN_HOME", str(HERE / ".gbrain"))


def available() -> bool:
    return bool(BIN) and os.path.exists(BIN)


def _run(args: list[str], timeout=180, cwd=None) -> dict:
    if not available():
        return {"ok": False, "reason": "gbrain not installed"}
    env = dict(os.environ, GBRAIN_HOME=HOME)
    Path(HOME).mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run([BIN, *args], capture_output=True, text=True, timeout=timeout, env=env, cwd=cwd)
    except subprocess.TimeoutExpired:
        return {"ok": False, "reason": f"gbrain {' '.join(args[:2])} timed out"}
    out = (r.stdout or "").strip()
    return {"ok": r.returncode == 0, "code": r.returncode, "stdout": out[:200000], "stderr": (r.stderr or "").strip()[-1500:]}


def init(brain: Path) -> dict:
    """Create a keyless local brain and import the folder once."""
    res = _run(["init", "--pglite", "--no-embedding", "--json"], cwd=str(brain))
    imp = _run(["import", ".", "--no-embed"], timeout=300, cwd=str(brain))
    return {"ok": imp.get("ok", False), "init": res, "import": imp}


def sync(brain: Path) -> dict:
    """Commit-driven incremental sync: only what approve merged into main is indexed."""
    res = _run(["sync", "--repo", str(brain), "--no-pull", "--json"], timeout=300, cwd=str(brain))
    if not res.get("ok"):
        imp = _run(["import", ".", "--no-embed"], timeout=300, cwd=str(brain))
        imp["fallback"] = "import"; imp["sync_error"] = (res.get("stderr") or res.get("stdout") or res.get("reason") or "")[-200:]
        return imp
    return res


def search(query: str, limit=5) -> dict:
    res = _run(["search", query, "--json", "--limit", str(limit)], timeout=60)
    if res.get("ok"):
        out = res["stdout"]
        try:
            lines = [ln for ln in out.splitlines() if not ln.startswith("[gbrain]")]
            clean = "\n".join(lines)
            start = clean.find("[\n") if "[\n" in clean else clean.find("[")
            rows = json.loads(clean[start:]) if start >= 0 else []
            res["results"] = [{"slug": r.get("slug"), "title": r.get("title"), "type": r.get("type"),
                               "score": round(float(r.get("score") or 0), 3)} for r in rows if isinstance(r, dict)]
        except Exception:
            res["results"] = []
    return res


def stats() -> dict:
    return _run(["stats", "--json"], timeout=60)


def reset(brain: Path) -> dict:
    """Throw the local index away and rebuild it from the seed brain (stage reset)."""
    if not available():
        return {"ok": False, "reason": "gbrain not installed"}
    if Path(HOME).exists():
        shutil.rmtree(HOME, ignore_errors=True)
    return init(brain)
