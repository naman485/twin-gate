"""The proposal runs in two halves so a slow sandbox never hangs an HTTP request.

Run: python3 -m unittest discover -s tests
Sandbox off, rules agent, throwaway copy of the seed brain."""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import twingate as tg  # noqa: E402

TASK = "Draft the dispute for the short staple chargeback on INV-102"


class ProposeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="twin-gate-test-"))
        shutil.copytree(HERE / "brain-seed", self.tmp / "brain")
        self.saved = (tg.BRAIN, tg.STATE, tg.AGENT, tg.sbx.available, tg.gb.available)
        tg.BRAIN = (self.tmp / "brain").resolve()
        tg.STATE = (self.tmp / "state").resolve()
        tg.AGENT = "rules"
        tg.sbx.available = lambda: False
        tg.gb.available = lambda: False
        tg.ensure_brain()

    def tearDown(self):
        tg.BRAIN, tg.STATE, tg.AGENT, tg.sbx.available, tg.gb.available = self.saved
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_start_then_run_reaches_the_gate(self):
        tid = tg.propose_start(TASK, False)
        st = tg.load(tid)
        self.assertEqual(st["status"], "working")
        self.assertEqual(st["log"][0]["action"], "proposed")
        self.assertEqual(tg.review(tid)["status"], "working")  # must not crash before the branch exists
        tg.propose_run(tid)
        st = tg.load(tid)
        self.assertEqual(st["status"], "passed", json.dumps(st["checks"], indent=1))
        self.assertEqual(st["changed"], ["chargebacks/cb-0003.md"])
        self.assertIsNone(st["sandbox"])
        self.assertTrue(tg.verify_log(st))

    def test_wrong_number_fails_the_gate_and_approve_refuses(self):
        tid = tg.propose(TASK, True)
        st = tg.load(tid)
        self.assertEqual(st["status"], "failed")
        self.assertEqual([c["name"] for c in st["checks"] if not c["ok"]], ["numbers reconcile"])
        with self.assertRaises(SystemExit):
            tg.approve(tid)

    def test_failure_inside_the_run_lands_as_error_not_exception(self):
        tid = tg.propose_start("x", False)
        orig = tg.run_agent

        def boom(*a, **k):
            raise RuntimeError("agent exploded")

        tg.run_agent = boom
        try:
            tg.propose_run(tid)
        finally:
            tg.run_agent = orig
        st = tg.load(tid)
        self.assertEqual(st["status"], "error")
        self.assertIn("agent exploded", st["error"])
        self.assertEqual(st["log"][-1]["action"], "proposal failed")
        self.assertTrue(tg.verify_log(st))


if __name__ == "__main__":
    unittest.main()
