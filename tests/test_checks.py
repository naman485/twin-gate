"""Run: python3 -m unittest discover -s tests"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import checks  # noqa: E402


def page(kind="chargeback", title="CB-1", extra="", body="Body."):
    return f"---\ntype: {kind}\ntitle: {title}\n{extra}---\n\n# {title}\n\n{body}\n"


class ChecksTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "shipping").mkdir()
        (self.root / "shipping" / "shp-1.md").write_text(page("shipment", "Shipment SHP-1", "net_kg: 17020\n"))
        (self.root / "chargebacks").mkdir()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, text):
        (self.root / "chargebacks" / "cb-1.md").write_text(text)
        return ["chargebacks/cb-1.md"]

    def result(self, name, changed, base=None):
        return next(r for r in checks.run_all(self.root, changed, base or {}) if r["name"] == name)

    def test_front_matter_required(self):
        changed = self.write("# no front matter\n")
        self.assertFalse(self.result("front matter", changed)["ok"])
        changed = self.write(page())
        self.assertTrue(self.result("front matter", changed)["ok"])

    def test_links_by_path_and_title(self):
        changed = self.write(page(body="See [[shipping/shp-1]] and [[Shipment SHP-1]]."))
        self.assertTrue(self.result("links resolve", changed)["ok"])
        changed = self.write(page(body="See [[shipping/missing]]."))
        self.assertFalse(self.result("links resolve", changed)["ok"])

    def test_reconcile_matches_source(self):
        changed = self.write(page(extra="net_kg: 17020\nreconcile: net_kg = shipping/shp-1#net_kg\n"))
        self.assertTrue(self.result("numbers reconcile", changed)["ok"])
        changed = self.write(page(extra="net_kg: 15318\nreconcile: net_kg = shipping/shp-1#net_kg\n"))
        r = self.result("numbers reconcile", changed)
        self.assertFalse(r["ok"])
        self.assertIn("15318", r["detail"])

    def test_no_new_urls(self):
        changed = self.write(page(body="Read https://example.com now."))
        self.assertFalse(self.result("no new external URLs", changed)["ok"])
        self.assertTrue(self.result("no new external URLs", changed, {"chargebacks/cb-1.md": "https://example.com"})["ok"])

    def test_no_secrets(self):
        changed = self.write(page(body="key sk-abcdefghijklmnopqrstuvwxyz"))
        self.assertFalse(self.result("no secrets", changed)["ok"])
        changed = self.write(page())
        self.assertTrue(self.result("no secrets", changed)["ok"])


if __name__ == "__main__":
    unittest.main()
