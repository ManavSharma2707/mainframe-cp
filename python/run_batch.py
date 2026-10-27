"""
run_batch.py - one complete validation run on TK5.

    python run_batch.py --scenario seeded      (REJECTED, RC 8)
    python run_batch.py --scenario clean       (APPROVED, RC 0)

Steps: generate data -> render MIGRUN with the data as inline cards ->
submit to the card reader -> wait for the output in prt/prt00e.txt ->
parse the printed result -> save runs/<BATCH_ID>/ -> compare with the
independent Python reference implementation.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

import gen_data
import render
import validator_core as vc
from tk5client import TK5, TK5Error

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent


def run(scenario: str, cfg: dict, log=print) -> Path:
    tk = TK5(cfg, log=log)
    tk.check()
    jcl = render.render_job("MIGRUN", cfg, scenario)
    res = tk.run(jcl)
    for s, p, pgm, rc in res.steps:
        log(f"  {s:9s}{p:6s}{pgm:10s}{rc}")
    if res.jcl_error:
        _save_fail(res.text)
        raise TK5Error("MIGRUN failed with a JCL ERROR (see runs/MIGRUN_failed.txt)")
    if res.abended:
        _save_fail(res.text)
        raise TK5Error(f"MIGRUN abended: {res.abended} (see runs/MIGRUN_failed.txt)")
    block = res.block("MIGOUT-BEGIN", "MIGOUT-END")
    if block is None:
        _save_fail(res.text)
        raise TK5Error("result block MIGOUT not found in the job output - "
                       "check REXXRUN in runs/MIGRUN_failed.txt")
    kv, exc = vc.parse_migout(block)
    batch = kv.get("BATCH_ID") or f"JOB{res.jobnum}"
    d = ROOT / "runs" / batch
    shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True)
    (d / "result.txt").write_text("".join(f"{k}={v}\n" for k, v in kv.items()))
    (d / "exceptions.txt").write_text("".join(vc.exc_to_line(e) + "\n" for e in exc))
    rpt = res.block("MIGRATION VALIDATION REPORT", "*** END OF REPORT ***")
    (d / "report.txt").write_text(rpt or "")
    (d / "joblog.txt").write_text(res.text, encoding="utf-8")
    src = ROOT / "data" / scenario
    for n in ("src_extract.txt", "tgt_extract.txt", "expected.json"):
        shutil.copy(src / n, d / n)
    (d / "meta.json").write_text(json.dumps(
        {"jobname": res.jobname, "jobnum": res.jobnum, "scenario": scenario,
         "steps": res.steps}, indent=2))
    return d


def _save_fail(text: str) -> None:
    p = ROOT / "runs" / "MIGRUN_failed.txt"
    p.parent.mkdir(exist_ok=True)
    p.write_text(text, encoding="utf-8")


def verify(d: Path) -> list[str]:
    kv = vc.parse_result((d / "result.txt").read_text())
    exc = vc.parse_excsort((d / "exceptions.txt").read_text())
    oracle = vc.reconcile(vc.read_lines(str(d / "src_extract.txt")),
                          vc.read_lines(str(d / "tgt_extract.txt")))
    return vc.compare_to_oracle(kv, exc, oracle)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--scenario", choices=gen_data.SCENARIOS, default="seeded")
    ap.add_argument("--config", default=str(HERE / "config.json"))
    a = ap.parse_args()
    try:
        cfg = render.load_config(Path(a.config))
        d = run(a.scenario, cfg)
    except (render.ConfigError, TK5Error) as e:
        print("\nERROR:", e)
        return 1
    kv = vc.parse_result((d / "result.txt").read_text())
    print("\n=== RESULT ===")
    for k in ("BATCH_ID", "DECISION", "RC", "SRC_RAW", "DUPS", "DUP_CONF",
              "SRC_UNIQUE", "TGT_RAW", "TGT_CNT", "MATCHED", "MISMATCH",
              "MISSING", "EXTRA", "REASON"):
        print(f"{k:11s} {kv.get(k, '')}")
    diffs = verify(d)
    if diffs:
        print("\nDIFFERENCES vs the Python reference implementation:")
        for x in diffs:
            print("  -", x)
        return 3
    print("\nTK5 result == Python reference result (verified)")
    print("saved in", d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
