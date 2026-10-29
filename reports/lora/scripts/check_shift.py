"""One-off: the shift-register state-machine style must pass every hidden test, at levels A, B and C."""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))  # repository root
from concurrent.futures import ProcessPoolExecutor
from stc import blind
from stc.evaluate import evaluate
from stc.families import fsm

def job(a):
    ds, rec, level = a
    p = json.loads(rec["design_group"][4:])
    text = fsm.rtl_shift(p)
    if level != "A":
        view = blind.make_view(rec["interface"], rec["task_id"], level)
        text = blind.wrap_candidate(rec["interface"], view, blind.view_reference(rec["interface"], view, text))
    return ds, rec["task_id"], level, evaluate(ds, rec, text)["status"]

def main():
  work = []
  for ds in sys.argv[1:]:
      for l in open(ds + "/records.jsonl"):
          r = json.loads(l)
          if r["family"] == "fsm":
              work += [(ds, r, L) for L in "ABC"]
  bad = 0
  with ProcessPoolExecutor() as pool:
      for ds, tid, L, st in pool.map(job, work, chunksize=8):
          if st != "pass":
              bad += 1
              if bad < 6: print(ds, tid, L, st)
  print(len(work), "checked,", bad, "not passing")

if __name__ == '__main__':
    main()
