"""The plant's workflows write every record through the gate. Sandbox off, rules, throwaway brain.

Run: python3 -m unittest discover -s tests"""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import twingate as tg  # noqa: E402
import plant  # noqa: E402

G = "TRUCK SCALE SL:1041 VNO:MH27AB4412 GROSS:6840KG"
T = "TRUCK SCALE SL:1041 VNO:MH27AB4412 TARE:2310KG"
NOTE = (HERE / "plant" / "audio" / "rate-note.txt").read_text(encoding="utf-8").strip()
CLAIM_A = "Spinning Mill A reports staple length 28.5 mm on invoice INV-102 against the 29 mm contract spec. They are deducting 0.6 cents per lb."
CLAIM_B = "Spinning Mill B reports micronaire 4.9 on invoice INV-110, above the 4.5 maximum. Charging back 0.4 cents per lb."


class PlantTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="twin-gate-plant-"))
        shutil.copytree(HERE / "brain-seed", self.tmp / "brain")
        self.saved = (tg.BRAIN, tg.STATE, tg.AGENT, tg.sbx.available, tg.gb.available)
        tg.BRAIN = (self.tmp / "brain").resolve()
        tg.STATE = (self.tmp / "state").resolve()
        tg.AGENT = "rules"
        tg.sbx.available = lambda: False
        tg.gb.available = lambda: False
        tg.ensure_brain()
        plant.reset()

    def tearDown(self):
        tg.BRAIN, tg.STATE, tg.AGENT, tg.sbx.available, tg.gb.available = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_truckload_writes_three_records_in_one_twin_and_merges_on_approval(self):
        self.assertIsNone(plant.on_sms(G)["reply"])
        r2 = plant.on_sms(T)
        self.assertEqual((r2["record"], r2["net_kg"]), ("ST-1041", 4530))
        r = plant.on_voice(NOTE, background=False)
        self.assertEqual(r["grower"], "Ramesh Patil")
        self.assertEqual((r["rate"], r["moisture"], r["amount_usd"]), (82.0, "8", 3714.6))
        st = tg.load(r["twin"])
        self.assertEqual(st["status"], "passed", st["checks"])
        self.assertEqual(sorted(st["changed"]), ["payables/gs-1041.md", "receiving/st-1041.md", "vendors/ramesh-patil.md"])
        self.assertIn("reconcile: net_kg = receiving/st-1041#net_kg", (tg.BRAIN / ".twins" / r["twin"] / "payables/gs-1041.md").read_text())
        self.assertFalse((tg.BRAIN / "payables/gs-1041.md").exists())      # nothing on main before approval
        tg.approve(r["twin"], "accounts")
        self.assertTrue((tg.BRAIN / "payables/gs-1041.md").exists())
        self.assertIn("gs-1041", (tg.BRAIN / "vendors/ramesh-patil.md").read_text())

    def test_claim_drafts_dispute_and_procedure_then_follows_it(self):
        r = plant.on_claim(CLAIM_A, background=False)
        self.assertEqual((r["record"], r["invoice"], r["spec"], r["net_kg"]), ("CB-0001", "INV-102", "staple", 17020))
        self.assertAlmostEqual(r["at_risk"], 225.14, places=2)
        self.assertFalse(r["learned"])
        self.assertIn("RS-0314", r["draft"])
        st = tg.load(r["twin"])
        self.assertEqual(st["status"], "passed", st["checks"])
        self.assertEqual(sorted(st["changed"]), ["chargebacks/cb-0001.md", "customers/spinning-mill-a.md", "sops/sop-quality-chargeback.md"])
        tg.approve(r["twin"])
        r2 = plant.on_claim(CLAIM_B, background=False)
        self.assertTrue(r2["learned"])
        self.assertEqual((r2["record"], r2["invoice"], r2["spec"]), ("CB-0002", "INV-110", "micronaire"))
        self.assertEqual(tg.load(r2["twin"])["status"], "passed")
        self.assertNotIn("sops/sop-quality-chargeback.md", tg.load(r2["twin"])["changed"])

    def test_wrong_weight_is_blocked_by_reconcile(self):
        r = plant.on_claim(CLAIM_A, inject_error=True, background=False)
        self.assertEqual(r["net_kg"], 15318)
        st = tg.load(r["twin"])
        self.assertEqual(st["status"], "failed")
        self.assertEqual([c["name"] for c in st["checks"] if not c["ok"]], ["numbers reconcile"])
        with self.assertRaises(SystemExit):
            tg.approve(r["twin"])

    def test_graph_and_config(self):
        g = plant.graph()
        self.assertEqual(len(g["nodes"]), 7)
        self.assertTrue(all(e["target"] in {n["id"] for n in g["nodes"]} for e in g["edges"]))
        self.assertEqual(plant.config()["agent"], "rules")


if __name__ == "__main__":
    unittest.main()
