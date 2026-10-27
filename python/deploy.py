"""
deploy.py - one-time setup and (re)build on TK5, through the card reader.

    python deploy.py setup     SETUP job: GDGs, model DSCB, audit KSDS, LOAD
                               (re-running it RESETS the audit history)
    python deploy.py build     BUILD job: load COBOL/REXX source, compile+link
    python deploy.py all       setup + build

Everything is created under <hlq>.MIG.* only.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import render
from tk5client import TK5, TK5Error

HERE = Path(__file__).resolve().parent

# acceptable return codes per step: (step, procstep) -> max RC
EXPECT = {
    "SETUP": {("DELETE", ""): 0, ("DEFINE", ""): 0, ("ALLOC", ""): 0},
    "BUILD": {("DELSRC", ""): 0, ("LOADCOB", ""): 0, ("LOADRX", ""): 0,
              ("COMPILE", "COB"): 4, ("COMPILE", "LKED"): 0},
}


def run_and_check(tk: TK5, name: str, cfg: dict) -> None:
    jcl = render.render_job(name, cfg)
    res = tk.run(jcl)
    print(f"  {'step':10s}{'procstep':10s}{'program':10s}result")
    for s, p, pgm, rc in res.steps:
        print(f"  {s:10s}{p:10s}{pgm:10s}{rc}")
    bad = []
    if res.jcl_error:
        bad.append("JCL ERROR")
    for (step, proc), mx in EXPECT[name].items():
        rc = res.rc(step, proc)
        if rc is None or not rc.startswith("RC=") or int(rc[4:]) > mx:
            bad.append(f"{step}{'.' + proc if proc else ''}={rc}")
    if bad:
        log = HERE.parent / "runs" / f"{name}_failed.txt"
        log.parent.mkdir(exist_ok=True)
        log.write_text(res.text, encoding="utf-8")
        raise TK5Error(f"{name} problems: {', '.join(bad)} - full job "
                       f"output saved in {log}")
    print(f"  {name} OK")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("step", choices=["setup", "build", "all"])
    ap.add_argument("--config", default=str(HERE / "config.json"))
    a = ap.parse_args()
    try:
        cfg = render.load_config(Path(a.config))
        tk = TK5(cfg)
        tk.check()
        for name in (["SETUP", "BUILD"] if a.step == "all"
                     else [a.step.upper()]):
            print(f"== {name}")
            run_and_check(tk, name, cfg)
    except (render.ConfigError, TK5Error) as e:
        print("\nERROR:", e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
