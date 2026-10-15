"""Same-seed rebuilds are byte-identical, and splits follow design groups, not seeds or variants."""
import hashlib
import json
import os
import shutil
import tempfile
import unittest

from stc import dedup
from stc.build import build
from tests.helpers import read


def tree_hashes(root):
    out = {}
    for d, _, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = hashlib.sha256(read(p, "rb")).hexdigest()
    return out


def records(ds, name="records.jsonl"):
    return [json.loads(l) for l in read(os.path.join(ds, name)).splitlines()]


class ReproAndSplits(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="stc-repro-")
        cls.a, cls.b, cls.c = (os.path.join(cls.tmp, n) for n in ("a", "b", "c"))
        build(cls.a, seed=0)            # three seed variants per design group
        build(cls.b, seed=0)
        build(cls.c, seed=1, small=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_same_seed_gives_identical_files(self):
        ha, hb = tree_hashes(self.a), tree_hashes(self.b)
        self.assertGreater(len(ha), 100)
        self.assertEqual(ha, hb)

    def test_no_absolute_paths_in_outputs(self):
        for rel in tree_hashes(self.a):
            self.assertNotIn(self.tmp, read(os.path.join(self.a, rel)), rel)

    def test_variants_of_a_group_share_one_split(self):
        groups = {}
        for r in records(self.a):
            groups.setdefault(r["design_group"], set()).add(r["split"])
        self.assertTrue(all(len(s) == 1 for s in groups.values()))
        # Every synthetic group made 3 variants; a variant whose visible trace repeats another one exactly
        # (possible for a counter whose only input is rst) is dropped as a duplicate task.
        counts = {}
        for r in records(self.a) + [r for r in records(self.a, "rejects.jsonl") if r["reason"] == "duplicate_task"]:
            counts[r["design_group"]] = counts.get(r["design_group"], 0) + 1
        synthetic = [g for g in groups if not g.startswith("ingest:")]
        self.assertEqual(len(synthetic), 21)
        self.assertTrue(all(counts[g] == 3 for g in synthetic), counts)

    def test_split_depends_only_on_the_group(self):
        split_a = {r["design_group"]: r["split"] for r in records(self.a)}
        split_c = {r["design_group"]: r["split"] for r in records(self.c)}
        self.assertEqual(split_a, split_c)
        for g, s in split_a.items():
            self.assertEqual(dedup.split_for(g), s)

    def test_variants_differ_only_in_stimulus(self):
        by_group = {}
        for r in records(self.a):
            by_group.setdefault(r["design_group"], []).append(r)
        for g, rs in by_group.items():
            if g.startswith("ingest:"):
                continue
            self.assertEqual(len({r["source_sha256"] for r in rs}), 1, g)
            self.assertEqual(len({r["seed"] for r in rs}), len(rs), g)
            traces = {read(os.path.join(self.a, r["public_trace_path"])) for r in rs}
            self.assertEqual(len(traces), len(rs), g)  # kept variants never share a visible trace

    def test_other_seed_changes_traces(self):
        ta = {r["design_group"]: read(os.path.join(self.a, r["public_trace_path"])) for r in records(self.a)}
        tc = {r["design_group"]: read(os.path.join(self.c, r["public_trace_path"])) for r in records(self.c)}
        self.assertTrue(any(ta[g] != tc[g] for g in tc))


if __name__ == "__main__":
    unittest.main()
