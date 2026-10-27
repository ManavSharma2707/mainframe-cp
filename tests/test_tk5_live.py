"""
test_tk5_live.py - full end-to-end test against a RUNNING TK5.
    python tests/test_tk5_live.py            (setup + build + 5 runs + history)
    python tests/test_tk5_live.py --no-setup (keep the existing audit history)

Uses python/config.json. Every run is compared with the reference
implementation. Takes about 2-4 minutes.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "python"))
import deploy                        # noqa: E402
import gen_data                      # noqa: E402
import history                       # noqa: E402
import render                        # noqa: E402
import run_batch                     # noqa: E402
from tk5client import TK5, TK5Error  # noqa: E402

EXPECT = {"seeded": ("REJECTED", "8"), "dups": ("WARNING", "4"),
          "clean": ("APPROVED", "0"), "conflict": ("REJECTED", "8"),
          "dup_target": ("ABORTED", "12")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-setup", action="store_true")
    ap.add_argument("--config", default=str(ROOT / "python" / "config.json"))
    a = ap.parse_args()
    cfg = render.load_config(Path(a.config))
    try:
        TK5(cfg).check()
    except TK5Error as e:
        print("TK5 not reachable - skipped:", e)
        return 0
    bad = 0
    tk = TK5(cfg, log=lambda *_: None)
    for job in ([] if a.no_setup else ["SETUP"]) + ["BUILD"]:
        try:
            deploy.run_and_check(tk, job, cfg)
            print(f"{job:12s} PASS")
        except TK5Error as e:
            print(f"{job:12s} FAIL {e}")
            return 1
    for sc in gen_data.SCENARIOS:
        try:
            d = run_batch.run(sc, cfg, log=lambda *_: None)
            kv = run_batch.vc.parse_result((d / "result.txt").read_text())
            diffs = run_batch.verify(d)
            ok = (kv.get("DECISION"), kv.get("RC")) == EXPECT[sc] and not diffs
            print(f"{sc:12s} {'PASS' if ok else 'FAIL'} {kv.get('DECISION')} "
                  f"RC {kv.get('RC')} {diffs if diffs else ''}")
            bad += not ok
        except TK5Error as e:
            print(f"{sc:12s} FAIL {e}")
            bad += 1
    try:
        lines = [l for l in history.fetch(cfg) if l.startswith("HIST:")]
        print(f"{'history':12s} {'PASS' if lines else 'FAIL'} {len(lines)} batch(es) in VSAM")
        bad += not lines
    except TK5Error as e:
        print("history      FAIL", e)
        bad += 1
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
