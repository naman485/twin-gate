"""Checks that run against a twin before anything reaches the real brain.

Each check returns a dict: {"name", "ok", "detail"}. The gate passes only when
every check is ok. Checks are deliberately plain: front matter, links, numbers
that must reconcile with their source pages, no new external URLs, no secrets.
"""

from __future__ import annotations

import re
from pathlib import Path

FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)
LINK = re.compile(r"\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
URL = re.compile(r"https?://[^\s)>\]]+")
SECRET = re.compile(
    r"(sk-[A-Za-z0-9]{16,}|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}|apikey_[0-9a-f]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)"
)
RECONCILE = re.compile(r"^reconcile:\s*(\S+)\s*=\s*([a-z0-9/_.-]+)#([a-z0-9_-]+)\s*$", re.M | re.I)
NUM = re.compile(r"-?\d[\d,]*\.?\d*")


def _pages(root: Path):
    for p in sorted(root.rglob("*.md")):
        rel = p.relative_to(root).parts
        if ".twins" in rel or ".git" in rel:
            continue
        yield p


def _front(text: str) -> dict:
    m = FRONT.match(text)
    if not m:
        return {}
    out = {}
    for line in m.group(1).splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            out[k.strip()] = v.strip()
    return out


def _num(s: str):
    m = NUM.search(s or "")
    return float(m.group(0).replace(",", "")) if m else None


def check_front_matter(root: Path, changed: list[str]) -> dict:
    bad = []
    for rel in changed:
        p = root / rel
        if not p.exists() or p.suffix != ".md":
            continue
        fm = _front(p.read_text(encoding="utf-8"))
        if "type" not in fm or "title" not in fm:
            bad.append(rel)
    return {"name": "front matter", "ok": not bad,
            "detail": "every changed page carries type and title" if not bad else f"missing type or title: {', '.join(bad)}"}


def check_links(root: Path, changed: list[str]) -> dict:
    titles = set()
    for p in _pages(root):
        titles.add(p.stem.lower())
        titles.add(p.relative_to(root).with_suffix("").as_posix().lower())
        fm = _front(p.read_text(encoding="utf-8"))
        if "title" in fm:
            titles.add(fm["title"].lower())
    broken = []
    for rel in changed:
        p = root / rel
        if not p.exists() or p.suffix != ".md":
            continue
        for target in LINK.findall(p.read_text(encoding="utf-8")):
            if target.strip().lower() not in titles:
                broken.append(f"{rel} -> [[{target}]]")
    return {"name": "links resolve", "ok": not broken,
            "detail": "every [[link]] on a changed page points at a page that exists" if not broken else "; ".join(broken)}


def check_reconcile(root: Path, changed: list[str]) -> dict:
    """A page may declare `reconcile: <field> = <page>#<field>` in its front matter.
    The value on this page must equal the value on the source page."""
    failures = []
    for rel in changed:
        p = root / rel
        if not p.exists() or p.suffix != ".md":
            continue
        text = p.read_text(encoding="utf-8")
        fm = _front(text)
        m = FRONT.match(text)
        if not m:
            continue
        for field, src_page, src_field in RECONCILE.findall(m.group(1)):
            src = root / f"{src_page}.md"
            if not src.exists():
                failures.append(f"{rel}: source page {src_page} not found")
                continue
            here = _num(fm.get(field, ""))
            there = _num(_front(src.read_text(encoding="utf-8")).get(src_field, ""))
            if here is None or there is None or abs(here - there) > 1e-6:
                failures.append(f"{rel}: {field}={fm.get(field)} but {src_page}#{src_field}={_front(src.read_text(encoding='utf-8')).get(src_field)}")
    return {"name": "numbers reconcile", "ok": not failures,
            "detail": "every declared figure matches its source page" if not failures else "; ".join(failures)}


def check_no_new_urls(root: Path, changed: list[str], base_text: dict[str, str]) -> dict:
    added = []
    for rel in changed:
        p = root / rel
        if not p.exists() or p.suffix != ".md":
            continue
        before = set(URL.findall(base_text.get(rel, "")))
        after = set(URL.findall(p.read_text(encoding="utf-8")))
        for u in sorted(after - before):
            added.append(f"{rel}: {u}")
    return {"name": "no new external URLs", "ok": not added,
            "detail": "the twin added no outbound links" if not added else "; ".join(added)}


def check_no_secrets(root: Path, changed: list[str]) -> dict:
    hits = []
    for rel in changed:
        p = root / rel
        if not p.exists():
            continue
        if SECRET.search(p.read_text(encoding="utf-8", errors="ignore")):
            hits.append(rel)
    return {"name": "no secrets", "ok": not hits,
            "detail": "no key material on changed pages" if not hits else f"secret-shaped text in: {', '.join(hits)}"}


def run_all(root: Path, changed: list[str], base_text: dict[str, str]) -> list[dict]:
    return [
        check_front_matter(root, changed),
        check_links(root, changed),
        check_reconcile(root, changed),
        check_no_new_urls(root, changed, base_text),
        check_no_secrets(root, changed),
    ]
