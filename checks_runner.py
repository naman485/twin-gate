"""Runs the same checks inside the twin sandbox. Prints one JSON line."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checks  # noqa: E402

root = Path(__file__).resolve().parent
changed = sys.argv[1:]
base_text = {}
results = checks.run_all(root, changed, base_text)
print(json.dumps({"ok": all(r["ok"] for r in results), "results": results, "where": "sandbox"}))
