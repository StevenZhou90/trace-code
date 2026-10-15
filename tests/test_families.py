"""The five families: references pass, deliberate bugs fail, broken candidates are classified, the
independent model agrees with the reference, hidden tests are separate, and public files leak nothing."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

from stc.families import FAMILIES
from stc.selfcheck import selfcheck
from tests.helpers import read, small_dataset

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def records(ds):
    with open(os.path.join(ds, "records.jsonl")) as f:
        return [json.loads(l) for l in f]


class Families(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ds, cls.summary = small_dataset()
        cls.recs = records(cls.ds)
        cls.check = selfcheck(cls.ds)

    def test_all_five_families_are_present(self):
        self.assertEqual(set(FAMILIES), {"comb", "counter", "fsm", "arbiter", "handshake"})
        for f in FAMILIES:
            self.assertEqual(self.summary["by_family"][f]["groups"], len(FAMILIES[f].GROUPS))

    def test_references_pass_bugs_fail_broken_classified(self):
        for r in self.check["results"]:
            with self.subTest(family=r["family"], group=r["design_group"], candidate=r["candidate"]):
                self.assertEqual(r["status"], r["expected"])
        for f, s in self.check["summary"].items():
            self.assertEqual(s["references_pass"], s["references"], f)
            self.assertEqual(s["mutants_killed"], s["mutants"], f)
            self.assertEqual(s["broken_classified"], s["broken"], f)
            self.assertEqual(s["broken"], 6, f)

    def test_required_bug_kinds_exist(self):
        names = {(r["family"], r["candidate"]) for r in self.check["results"] if r["kind"] == "mutant"}
        for need in [("counter", "reset_to_one"), ("counter", "wraps_one_early"), ("fsm", "wrong_transition"),
                     ("arbiter", "reversed_priority"), ("handshake", "drop_word"), ("handshake", "duplicate_word"),
                     ("handshake", "unstable_data"), ("comb", "limit_off_by_one")]:
            self.assertIn(need, names)

    def test_reference_agrees_with_independent_model(self):
        for r in self.recs:
            if r["family"] in FAMILIES:
                self.assertEqual(r["model_check_status"], "agree")
                self.assertEqual(r["reference_status"], {"visible": "pass", "hidden": "pass"})

    def test_stream_checker_flags_lost_and_duplicated_words(self):
        by = {(r["design_group"], r["candidate"]): r for r in self.check["results"] if r["family"] == "handshake"}
        for (group, cand), r in by.items():
            if cand == "reference":
                self.assertEqual(r["protocol_problems"], [], group)
            elif cand in ("drop_word", "duplicate_word", "unstable_data"):
                self.assertTrue(r["protocol_problems"], (group, cand))

    def test_hidden_tests_are_separate_from_the_visible_trace(self):
        for r in self.recs:
            with open(os.path.join(self.ds, r["private_tests_path"])) as f:
                hidden = json.load(f)
            with open(os.path.join(self.ds, r["public_trace_path"])) as f:
                trace = json.load(f)
            n_in = sum(1 for s in trace["signals"] if s["dir"] == "input")
            names = [s["name"] for s in trace["signals"][:n_in]]
            visible = [dict(zip(names, row[:n_in])) for row in trace["rows"]]
            self.assertNotEqual(hidden["stimulus"][:len(visible)], visible)
            self.assertGreater(hidden["corner_rows"], 0)
            self.assertEqual(len(hidden["stimulus"]), r["hidden_rows"])

    def test_public_files_leak_nothing(self):
        bug_names = {b for f in FAMILIES.values() for p in f.GROUPS for b in f.bugs(p)}
        banned_words = set(FAMILIES) | bug_names | {"module ", "always", "assign", "endmodule", "expected",
                                                   "seed", "split", "private", "pattern", "family"}
        for r in self.recs:
            pub = os.path.join(self.ds, r["public_dir"])
            self.assertEqual(sorted(os.listdir(pub)), ["interface.json", "trace.json"])
            iface = json.loads(read(os.path.join(pub, "interface.json")))
            trace = json.loads(read(os.path.join(pub, "trace.json")))
            self.assertEqual(set(iface), {"module", "ports", "clock", "reset", "timing"})
            self.assertEqual(set(trace), {"signals", "rows"})
            self.assertEqual(iface["module"], "dut")
            text = (read(os.path.join(pub, "interface.json")) + read(os.path.join(pub, "trace.json"))).lower()
            for word in banned_words:
                self.assertNotIn(word.lower(), text, (r["task_id"], word))
            ref = read(os.path.join(self.ds, r["reference_rtl_path"]))
            for line in ref.splitlines():
                if len(line.strip()) > 12:
                    self.assertNotIn(line.strip().lower(), text)

    def test_evaluate_command_end_to_end(self):
        rec = next(r for r in self.recs if r["family"] == "fsm")
        ref = os.path.join(self.ds, rec["reference_rtl_path"])
        bad = os.path.join(tempfile.mkdtemp(), "bad.v")
        with open(bad, "w") as f:
            f.write(FAMILIES["fsm"].rtl(rec["params"], "mealy_output"))
        cmd = [sys.executable, "-m", "stc.evaluate", "--dataset", self.ds, "--task", rec["task_id"], "--candidate"]
        ok = subprocess.run(cmd + [ref], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout)
        self.assertEqual(json.loads(ok.stdout)["status"], "pass")
        no = subprocess.run(cmd + [bad], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(no.returncode, 1)
        self.assertEqual(json.loads(no.stdout)["status"], "fail")


if __name__ == "__main__":
    unittest.main()
