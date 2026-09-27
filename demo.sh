#!/bin/sh
# Stage demo: reset, wrong number (gate fails), clean run (gate passes), approve.
set -e
cd "$(dirname "$0")"
rm -rf brain state; cp -R brain-seed brain
python3 twingate.py propose --task "Draft the dispute for the short staple chargeback on INV-102" --inject-error | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["id"],d["status"]);[print("  ",("PASS" if c["ok"] else "FAIL"),c["name"],"|",c["detail"][:100]) for c in d["checks"]]'
OUT=$(python3 twingate.py propose --task "Draft the dispute for the short staple chargeback on INV-102")
echo "$OUT" | python3 -c 'import json,sys;d=json.load(sys.stdin);print(d["id"],d["status"]);[print("  ",("PASS" if c["ok"] else "FAIL"),c["name"]) for c in d["checks"]];print("   sandbox:",(d["sandbox"] or {}).get("id","none"))'
TID=$(echo "$OUT" | python3 -c 'import json,sys;print(json.load(sys.stdin)["id"])')
python3 twingate.py approve "$TID"
git -C brain log --oneline -3
