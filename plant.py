"""Plant example: a small textile plant's workflows, every record written through the gate.

Inputs the plant already produces: two truck scale SMS, a QC voice note in three languages, a
broker's message about a mill's claim. The agent turns them into records: scale ticket, grower
settlement, chargeback and dispute, a learned procedure. It never writes to the brain. Each run's
records go into one twin, Twin Gate checks them (on the branch and inside a forked sandbox), and
a person approves the merge. All data is synthetic.

Ported from Factory Brain, the same author's console, so the two demos share one shape.
Model use is optional: with TWIN_AGENT=auto and Ollama reachable, the voice note and the dispute
go through the model; otherwise rules, and the page says which ran.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
import threading
import urllib.request
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "plant"))
import twingate as tg  # noqa: E402
from kanta_pair import pair  # noqa: E402

LB_PER_KG = 2.20462
STATE = {"sms": [], "pending": None, "llm_ok": None}


def reset():
    STATE.update(sms=[], pending=None)


# ---------- pages ----------

def read(rel: str) -> str:
    return tg.read_page(rel, tg.BRAIN)


def front(text: str) -> dict:
    return tg.checks._front(text)


def page(kind: str, title: str, body: str, **meta) -> str:
    head = "\n".join([f"type: {kind}", f"title: {title}"] + [f"{k}: {v}" for k, v in meta.items()])
    return f"---\n{head}\n---\n\n# {title}\n\n{body.strip()}\n"


def usd(n: float) -> str:
    return f"${n:,.2f}"


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s or "grower-" + hashlib.sha1(text.encode()).hexdigest()[:6]


def graph() -> dict:
    nodes, edges = [], []
    for p in sorted(tg.BRAIN.rglob("*.md")):
        if ".twins" in p.parts or ".git" in p.parts:
            continue
        rel = p.relative_to(tg.BRAIN).with_suffix("").as_posix()
        text = p.read_text(encoding="utf-8")
        meta = front(text)
        nodes.append({"id": rel, "title": meta.get("record", meta.get("title", rel)), "type": meta.get("type", "page")})
        for link in set(re.findall(r"\[\[([^\]|]+)", text)):
            edges.append({"source": rel, "target": link})
    ids = {n["id"] for n in nodes}
    return {"nodes": nodes, "edges": [e for e in edges if e["target"] in ids]}


def config() -> dict:
    return {"agent": tg.AGENT, "model": tg.MODEL if tg.AGENT != "rules" else None, "llm_reachable": STATE["llm_ok"],
            "speech": "none", "sandbox": tg.sbx.available(), "gbrain": tg.gb.available(),
            "base_ready": tg._base_marker().exists()}


# ---------- optional model ----------

def _chat(prompt: str, as_json: bool):
    if tg.AGENT not in ("auto", "ollama"):
        return None
    body = {"model": tg.MODEL, "stream": False, "messages": [{"role": "user", "content": prompt}], "options": {"temperature": 0}}
    if as_json:
        body["format"] = "json"
    try:
        req = urllib.request.Request(tg.OLLAMA + "/api/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=90) as r:
            text = json.loads(r.read())["message"]["content"]
        STATE["llm_ok"] = True
        return json.loads(text) if as_json else text.strip()
    except Exception:  # noqa: BLE001  a missing model must never stop the plant
        STATE["llm_ok"] = False
        return None


def _agent_label() -> str:
    return f"plant ollama:{tg.MODEL}" if STATE["llm_ok"] else "plant rules"


def _start(task: str, edits: list[dict], inject_error: bool = False, background: bool = True) -> str:
    """Hand the records to Twin Gate as one twin. The page polls /api/twin/<id>."""
    twin = tg.propose_start(task, inject_error, edits=edits, agent=_agent_label())
    if background:
        threading.Thread(target=tg.propose_run, args=(twin,), daemon=True).start()
    else:
        tg.propose_run(twin)
    return twin


# ---------- 1. receiving: two scale SMS -> scale ticket (held for the twin) ----------

def on_sms(body: str) -> dict:
    STATE["sms"].append((datetime.now(), body))
    weighments, _ = pair(STATE["sms"])
    done = [w for w in weighments if w.status in ("PAIRED", "NEEDS_CONFIRM") and w.second]
    latest = done[-1] if done and done[-1].second.body == body else None
    if not latest:
        return {"reply": None, "note": "first scale reading stored, waiting for the second"}
    tid = f"ST-{latest.slip or latest.first.received.strftime('%H%M')}"
    path = f"receiving/{tid.lower()}.md"
    direction = {"purchase": "Inbound", "dispatch": "Outbound"}.get(latest.direction, "Unknown")
    content = page(
        "ticket", f"Scale ticket {tid}",
        f"{direction} truck {latest.vehicle}. Gross {latest.gross:,} kg, tare {latest.tare:,} kg, net {latest.net:,} kg raw cotton.\n"
        f"Source: two truck scale SMS, received {latest.first.received:%H:%M} and {latest.second.received:%H:%M}. No manual entry.\n"
        f"Exceptions: {'; '.join(latest.flags) or 'none'}",
        record=tid, truck=latest.vehicle, direction=direction, gross_kg=latest.gross, tare_kg=latest.tare,
        net_kg=latest.net, status="Awaiting QC",
    )
    STATE["pending"] = {"path": path, "tid": tid, "net": latest.net, "gross": latest.gross, "tare": latest.tare,
                        "vehicle": latest.vehicle, "content": content}
    reply = (f"{tid}: truck {latest.vehicle}, net {latest.net:,} kg raw cotton received.\n"
             "QC: send grower name, price per 100 kg and moisture (a voice note is fine).")
    return {"reply": reply, "record": tid, "path": path[:-3], "gross_kg": latest.gross, "tare_kg": latest.tare,
            "net_kg": latest.net, "vehicle": latest.vehicle, "flags": latest.flags,
            "note": "drafted; it enters the twin with the settlement"}


# ---------- 2. QC voice note -> grower settlement, one twin for ticket + grower + settlement ----------

NUM_WORDS = {"aath": 8, "आठ": 8, "आत": 8, "आथ": 8, "saat": 7, "सात": 7, "नौ": 9, "nau": 9, "दस": 10, "das": 10}
NAMES = {"रमेश": "Ramesh", "पाटिल": "Patil", "सुरेश": "Suresh", "देशमुख": "Deshmukh", "जाधव": "Jadhav"}


def rule_extract(text: str) -> dict:
    """No model: digits, number words, and the two words after farmer or kisan."""
    nums = [float(n.replace(",", "")) for n in re.findall(r"\d[\d,.]*\d|\d", text)]
    moist = next((n for n in nums if 1 <= n <= 20), None)
    if moist is None:
        m = re.search(r"(?:moisture|ओलावा|मॉइश्चर|मौईश्चर|नमी)\W*(\S+)", text, re.I)
        moist = NUM_WORDS.get(m.group(1).lower().strip(",.")) if m else None
    name = re.search(r"(?:farmer|kisan|फार्मर|किसान)\s+(\S+\s+\S+?)[,.]", text, re.I)
    return {"farmer": name.group(1) if name else None,
            "rate_per_quintal": next((n for n in nums if 20 <= n <= 500), None), "moisture_pct": moist}


def latinise(name: str | None) -> str | None:
    if not name:
        return None
    return " ".join(NAMES.get(w, w) for w in name.split())


def tally_xml(grower: str, amount: float, p: dict) -> str:
    return f"""<ENVELOPE><HEADER><TALLYREQUEST>Import Data</TALLYREQUEST></HEADER><BODY><IMPORTDATA>
