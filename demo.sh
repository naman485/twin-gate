#!/bin/sh
# Stage demo: reset, wrong number (gate fails), clean run (gate passes), approve.
set -e
cd "$(dirname "$0")"
rm -rf brain; mkdir -p state; find state -name "tg-*.json" -delete; cp -R brain-seed brain
export GBRAIN_HOME="${GBRAIN_HOME:-$PWD/.gbrain}"; export PATH="$HOME/.bun/bin:$PATH"
if command -v gbrain >/dev/null; then rm -rf "$GBRAIN_HOME"; (cd brain && { gbrain init --pglite --no-embedding --json >/dev/null 2>&1 || true; }; { gbrain import . --no-embed >/dev/null 2>&1 || true; }); echo "GBrain recall before approve:"; gbrain search "chargeback INV-102" --json --limit 2 2>/dev/null | python3 -c 'import json,sys;r=json.load(sys.stdin);print("   ", [x["slug"] for x in r] or "nothing about a chargeback yet")'; fi
BAD=$(python3 twingate.py propose --task "Draft the dispute for the short staple chargeback on INV-102" --inject-error)
echo "$BAD" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["id"],d["status"]);[print("  ",("PASS" if c["ok"] else "FAIL"),c["name"],"|",c["detail"][:100]) for c in d["checks"]]'
BID=$(echo "$BAD" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
OUT=$(python3 twingate.py propose --task "Draft the dispute for the short staple chargeback on INV-102")
echo "$OUT" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["id"],d["status"]);[print("  ",("PASS" if c["ok"] else "FAIL"),c["name"]) for c in d["checks"]];print("   sandbox:",(d["sandbox"] or {}).get("id","none"))'
TID=$(echo "$OUT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
python3 twingate.py approve "$TID"
python3 twingate.py reject "$BID"
git -C brain log --oneline -3
if command -v gbrain >/dev/null; then echo "GBrain recall after approve:"; gbrain search "chargeback INV-102" --json --limit 2 2>/dev/null | python3 -c 'import json,sys;r=json.load(sys.stdin);print("   ", [x["slug"] for x in r])'; fi
