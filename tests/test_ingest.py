"""Ingestion, rejection reasons and source deduplication."""
import json
import os
import unittest

from stc import dedup, ingest
from tests.helpers import read, small_dataset

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "ingest")

EXPECTED_REJECTS = {
    "ingest/bidir.v": "inout_port",
    "ingest/broken_syntax.v": "compile_error",
    "ingest/logger.v": "unsafe_construct:system_task:$fopen",
    "ingest/other_clock.v": "unsupported_clock:clock",
    "ingest/parity8_unlicensed.v": "license_unknown",
    "ingest/shift4_copy.v": "exact_duplicate_of:ingest/shift4.v",
    "ingest/shift4_reformatted.v": "normalized_duplicate_of:ingest/shift4.v",
    "ingest/two_modules.v": "module_count:2",
    "ingest/wide64.v": "port_too_wide",
}


class Ingest(unittest.TestCase):
    def test_accepts_and_rejects_with_reasons(self):
        accepted, rejected = ingest.ingest(FIXTURES, dedup.Seen())
        self.assertEqual(sorted(a["file"] for a in accepted),
                         ["ingest/gray3.v", "ingest/parity8.v", "ingest/shift4.v", "ingest/shift4_renamed.v"])
        got = {r["file"]: r["reason"] for r in rejected}
        self.assertEqual(set(got), set(EXPECTED_REJECTS))
        for f, reason in EXPECTED_REJECTS.items():
            self.assertTrue(got[f].startswith(reason), (f, got[f]))

    def test_ingest_is_deterministic(self):
        a = ingest.ingest(FIXTURES, dedup.Seen())
        b = ingest.ingest(FIXTURES, dedup.Seen())
        self.assertEqual(a, b)

    def test_ingested_records(self):
        ds, _ = small_dataset()
        recs = [json.loads(l) for l in read(os.path.join(ds, "records.jsonl")).splitlines()]
        ing = [r for r in recs if r["family"] == "ingested"]
        self.assertEqual(len(ing), 4)
        for r in ing:
            self.assertEqual(r["model_check_status"], "none")
            self.assertEqual(r["license"], "project-owned")
            self.assertTrue(r["origin"].startswith("project fixture: ingest/"))
            ref = read(os.path.join(ds, r["reference_rtl_path"]))
            self.assertIn("module dut", ref)
            self.assertEqual(r["source_sha256"], dedup.sha256(read(os.path.join(FIXTURES, r["origin"].split("ingest/")[1]))))
            pub = read(os.path.join(ds, r["public_dir"], "interface.json"))
            for original in ("shift4", "shreg", "parity8", "gray3"):
                self.assertNotIn(original, pub)
        rejects = [json.loads(l) for l in read(os.path.join(ds, "rejects.jsonl")).splitlines()]
        self.assertEqual({r["file"] for r in rejects if "file" in r}, set(EXPECTED_REJECTS))


class Dedup(unittest.TestCase):
    A = "module a(input x, output y);\n  assign y = x; // copy\nendmodule\n"

    def test_exact_and_normalized_duplicates(self):
        seen = dedup.Seen()
        self.assertIsNone(seen.check(self.A, "a"))
        self.assertEqual(seen.check(self.A, "b"), "exact_duplicate_of:a")
        self.assertEqual(seen.check("/* new */ module a(input x,  output y);\n assign y = x;\nendmodule", "c"),
                         "normalized_duplicate_of:a")

    def test_renamed_copy_is_not_caught(self):
        # Documented limit: normalization is only comments and whitespace, so renaming defeats it.
        seen = dedup.Seen()
        seen.check(self.A, "a")
        self.assertIsNone(seen.check("module a(input in1, output out1);\n assign out1 = in1;\nendmodule", "d"))

    def test_spacing_inside_tokens_matters(self):
        # "y=x" and "y = x" normalize differently: the rule is conservative, not token-aware.
        self.assertNotEqual(dedup.normalize("assign y=x;"), dedup.normalize("assign y = x;"))


if __name__ == "__main__":
    unittest.main()
