"""Parse weighbridge SMS and pair them into vehicle weighments.

Built on SYNTHETIC SMS. The regexes below are guesses at the format the scale
vendor uses. When real SMS arrive, change PATTERNS and nothing else should need
to move.

Pairing rule: an SMS joins an open weighment when both carry the same slip
number, or, when either lacks a slip number, when the vehicle numbers match
after removing spaces. Anything with neither is left for the office to pair with
one tap. Direction follows from which weight came first: gross first is a
purchase (raw cotton in), tare first is a dispatch (seed or bales out).

Usage: python3 plant/kanta_pair.py <file of "YYYY-MM-DD HH:MM:SS | sms body" lines>
"""

import re
import sys
from dataclasses import dataclass, field
from datetime import datetime

PATTERNS = {
    "slip": re.compile(r"\b(?:SL|SLIP|Wt\s+Slip)\b[:.\s]*(\d+)", re.I),
    "vehicle": re.compile(r"\b(?:VNO|Veh)\b[:.\s]*([A-Z]{2}\s?\d{1,2}\s?[A-Z]{0,3}\s?\d{3,4})\b", re.I),
    "gross": re.compile(r"\b(?:GROSS|Gr)\b[:.\s]*(\d+)", re.I),
    "tare": re.compile(r"\b(?:TARE|Tr)\b[:.\s]*(\d+)", re.I),
    "net": re.compile(r"\bNet\b[:.\s]*(\d+)", re.I),
}

# The same body arriving again within this many seconds is a resend.
DUPLICATE_WINDOW_S = 600


@dataclass
class Reading:
    received: datetime
    body: str
    slip: str | None
    vehicle: str | None
    gross: int | None
    tare: int | None
    net: int | None


@dataclass
class Weighment:
    first: Reading
    second: Reading | None = None
    flags: list[str] = field(default_factory=list)

    @property
    def slip(self):
        return self.first.slip or (self.second and self.second.slip)

    @property
    def vehicle(self):
        return self.first.vehicle or (self.second and self.second.vehicle)

    @property
    def gross(self):
        for r in (self.second, self.first):
            if r and r.gross is not None:
                return r.gross
        return None

    @property
    def tare(self):
        for r in (self.second, self.first):
            if r and r.tare is not None:
                return r.tare
        return None

    @property
    def net(self):
        if self.gross is None or self.tare is None:
            return None
        return self.gross - self.tare

    @property
    def direction(self):
        if self.first.gross is not None and self.first.tare is None:
            return "purchase"
        if self.first.tare is not None and self.first.gross is None:
            return "dispatch"
        return "unknown"

    @property
    def status(self):
        if not (self.slip or self.vehicle):
            return "NEEDS_CONFIRM"
        if self.second is None and (self.gross is None or self.tare is None):
            return "OPEN"
        if self.net is not None and self.net <= 0:
            return "INVALID"
        return "PAIRED"


def parse(received, body):
    def grab(name):
        m = PATTERNS[name].search(body)
        return m.group(1) if m else None

    gross, tare = grab("gross"), grab("tare")
    if gross is None and tare is None:
        return None
    vehicle = grab("vehicle")
    net = grab("net")
    return Reading(
        received=received,
        body=body,
        slip=grab("slip"),
        vehicle=re.sub(r"\s", "", vehicle).upper() if vehicle else None,
        gross=int(gross) if gross else None,
        tare=int(tare) if tare else None,
        net=int(net) if net else None,
    )


def same_vehicle(a, b):
    if a.slip and b.slip:
        return a.slip == b.slip
    return bool(a.vehicle and b.vehicle and a.vehicle == b.vehicle)


def pair(lines):
    """lines: iterable of (received datetime, body). Returns (weighments, ignored)."""
    weighments, ignored, open_, open_unkeyed = [], [], [], []
    last_seen = {}
    for received, body in sorted(lines, key=lambda x: x[0]):
        prev = last_seen.get(body)
        last_seen[body] = received
        if prev and (received - prev).total_seconds() <= DUPLICATE_WINDOW_S:
            continue
        r = parse(received, body)
        if r is None:
            ignored.append((received, body))
            continue

        is_full = r.gross is not None and r.tare is not None
        if not (r.slip or r.vehicle):
            # Unkeyed. Never guess silently: the nearest earlier unkeyed
            # reading of the other kind is proposed, and the office confirms.
            w = next((w for w in open_unkeyed if (r.gross is None) != (w.first.gross is None)), None)
            if w and not is_full:
                w.second = r
                open_unkeyed.remove(w)
                w.flags = ["no slip or vehicle number, proposed pair for the office to confirm"]
            else:
                w = Weighment(first=r, flags=["no slip or vehicle number"])
                weighments.append(w)
                if not is_full:
                    open_unkeyed.append(w)
            continue

        match = next((w for w in open_ if same_vehicle(w.first, r)), None)
        if match and (is_full or (r.gross is None) != (match.first.gross is None)):
            match.second = r
            open_.remove(match)
            if r.gross is not None and match.first.gross is not None and r.gross != match.first.gross:
                match.flags.append(f"gross differs: {match.first.gross} then {r.gross}")
            if r.tare is not None and match.first.tare is not None and r.tare != match.first.tare:
                match.flags.append(f"tare differs: {match.first.tare} then {r.tare}")
        else:
            if match:
                match.flags.append("superseded by a later reading of the same kind")
                open_.remove(match)
            w = Weighment(first=r)
            weighments.append(w)
            if not is_full:
                open_.append(w)

    for w in weighments:
        stated = (w.second or w.first).net
        if stated is not None and w.net is not None and stated != w.net:
            w.flags.append(f"SMS net {stated} != gross - tare {w.net}")
        if w.status == "INVALID":
            w.flags.append("tare is not below gross")
    return weighments, ignored


def read_file(path):
    lines = []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw or raw.startswith("#"):
                continue
            stamp, body = raw.split("|", 1)
            lines.append((datetime.strptime(stamp.strip(), "%Y-%m-%d %H:%M:%S"), body.strip()))
    return lines


def main(path):
    weighments, ignored = pair(read_file(path))
    print(f"{'first SMS':<17} {'slip':<5} {'vehicle':<11} {'dir':<9} {'gross':>6} {'tare':>6} {'net':>6} {'qtl':>6}  status")
    for w in weighments:
        net = w.net if w.net is not None else ""
        qtl = f"{w.net / 100:.2f}" if w.net is not None and w.net > 0 else ""
        print(
            f"{w.first.received:%Y-%m-%d %H:%M} {w.slip or '':<5} {w.vehicle or '?':<11} {w.direction:<9} "
            f"{w.gross or '':>6} {w.tare or '':>6} {net:>6} {qtl:>6}  {w.status}"
            + (f"  ({'; '.join(w.flags)})" if w.flags else "")
        )
    for received, body in ignored:
        print(f"{received:%Y-%m-%d %H:%M} ignored, not a weighment: {body}")


if __name__ == "__main__":
    main(sys.argv[1])