<REQUESTDESC><REPORTNAME>Vouchers</REPORTNAME></REQUESTDESC><REQUESTDATA><TALLYMESSAGE xmlns:UDF="TallyUDF">
<VOUCHER VCHTYPE="Purchase" ACTION="Create"><DATE>{datetime.now():%Y%m%d}</DATE>
<VOUCHERTYPENAME>Purchase</VOUCHERTYPENAME><PARTYLEDGERNAME>{grower}</PARTYLEDGERNAME>
<NARRATION>Raw cotton, {p['tid']}, truck {p['vehicle']}, net {p['net']} kg. SYNTHETIC DEMO</NARRATION>
<ALLLEDGERENTRIES.LIST><LEDGERNAME>{grower}</LEDGERNAME><ISDEEMEDPOSITIVE>No</ISDEEMEDPOSITIVE><AMOUNT>{amount}</AMOUNT></ALLLEDGERENTRIES.LIST>
<ALLLEDGERENTRIES.LIST><LEDGERNAME>Purchases - Raw Cotton</LEDGERNAME><ISDEEMEDPOSITIVE>Yes</ISDEEMEDPOSITIVE><AMOUNT>-{amount}</AMOUNT></ALLLEDGERENTRIES.LIST>
</VOUCHER></TALLYMESSAGE></REQUESTDATA></IMPORTDATA></BODY></ENVELOPE>"""


def on_voice(transcript: str, background: bool = True) -> dict:
    p = STATE["pending"]
    if not p:
        return {"error": "No scale ticket awaiting QC. Send the two scale SMS first."}
    fields = _chat(
        "A textile plant's QC grader sent this voice note about a truck of raw cotton. It mixes three languages, "
        "often in Devanagari. Return JSON with keys farmer (the grower's name in English letters, e.g. Ramesh Patil; "
        "drop the word kisan or farmer), rate_per_quintal (price in US dollars per 100 kg, a number), moisture_pct "
        "(a number). Words: फार्मर or किसान = farmer; भाव = price; ओलावा or मॉइश्चर = moisture; टक्के or प्रतिशत = "
        "percent; आठ, आत or आथ = 8; डॉलर = dollars. A number word may be glued to the next word. Use null if absent.\n\n"
        f"Voice note: {transcript}", as_json=True) or {}
    fb = rule_extract(transcript)
    fields = {k: fields.get(k) or fb.get(k) for k in ("farmer", "rate_per_quintal", "moisture_pct")}
    grower = latinise(fields["farmer"]) or "Unnamed grower"
    moist = f"{float(fields['moisture_pct']):g}" if fields["moisture_pct"] is not None else "?"
    rate = float(fields["rate_per_quintal"] or 0)
    amount = round(p["net"] / 100 * rate, 2)
    vendor = "vendors/" + slug(grower)
    gs = p["tid"].replace("ST-", "GS-")
    spath = f"payables/{gs.lower()}"
    today = f"{datetime.now():%d %b}"

    vendor_text = read(vendor + ".md") or page("vendor", grower, "Grower. Supplies raw cotton.\n\n## History",
                                               record=grower, category="Grower", status="Active")
    vendor_text = vendor_text.rstrip() + f"\n- {today}: [[{spath}]], {p['net']:,} kg at {usd(rate)}/100 kg, {usd(amount)}\n"
    settlement = page(
        "settlement", f"Grower settlement {gs}",
        f"Vendor: [[{vendor}]]. Scale ticket: [[{p['path'][:-3]}]].\n"
        f"{p['net']:,} kg raw cotton at {usd(rate)} per 100 kg, moisture {moist}%. Amount {usd(amount)}.\n"
        f"Price and moisture captured from a voice note: \"{transcript.strip()}\"\n"
        "Posting: queued for the accounting system (Tally), which posts when the office PC is on.",
        record=gs, vendor=grower, net_kg=p["net"], reconcile=f"net_kg = {p['path'][:-3]}#net_kg",
        price=f"{usd(rate)} per 100 kg", moisture=f"{moist}%", amount_usd=f"{amount:.2f}", status="Pending AP approval",
    )
    edits = [{"path": p["path"], "content": p["content"]},
             {"path": vendor + ".md", "content": vendor_text},
             {"path": spath + ".md", "content": settlement}]
    task = f"Receive truck {p['vehicle']} and settle {grower}: {p['tid']}, {gs}"
    twin = _start(task, edits, background=background)
    STATE["pending"] = None
    return {"twin": twin, "fields": fields, "grower": grower, "record": gs, "path": spath, "ticket": p["tid"],
            "vendor": vendor, "net_kg": p["net"], "rate": rate, "moisture": moist, "amount_usd": amount,
            "amount": usd(amount), "tally_xml": tally_xml(grower, amount, p), "extracted_by": _agent_label(),
            "records": [p["path"][:-3], vendor, spath],
            "reply": f"{gs} ready: {grower}, {p['net']:,} kg x {usd(rate)}/100 kg = {usd(amount)}. Moisture {moist}%."}


# ---------- 3. a mill's claim -> evidence -> dispute, and a learned procedure ----------

def _val(text: str, label: str) -> str:
    m = re.search(rf"{label}[^:\n]*:\s*([^\n]+)", text, re.I)
    return m.group(1).strip().rstrip(".") if m else "on record"


def fallback_reply(so_id, invoice, order, shipment, param) -> str:
    return (f"Dear Joshi ji,\n\nRe the {param} chargeback on {invoice} under {so_id}: the contract spec is "
            f"{_val(order, param)}. Our outbound QC recorded {_val(shipment, param)}. Retained sample "
            f"{_val(shipment, 'retained sample').split(',')[0]} is sealed and held at the plant. We propose a joint re-test "
            "of that sample before any deduction.")


def on_claim(text: str, inject_error: bool = False, background: bool = True) -> dict:
    ref = re.search(r"\b(SO-\d+|INV-\d+)\b", text)
    so_id, ship_path = None, None
    for d in sorted((tg.BRAIN / "shipping").glob("*.md")):
        body = d.read_text(encoding="utf-8")
        if ref and ref.group(1) in body:
            ship_path = d
            m = re.search(r"\[\[sales-orders/([^\]]+)\]\]", body)
            so_id = m.group(1).upper() if m else None
    param = next((k for k in ("staple", "micronaire", "rd", "moisture", "trash", "weight") if re.search(rf"\b{k}", text, re.I)), "quality")
    family = "weight" if param == "weight" else "quality"
    sop_rel = f"sops/sop-{family}-chargeback"
    learned = bool(read(sop_rel + ".md"))

    order = read(f"sales-orders/{so_id.lower()}.md") if so_id else ""
    shipment = ship_path.read_text(encoding="utf-8") if ship_path else ""
    cust = re.search(r"\[\[(customers/[^\]]+)\]\]", order)
    customer = read(cust.group(1) + ".md") if cust else ""
    ship_meta, cust_meta = front(shipment), front(customer)
    steps = [f"Sales order {so_id or '?'}: {'found' if order else 'NOT FOUND'}",
             f"Shipment {ship_meta.get('record', '?')} with outbound QC: {'found' if shipment else 'NOT FOUND'}",
             f"Customer history, {cust_meta.get('record', '?')}: {'found' if customer else 'NOT FOUND'}"]
    if not learned:
        steps.append("No procedure for this chargeback type yet: working it out from the records")

    net_true = int(float(ship_meta.get("net_kg", 0) or 0))
    net_written = round(net_true * 0.9) if inject_error else net_true
    cents_m = re.search(r"(\d+(?:\.\d+)?)\s*cents? per lb", text)
    cents = float(cents_m.group(1)) if cents_m else 0.0
    at_risk = round(cents / 100 * net_written * LB_PER_KG, 2)
    invoice = ship_meta.get("invoice", "?")

    draft = _chat(
        "You write for a textile plant. A customer (a spinning mill) has issued a quality chargeback. Write the plant's "
        "dispute to the broker, at most 90 words, in plain business English. Start with \"Dear Joshi ji,\" and do not sign. "
        "State the sales order number, the invoice number, the contract spec, the outbound QC result and the retained "
        "sample number, copying numbers and units exactly as written in the records. Micronaire has no unit. Do not "
        "mention price or what the photos show. Propose a joint re-test of the retained sample before any deduction.\n\n"
        f"CHARGEBACK:\n{text}\n\nSALES ORDER:\n{order}\n\nSHIPMENT:\n{shipment}\n\nCUSTOMER:\n{customer}\n\n"
        + (f"HOW THIS PLANT HANDLES THIS TYPE (learned procedure):\n{read(sop_rel + '.md')}" if learned else ""),
        as_json=False) or fallback_reply(so_id, invoice, order, shipment, param)
    draft = re.sub(r"\s*For the (plant|gin)\.?\s*$", "", draft, flags=re.I).strip() + "\n\nFor the plant"

    n = len(list((tg.BRAIN / "chargebacks").glob("*.md"))) + 1 if (tg.BRAIN / "chargebacks").exists() else 1
    cb = f"CB-{n:04d}"
    cb_rel = f"chargebacks/{cb.lower()}"
    ship_rel = f"shipping/{ship_path.stem}" if ship_path else None
    links = " ".join(f"[[{x}]]" for x in [so_id and f"sales-orders/{so_id.lower()}", ship_rel, cust and cust.group(1)] if x)
    meta = dict(record=cb, customer=cust_meta.get("name", "?"), sales_order=so_id or "?", shipment=ship_meta.get("record", "?"),
                invoice=invoice, spec=param.capitalize(), net_kg=net_written)
    if ship_rel:
        meta["reconcile"] = f"net_kg = {ship_rel}#net_kg"
    meta.update(claim_cents_per_lb=f"{cents:g}", at_risk_usd=f"{at_risk:.2f}", status="Dispute drafted")
    cb_page = page("chargeback", f"Chargeback {cb}: {param} claim on {invoice}",
                   f"Customer claim: {text}\n\nEvidence: {links}\n\n"
                   f"Shipment {ship_meta.get('record', '?')} carried {net_written:,} kg net; at {cents:g} cents per lb the deduction "
                   f"is {usd(at_risk)}.\n\nDispute draft:\n\n{draft}\n\nOwner to approve before this leaves the building.", **meta)
    edits = [{"path": cb_rel + ".md", "content": cb_page}]
    if cust and customer:
        edits.append({"path": cust.group(1) + ".md",
                      "content": customer.rstrip() + f"\n- {datetime.now():%d %b}: {param} chargeback [[{cb_rel}]], {usd(at_risk)} at risk\n"})
    if not learned:
        edits.append({"path": sop_rel + ".md", "content": page(
            "sop", f"SOP: {family} chargeback",
            f"Learned from [[{cb_rel}]].\n\n"
            "1. Read the invoice or sales order number from the claim, and which spec is disputed.\n"
            "2. Open the sales order: the contract spec for that parameter.\n"
            "3. Open the shipment: the outbound QC result, retained sample number, loading photos.\n"
            "4. Check the customer's chargeback history.\n"
            "5. Dispute through the broker: contract spec, outbound QC result, joint re-test of the retained sample. "
            "No deduction accepted before the re-test.\n"
            "6. Owner approves before anything leaves the building. The record feeds the claims ledger.",
            record=f"SOP-{family.upper()}-CB", learned_from=cb, status="Active")})
    task = f"Draft the dispute for the {param} chargeback on {invoice}"
    twin = _start(task, edits, inject_error=inject_error, background=background)
    return {"twin": twin, "draft": draft, "steps": steps, "learned": learned, "record": cb, "path": cb_rel,
            "at_risk": at_risk, "sop": sop_rel, "net_kg": net_written, "net_kg_on_shipment": net_true, "invoice": invoice,
            "spec": param, "cents_per_lb": cents, "drafted_by": _agent_label(),
            "records": [e["path"][:-3] for e in edits]}
